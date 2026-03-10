"""Phase 2 오케스트레이션: 다글로 + school_sync -> NotebookLM 패키지."""
from __future__ import annotations

import json
import platform
import subprocess
import sys
from pathlib import Path

from loguru import logger

from .config import AppConfig
from .guide_generator import generate_guide
from .srt_parser import (
    extract_date_from_filename,
    find_all_dates,
    find_daglo_files,
    format_for_notebooklm,
    parse_srt,
    parse_txt,
)


def pack_course(course: str, cfg: AppConfig, date: str | None = None,
                auto_open: bool = True, no_sync: bool = False) -> Path | None:
    """한 과목의 NotebookLM 업로드 패키지를 생성한다.

    date가 None이면 해당 과목의 모든 날짜를 처리한다.

    Returns:
        마지막으로 생성된 패키지 디렉토리 경로. 실패 시 None.
    """
    daglo_dir = Path(cfg.daglo.input_dir)

    if not date:
        dates = find_all_dates(daglo_dir, course)
        if not dates:
            logger.error(f"다글로 파일 없음: {daglo_dir / course}/")
            logger.info(f"  -> {daglo_dir / course}/ 폴더에 YYYY-MM-DD.srt 또는 .txt 파일을 넣어주세요.")
            return None
        if len(dates) > 1:
            logger.info(f"{course}: {len(dates)}개 날짜 발견 ({', '.join(dates)})")
        last_result = None
        for d in dates:
            result = _pack_single(course, cfg, d, daglo_dir, auto_open=auto_open, no_sync=no_sync)
            if result:
                last_result = result
        return last_result

    return _pack_single(course, cfg, date, daglo_dir, auto_open=auto_open, no_sync=no_sync)


def _pack_single(course: str, cfg: AppConfig, date: str, daglo_dir: Path,
                 auto_open: bool = True, no_sync: bool = False) -> Path | None:
    """단일 날짜에 대한 패키징을 수행한다."""
    daglo_files = find_daglo_files(daglo_dir, course, date)

    if not daglo_files:
        logger.error(f"다글로 파일 없음: {daglo_dir / course}/ (date={date})")
        return None

    logger.info(f"패키징 시작: {course} / {date}")

    # 0. school_sync 크롤링 상태 체크
    if not no_sync:
        _check_school_sync(cfg, date)

    # 1. 전사본 정제
    transcript_text = ""
    if "srt" in daglo_files:
        segments = parse_srt(daglo_files["srt"])
        transcript_text = format_for_notebooklm(segments)
    elif "txt" in daglo_files:
        transcript_text = parse_txt(daglo_files["txt"])

    if not transcript_text:
        logger.error("전사본 내용이 비어 있습니다.")
        return None

    # 2. 학습 컨텍스트 (school_sync에서 생성한 파일 읽기)
    context_md = _load_context(cfg, course)

    # 3. 가이드 프롬프트
    guide_md = generate_guide(course, date, cfg)

    # 4. 출력 디렉토리 생성
    output_dir = Path(cfg.notebooklm.output_dir) / f"{course}_{date}"
    output_dir.mkdir(parents=True, exist_ok=True)

    transcript_path = output_dir / f"전사본_{date}.txt"
    transcript_path.write_text(transcript_text, encoding="utf-8")
    logger.info(f"  전사본: {transcript_path.name} ({len(transcript_text)}자)")

    if context_md:
        context_path = output_dir / "학습컨텍스트.md"
        context_path.write_text(context_md, encoding="utf-8")
        logger.info(f"  학습컨텍스트: {context_path.name}")
    else:
        logger.warning("  학습컨텍스트: school_sync 데이터 없음 (건너뜀)")

    guide_path = output_dir / "NotebookLM_가이드.md"
    guide_path.write_text(guide_md, encoding="utf-8")
    logger.info(f"  가이드: {guide_path.name}")

    # 5. README
    materials_path = cfg.school_sync.downloads_path / course
    readme = _build_readme(date, materials_path, context_md != "")
    (output_dir / "README.txt").write_text(readme, encoding="utf-8")

    logger.info(f"패키지 생성 완료: {output_dir}")

    # 6. 폴더 열기
    if auto_open:
        _open_folder(output_dir)
        if materials_path.exists():
            _open_folder(materials_path)
        else:
            logger.warning(f"  수업자료 폴더 없음: {materials_path}")

    return output_dir


def pack_all(cfg: AppConfig, auto_open: bool = True, no_sync: bool = False) -> list[Path]:
    """모든 과목의 미처리 다글로 파일을 패키징한다."""
    daglo_dir = Path(cfg.daglo.input_dir)
    if not daglo_dir.exists():
        logger.error(f"다글로 입력 폴더 없음: {daglo_dir}")
        return []

    results: list[Path] = []
    skip_dirs = {"inbox"}
    for course_dir in sorted(daglo_dir.iterdir()):
        if not course_dir.is_dir() or course_dir.name.startswith("."):
            continue
        if course_dir.name in skip_dirs:
            continue
        course = course_dir.name
        result = pack_course(course, cfg, auto_open=auto_open, no_sync=no_sync)
        if result:
            results.append(result)

    if not results:
        logger.warning("패키징할 다글로 파일이 없습니다.")
    else:
        logger.info(f"총 {len(results)}개 과목 패키징 완료")

    return results


def _load_context(cfg: AppConfig, course: str) -> str:
    """school_sync가 생성한 과목별 학습 컨텍스트 파일을 읽는다."""
    context_path = cfg.school_sync.context_path / f"{course}.md"
    if not context_path.exists():
        logger.warning(f"학습 컨텍스트 파일 없음: {context_path}")
        logger.info("  -> school_sync에서 정규화를 실행하면 자동 생성됩니다.")
        return ""
    try:
        content = context_path.read_text(encoding="utf-8")
        logger.info(f"  학습 컨텍스트 로드: {context_path.name} ({len(content)}자)")
        return content
    except Exception as e:
        logger.warning(f"학습 컨텍스트 읽기 실패: {e}")
        return ""


def _build_readme(date: str, materials_path: Path, has_context: bool) -> str:
    files = [
        f"1. 전사본_{date}.txt (이 폴더)",
        "2. NotebookLM_가이드.md (이 폴더)",
    ]
    if has_context:
        files.insert(1, "3. 학습컨텍스트.md (이 폴더)")

    materials_note = f"   -> {materials_path}" if materials_path.exists() else "   -> (폴더 없음 - school_sync --download 실행 필요)"

    return f"""=== NotebookLM 업로드 안내 ===

아래 파일을 NotebookLM 노트북에 업로드하세요:

{chr(10).join(files)}

수업자료 PDF/PPT:
{materials_note}

가이드 파일(NotebookLM_가이드.md)을 반드시 소스에 포함하세요.
NotebookLM이 데이터를 이해하고 활용하는 데 필요합니다.
"""


def _check_school_sync(cfg: AppConfig, transcript_date: str):
    """school_sync 실행 기록을 확인하고, 필요하면 자동 크롤링을 실행한다."""
    ss_root = Path(cfg.school_sync.root)
    if not cfg.school_sync.root or not ss_root.exists():
        logger.info("school_sync 미설정 또는 경로 없음 (크롤링 체크 건너뜀)")
        return

    log_path = ss_root / "output" / ".last_run.json"
    needs_sync = False

    if not log_path.exists():
        logger.warning("school_sync 실행 기록 없음")
        needs_sync = True
    else:
        try:
            log = json.loads(log_path.read_text(encoding="utf-8"))
            last_run = log.get("last_run", "")[:10]
            if last_run < transcript_date:
                logger.warning(
                    f"school_sync 마지막 실행: {last_run} (전사본 날짜: {transcript_date})"
                )
                needs_sync = True
            else:
                logger.info(f"school_sync 실행 기록 확인: {last_run} (최신)")
        except Exception as e:
            logger.warning(f"실행 기록 읽기 실패: {e}")
            needs_sync = True

    if not needs_sync:
        return

    try:
        answer = input("  school_sync 크롤링을 실행할까요? (y/N): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"
    if answer != "y":
        logger.info("크롤링 건너뜀")
        return

    logger.info("school_sync 크롤링을 실행합니다...")
    try:
        result = subprocess.run(
            [sys.executable, "main.py", "--download"],
            cwd=str(ss_root),
            timeout=300,
        )
        if result.returncode == 0:
            logger.info("school_sync 크롤링 완료")
        else:
            logger.warning(f"school_sync 크롤링 실패 (exit code: {result.returncode})")
    except subprocess.TimeoutExpired:
        logger.error("school_sync 크롤링 타임아웃 (5분)")
    except Exception as e:
        logger.error(f"school_sync 실행 실패: {e}")


def _open_folder(path: Path):
    """탐색기에서 폴더를 연다."""
    try:
        if platform.system() == "Windows":
            subprocess.Popen(["explorer", str(path.resolve())])
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        logger.info(f"  폴더 열기: {path}")
    except Exception as e:
        logger.warning(f"  폴더 열기 실패: {e}")
