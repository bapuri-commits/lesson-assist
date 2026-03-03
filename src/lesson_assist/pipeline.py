"""파이프라인 오케스트레이터.

전사 → 교정 검토 → 분할 → 요약 → 액션 추출 → 노트 생성 → 데일리 연동
"""
from __future__ import annotations

from datetime import date as date_type
from pathlib import Path

from loguru import logger

from .actions import extract_actions
from .config import AppConfig
from .daily_linker import link_to_daily
from .obsidian_writer import write_note
from .review import (
    ReviewCandidate,
    apply_corrections,
    extract_candidates,
    load_review,
    print_candidates,
    save_review,
)
from .segment import save_parts, segment_transcript
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
) -> Path:
    """전체 파이프라인을 실행하고 생성된 노트 경로를 반환한다."""
    if not audio_path.exists():
        raise FileNotFoundError(f"오디오 파일 없음: {audio_path}")

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

    # 3. 분할
    logger.info("=" * 50)
    logger.info("STEP 3: 분할")
    logger.info("=" * 50)

    parts = segment_transcript(transcript, cfg.segment)
    save_parts(parts, parts_dir, file_id)

    # 4. 요약
    logger.info("=" * 50)
    logger.info("STEP 4: 요약")
    logger.info("=" * 50)

    summary_result = summarize(parts, course, date, cfg.summarize, cfg.openai_api_key)
    summary_result.save(summary_dir, file_id)

    # 5. 액션 추출
    logger.info("=" * 50)
    logger.info("STEP 5: 액션 아이템 추출")
    logger.info("=" * 50)

    actions_result = extract_actions(transcript, course, date, cfg.summarize, cfg.openai_api_key)
    actions_result.save(summary_dir, file_id)

    # 6. 노트 생성
    logger.info("=" * 50)
    logger.info("STEP 6: Obsidian 노트 생성")
    logger.info("=" * 50)

    note_path = write_note(
        summary=summary_result,
        transcript=transcript,
        actions=actions_result,
        review_candidates=candidates,
        vault_path=cfg.vault_path,
        course=course,
        date=date,
        audio_filename=audio_path.name,
        summarize_model=cfg.summarize.model,
        include_raw=include_raw,
    )

    # 7. 데일리 노트 연동
    if not no_daily:
        logger.info("=" * 50)
        logger.info("STEP 7: 데일리 노트 연동")
        logger.info("=" * 50)

        # 통합 요약의 첫 줄을 한 줄 요약으로 사용
        first_line = summary_result.integrated_summary.strip().split("\n")[0]
        first_line = first_line.lstrip("#").strip()
        if len(first_line) > 60:
            first_line = first_line[:57] + "…"

        link_to_daily(cfg.vault_path, course, date, first_line, actions_result)

    logger.info("=" * 50)
    logger.info(f"완료! 노트: {note_path}")
    logger.info("=" * 50)
    return note_path


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
