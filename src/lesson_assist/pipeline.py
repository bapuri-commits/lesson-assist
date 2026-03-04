"""파이프라인 오케스트레이터.

전사 → 교정 검토 → 분할 → 요약(파트별 RAG 주입) → 액션 추출
→ Visual Anchors → 자막 → 노트 생성 → RAG 저장 → 데일리 연동
"""
from __future__ import annotations

from datetime import date as date_type
from pathlib import Path

from loguru import logger

from .actions import extract_actions
from .anchors import AnchorsResult, detect_anchors
from .config import AppConfig
from .daily_linker import link_to_daily
from .eclass import EclassData
from .obsidian_writer import write_note
from .preprocess import is_video, prepare_input
from .review import (
    ReviewCandidate,
    apply_corrections,
    extract_candidates,
    load_review,
    print_candidates,
    save_review,
)
from .segment import save_parts, segment_transcript
from .subtitle import save_subtitles
from .summarize import summarize
from .transcribe import TranscriptResult, transcribe


def run_pipeline(
    audio_path: Path,
    course: str,
    cfg: AppConfig,
    date: str | None = None,
    skip_review: bool = False,
    review_mode: bool = False,
    interactive: bool = False,
    no_daily: bool = False,
    include_raw: bool = True,
    no_rag: bool = False,
    no_anchors: bool = False,
    no_subtitle: bool = False,
) -> Path:
    """전체 파이프라인을 실행하고 생성된 노트 경로를 반환한다."""
    if not audio_path.exists():
        raise FileNotFoundError(f"입력 파일 없음: {audio_path}")

    if not cfg.openai_api_key:
        raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다. 환경변수 또는 config.yaml을 확인하세요.")

    if not cfg.vault_path:
        raise ValueError("vault_path가 설정되지 않았습니다. config.yaml을 확인하세요.")

    if date is None:
        date = date_type.today().isoformat()

    file_id = f"{date}_{course}"
    out_base = Path(cfg.output_dir)
    transcript_dir = out_base / "transcripts"
    review_dir = out_base / "reviews"
    parts_dir = out_base / "parts"
    summary_dir = out_base / "summaries"
    subtitle_dir = out_base / "subtitles"

    # 0. 전처리 (영상 → 오디오)
    original_path = audio_path
    input_is_video = is_video(audio_path)
    if input_is_video:
        logger.info("=" * 50)
        logger.info("STEP 0: 영상 → 오디오 추출")
        logger.info("=" * 50)
        audio_path, _ = prepare_input(audio_path, out_base / "extracted_audio")

    # 1. 전사
    logger.info("=" * 50)
    logger.info("STEP 1: 전사")
    logger.info("=" * 50)

    seg_path = transcript_dir / f"{file_id}_segments.json"
    if review_mode and seg_path.exists():
        logger.info("기존 전사 결과 로드 (--review 모드)")
        transcript = TranscriptResult.load(seg_path)
    else:
        transcript = transcribe(audio_path, cfg.transcribe, out_dir=transcript_dir, file_id=file_id)
        if not seg_path.exists():
            transcript.save(transcript_dir, file_id)

    # 2. 품질 검토
    logger.info("=" * 50)
    logger.info("STEP 2: 품질 검토")
    logger.info("=" * 50)

    review_path = review_dir / f"{file_id}_review.jsonl"
    candidates: list[ReviewCandidate] = []

    if review_mode and review_path.exists():
        candidates = load_review(review_path)
        corrected_count = sum(1 for c in candidates if c.action == "accepted")
        logger.info(f"교정 파일 로드: {len(candidates)}개 후보, {corrected_count}개 교정됨")
        transcript = apply_corrections(transcript, candidates)
    elif not skip_review:
        candidates = extract_candidates(transcript, cfg.review)
        if candidates:
            save_review(candidates, review_dir, file_id)
            print_candidates(candidates)

            if interactive:
                _interactive_review(candidates, review_path)
                transcript = apply_corrections(transcript, candidates)
            else:
                logger.info(f"교정 파일: {review_path}")
                logger.info("교정하려면 파일을 편집한 뒤 --review 플래그로 재실행하세요.")
    else:
        logger.info("품질 검토 건너뜀 (--skip-review)")

    # 2.5 자막 생성
    if not no_subtitle:
        logger.info("=" * 50)
        logger.info("STEP 2.5: 자막 생성 (SRT/VTT)")
        logger.info("=" * 50)
        save_subtitles(transcript, subtitle_dir, file_id)

    # 3. 분할
    logger.info("=" * 50)
    logger.info("STEP 3: 분할")
    logger.info("=" * 50)

    parts = segment_transcript(transcript, cfg.segment)
    save_parts(parts, parts_dir, file_id)

    # 3.5 RAG 준비 + eclass 자료 저장 + 주차 매칭
    rag_store = None
    week_topic: str | None = None

    if cfg.rag.enabled and not no_rag:
        logger.info("=" * 50)
        logger.info("STEP 3.5: RAG 준비")
        logger.info("=" * 50)
        rag_store = _get_rag_store(cfg)

        if rag_store is not None:
            _load_eclass_materials_to_rag(cfg, course, rag_store)

    eclass = EclassData(cfg.eclass)
    if eclass.available:
        logger.info("eclass 주차 주제 매칭 중…")
        week_topic = eclass.get_week_topic(course, date)

    # 4. 요약 (각 파트마다 개별 RAG 검색·주입)
    logger.info("=" * 50)
    logger.info("STEP 4: 요약")
    logger.info("=" * 50)

    summary_result = summarize(
        parts, course, date, cfg.summarize, cfg.openai_api_key,
        rag_store=rag_store,
        week_topic=week_topic,
    )
    summary_result.save(summary_dir, file_id)

    # 4.5 RAG 저장
    if cfg.rag.enabled and not no_rag and rag_store is not None:
        logger.info("=" * 50)
        logger.info("STEP 4.5: RAG 저장")
        logger.info("=" * 50)
        _save_to_rag_with_store(rag_store, course, date, summary_result)

    # 5. 액션 추출
    logger.info("=" * 50)
    logger.info("STEP 5: 액션 아이템 추출")
    logger.info("=" * 50)

    actions_result = extract_actions(transcript, course, date, cfg.summarize, cfg.openai_api_key)
    actions_result.save(summary_dir, file_id)

    # 5.5 Visual Anchors
    anchors_result: AnchorsResult | None = None
    if not no_anchors:
        logger.info("=" * 50)
        logger.info("STEP 5.5: Visual Anchors 탐지")
        logger.info("=" * 50)
        anchors_result = detect_anchors(transcript, cfg.anchors, course, date)

        if input_is_video and anchors_result.candidates:
            _extract_video_screenshots(
                original_path, anchors_result, out_base / "screenshots", file_id,
            )

    # 6. 노트 생성
    logger.info("=" * 50)
    logger.info("STEP 6: Obsidian 노트 생성")
    logger.info("=" * 50)

    note_path = write_note(
        summary=summary_result,
        transcript=transcript,
        actions=actions_result,
        review_candidates=candidates,
        anchors=anchors_result,
        vault_path=cfg.vault_path,
        course=course,
        date=date,
        audio_filename=original_path.name,
        summarize_model=cfg.summarize.model,
        include_raw=include_raw,
    )

    # 7. 데일리 노트 연동
    if not no_daily:
        logger.info("=" * 50)
        logger.info("STEP 7: 데일리 노트 연동")
        logger.info("=" * 50)

        first_line = summary_result.integrated_summary.strip().split("\n")[0]
        first_line = first_line.lstrip("#").strip()
        if len(first_line) > 60:
            first_line = first_line[:57] + "…"

        link_to_daily(cfg.vault_path, course, date, first_line, actions_result)

    logger.info("=" * 50)
    logger.info(f"완료! 노트: {note_path}")
    logger.info("=" * 50)
    return note_path


def _get_rag_store(cfg: AppConfig):
    """RAG store 인스턴스를 생성한다. chromadb 미설치 시 None."""
    try:
        from .rag import LectureStore
        return LectureStore(cfg.rag, cfg.openai_api_key)
    except ImportError:
        logger.warning("chromadb가 설치되지 않아 RAG를 건너뜁니다. pip install chromadb")
        return None
    except Exception as e:
        logger.warning(f"RAG 초기화 실패 (계속 진행): {e}")
        return None


def _load_eclass_materials_to_rag(cfg: AppConfig, course: str, store) -> None:
    """eclass 강의자료(PDF/PPT)를 RAG에 저장한다."""
    eclass = EclassData(cfg.eclass)
    if not eclass.available:
        return

    try:
        from .material_loader import extract_and_store_materials
        materials = eclass.get_downloaded_materials(course)
        if materials:
            extract_and_store_materials(store, course, materials)
    except ImportError:
        logger.debug("material_loader 또는 의존성 없음 — eclass 자료 RAG 저장 스킵")
    except Exception as e:
        logger.warning(f"eclass 자료 RAG 저장 실패 (계속 진행): {e}")


def _save_to_rag_with_store(store, course: str, date: str, summary_result) -> None:
    """요약 결과를 RAG에 저장한다. 기존 store 인스턴스를 재사용."""
    try:
        part_texts = [ps.summary for ps in summary_result.part_summaries]
        store.add_lecture(
            course=course,
            date=date,
            integrated_summary=summary_result.integrated_summary,
            part_summaries=part_texts,
        )
    except Exception as e:
        logger.warning(f"RAG 저장 실패 (계속 진행): {e}")


def _extract_video_screenshots(
    video_path: Path,
    anchors_result: AnchorsResult,
    screenshots_dir: Path,
    file_id: str,
) -> None:
    """온라인 수업 영상에서 Visual Anchor 시점의 스크린샷을 추출한다."""
    try:
        from .preprocess import extract_screenshots
        from .anchors import attach_image

        timestamps = [c.timestamp for c in anchors_result.candidates]
        paths = extract_screenshots(video_path, timestamps, screenshots_dir, file_id)

        for path in paths:
            stem = path.stem
            parts = stem.rsplit("_", 1)
            if parts and parts[-1].endswith("s"):
                try:
                    ts = float(parts[-1][:-1])
                    attach_image(anchors_result, path.name, ts)
                except ValueError:
                    pass
    except Exception as e:
        logger.warning(f"스크린샷 추출 실패 (계속 진행): {e}")


def _interactive_review(candidates: list[ReviewCandidate], review_path: Path) -> None:
    """터미널에서 대화형으로 교정을 수행한다."""
    print("\n대화형 교정 모드 (Enter로 건너뛰기, 'q'로 종료)")
    print("-" * 40)

    for c in candidates:
        print(f"\n[{c.start}~{c.end}] ({c.reason})")
        print(f"  원문: \"{c.original}\"")
        corrected = input("  교정 (Enter=건너뛰기, q=종료): ").strip()

        if corrected.lower() == "q":
            break
        elif corrected:
            c.corrected = corrected
            c.action = "accepted"
            print(f"  → 교정됨: \"{corrected}\"")
        else:
            c.action = "skipped"

    save_review(candidates, review_path.parent, review_path.stem.replace("_review", ""))
    print(f"\n교정 결과 저장: {review_path}")


# --- 독립 서브커맨드 ---

def run_exam_sheet(
    course: str,
    cfg: AppConfig,
    date_range: tuple[str, str] | None = None,
    output_dir: Path | None = None,
) -> Path:
    """시험 대비 A4 서브커맨드."""
    from .exam_sheet import generate_exam_sheet
    summaries_dir = Path(cfg.output_dir) / "summaries"
    return generate_exam_sheet(
        course=course,
        summaries_dir=summaries_dir,
        cfg=cfg.exam_sheet,
        api_key=cfg.openai_api_key,
        date_range=date_range,
        output_dir=output_dir,
    )
