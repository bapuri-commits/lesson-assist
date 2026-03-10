"""Phase 2 오케스트레이션: 다글로 + school_sync -> NotebookLM 패키지."""
from __future__ import annotations

import json
import platform
import re
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

    출력 구조: output/notebooklm/{과목}/
      ├── 학습컨텍스트.md        (공유, 최신으로 갱신)
      ├── NotebookLM_가이드.md   (공유)
      ├── README.txt
      ├── 전사본_2026-03-04.txt  (날짜별)
      └── 전사본_2026-03-10.txt  (날짜별)

    Returns:
        과목 패키지 디렉토리 경로. 실패 시 None.
    """
    daglo_dir = Path(cfg.daglo.input_dir)

    if date:
        dates = [date]
    else:
        dates = find_all_dates(daglo_dir, course)

    if not dates:
        logger.error(f"다글로 파일 없음: {daglo_dir / course}/")
        logger.info(f"  -> {daglo_dir / course}/ 폴더에 YYYY-MM-DD.srt 또는 .txt 파일을 넣어주세요.")
        return None

    # 과목 단위 출력 디렉토리
    output_dir = Path(cfg.notebooklm.output_dir) / course
    output_dir.mkdir(parents=True, exist_ok=True)

    if len(dates) > 1:
        logger.info(f"{course}: {len(dates)}개 날짜 발견 ({', '.join(dates)})")

    # 0. school_sync 크롤링 상태 체크 + 컨텍스트 재생성 (과목당 1회)
    if not no_sync:
        _check_school_sync(cfg, course, dates[-1])

    # 1. 날짜별 전사본 생성
    for d in dates:
        daglo_files = find_daglo_files(daglo_dir, course, d)
        if not daglo_files:
            logger.warning(f"  {d}: 다글로 파일 없음 (건너뜀)")
            continue

        transcript_text = ""
        if "srt" in daglo_files:
            segments = parse_srt(daglo_files["srt"])
            transcript_text = format_for_notebooklm(segments)
        elif "txt" in daglo_files:
            transcript_text = parse_txt(daglo_files["txt"])

        if not transcript_text:
            logger.warning(f"  {d}: 전사본 비어 있음 (건너뜀)")
            continue

        transcript_path = output_dir / f"전사본_{d}.txt"
        transcript_path.write_text(transcript_text, encoding="utf-8")
        logger.info(f"  전사본: {transcript_path.name} ({len(transcript_text)}자)")

    # 2. 공유 파일 (과목당 1회, 최신으로 갱신)
    context_md = _load_context(cfg, course, dates[-1])
    if context_md:
        (output_dir / "학습컨텍스트.md").write_text(context_md, encoding="utf-8")
        logger.info(f"  학습컨텍스트: 학습컨텍스트.md")
    else:
        logger.warning("  학습컨텍스트: school_sync 데이터 없음 (건너뜀)")

    guide_md = generate_guide(course, dates[-1], cfg)
    (output_dir / "NotebookLM_가이드.md").write_text(guide_md, encoding="utf-8")
    logger.info(f"  가이드: NotebookLM_가이드.md")

    materials_path = cfg.school_sync.downloads_path / cfg.resolve_sync_name(course)
    readme = _build_readme(dates, materials_path, context_md != "")
    (output_dir / "README.txt").write_text(readme, encoding="utf-8")

    logger.info(f"패키지 생성 완료: {output_dir}")

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


def _load_context(cfg: AppConfig, course: str, transcript_date: str = "") -> str:
    """school_sync가 생성한 과목별 학습 컨텍스트 파일을 읽는다.

    daglo 폴더명과 school_sync 과목명이 다를 수 있으므로
    config의 sync_name 매핑을 적용한다.
    transcript_date가 주어지면 freshness 검증도 수행한다.
    """
    sync_name = cfg.resolve_sync_name(course)
    if sync_name != course:
        logger.info(f"  과목명 매핑: {course} -> {sync_name}")
    context_path = cfg.school_sync.context_path / f"{sync_name}.md"
    if not context_path.exists():
        logger.warning(f"학습 컨텍스트 파일 없음: {context_path}")
        logger.info("  -> school_sync에서 정규화를 실행하면 자동 생성됩니다.")
        return ""
    try:
        content = context_path.read_text(encoding="utf-8")
        _validate_context_freshness(content, transcript_date)
        logger.info(f"  학습 컨텍스트 로드: {context_path.name} ({len(content)}자)")
        return content
    except Exception as e:
        logger.warning(f"학습 컨텍스트 읽기 실패: {e}")
        return ""


def _validate_context_freshness(content: str, transcript_date: str):
    """컨텍스트 파일의 YAML frontmatter에서 생성 시점과 기준 날짜를 확인한다."""
    if not transcript_date:
        return

    fm = _parse_frontmatter(content)
    if not fm:
        return

    target = fm.get("target_date", "")
    generated = fm.get("generated_at", "")[:10]

    if target and target != transcript_date:
        logger.warning(
            f"  컨텍스트 기준일 불일치: target_date={target}, 전사본={transcript_date}"
        )
    if generated and generated < transcript_date:
        logger.warning(
            f"  컨텍스트가 전사본보다 이전에 생성됨: generated={generated}, 전사본={transcript_date}"
        )


_FM_PATTERN = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def _parse_frontmatter(content: str) -> dict[str, str]:
    """YAML frontmatter에서 key: value 쌍을 간단히 추출한다."""
    m = _FM_PATTERN.match(content)
    if not m:
        return {}
    result: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip().strip('"')
    return result


def _build_readme(dates: list[str], materials_path: Path, has_context: bool) -> str:
    transcript_list = "\n".join(f"  - 전사본_{d}.txt" for d in dates)

    files = [f"1. 전사본 ({len(dates)}개):\n{transcript_list}"]
    idx = 2
    files.append(f"{idx}. NotebookLM_가이드.md")
    idx += 1
    if has_context:
        files.append(f"{idx}. 학습컨텍스트.md")
        idx += 1

    materials_note = f"   -> {materials_path}" if materials_path.exists() else "   -> (폴더 없음 - school_sync --download 실행 필요)"

    return f"""=== NotebookLM 업로드 안내 ===

이 폴더의 모든 파일을 NotebookLM 노트북에 업로드하세요:

{chr(10).join(files)}

수업자료 PDF/PPT:
{materials_note}

가이드 파일(NotebookLM_가이드.md)을 반드시 소스에 포함하세요.
새 수업 후에는 전사본만 추가하면 됩니다.
"""


def _check_school_sync(cfg: AppConfig, course: str, transcript_date: str) -> bool:
    """school_sync 실행 기록을 확인하고, 필요하면 크롤링 + 컨텍스트 재생성.

    Returns:
        True if context is considered fresh, False otherwise.
    """
    ss_root = Path(cfg.school_sync.root)
    if not cfg.school_sync.root or not ss_root.exists():
        logger.info("school_sync 미설정 또는 경로 없음 (크롤링 체크 건너뜀)")
        return False

    log_path = ss_root / "output" / ".last_run.json"
    needs_crawl = False

    if not log_path.exists():
        logger.warning("school_sync 실행 기록 없음")
        needs_crawl = True
    else:
        try:
            log = json.loads(log_path.read_text(encoding="utf-8"))
            last_run = log.get("last_run", "")[:10]
            if last_run < transcript_date:
                logger.warning(
                    f"school_sync 마지막 실행: {last_run} (전사본 날짜: {transcript_date})"
                )
                needs_crawl = True
            else:
                logger.info(f"school_sync 실행 기록 확인: {last_run} (최신)")
        except Exception as e:
            logger.warning(f"실행 기록 읽기 실패: {e}")
            needs_crawl = True

    if needs_crawl:
        try:
            answer = input("  school_sync 크롤링을 실행할까요? (y/N): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        if answer == "y":
            logger.info("school_sync 크롤링을 실행합니다...")
            try:
                result = subprocess.run(
                    [sys.executable, "main.py", "--download"],
                    cwd=str(ss_root),
                    timeout=300,
                )
                if result.returncode != 0:
                    logger.error(f"school_sync 크롤링 실패 (exit code: {result.returncode})")
                    return False
                logger.info("school_sync 크롤링 완료")
            except subprocess.TimeoutExpired:
                logger.error("school_sync 크롤링 타임아웃 (5분)")
                return False
            except Exception as e:
                logger.error(f"school_sync 실행 실패: {e}")
                return False

    sync_name = cfg.resolve_sync_name(course)
    _regenerate_context(ss_root, sync_name, transcript_date)
    return True


def _regenerate_context(ss_root: Path, course: str, target_date: str):
    """school_sync의 context_export를 호출하여 target_date 기준 컨텍스트를 재생성."""
    try:
        result = subprocess.run(
            [sys.executable, "context_export.py", "--course", course, "--date", target_date],
            cwd=str(ss_root),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30,
        )
        if result.returncode == 0:
            logger.info(f"  컨텍스트 재생성 완료: {course} (기준일: {target_date})")
        else:
            logger.warning(f"  컨텍스트 재생성 실패: {result.stderr[:100] if result.stderr else 'unknown error'}")
    except Exception as e:
        logger.warning(f"  컨텍스트 재생성 실패: {e}")


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
