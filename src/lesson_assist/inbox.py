"""다글로 inbox 자동 분류 — 파일명에서 과목명/날짜를 감지하여 정리한다."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from loguru import logger

from .config import AppConfig


def _get_known_courses(cfg: AppConfig) -> list[str]:
    """config + school_sync courses.json에서 알려진 과목명 목록을 수집한다."""
    courses: set[str] = set(cfg.courses.keys())

    ss_root = Path(cfg.school_sync.root)
    courses_json = ss_root / "output" / "normalized" / "academics" / "courses.json"
    if courses_json.exists():
        try:
            data = json.loads(courses_json.read_text(encoding="utf-8"))
            for c in data:
                name = c.get("short_name", c.get("name", ""))
                if name:
                    courses.add(name)
        except Exception:
            pass

    return sorted(courses, key=len, reverse=True)


def _detect_course(filename: str, known_courses: list[str]) -> str | None:
    """파일명에서 과목명을 감지한다."""
    stem = Path(filename).stem
    for course in known_courses:
        if course in stem:
            return course
    return None


def _detect_date(filename: str) -> str | None:
    """파일명에서 YYYY-MM-DD 또는 YYYYMMDD 형식의 날짜를 추출한다."""
    stem = Path(filename).stem

    m = re.search(r"(\d{4}-\d{2}-\d{2})", stem)
    if m:
        return m.group(1)

    m = re.search(r"(\d{4})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])", stem)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    m = re.search(r"(2[0-9])(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])", stem)
    if m:
        return f"20{m.group(1)}-{m.group(2)}-{m.group(3)}"

    return None


def _ask_user(prompt: str) -> str:
    """CLI에서 사용자 입력을 받는다."""
    try:
        return input(f"  {prompt}: ").strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def process_inbox(cfg: AppConfig) -> list[dict]:
    """inbox 폴더의 파일들을 과목별 폴더로 분류한다.

    Returns:
        분류 결과 리스트 [{"file": "원본.srt", "course": "과목명", "date": "2026-03-10", "dest": Path}]
    """
    inbox_dir = Path(cfg.daglo.input_dir) / "inbox"
    if not inbox_dir.exists():
        inbox_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"inbox 폴더 생성: {inbox_dir}")
        return []

    files = [f for f in inbox_dir.iterdir()
             if f.is_file() and f.suffix.lower() in (".srt", ".txt")
             and not f.name.startswith(".")]

    if not files:
        logger.info("inbox에 처리할 파일이 없습니다.")
        return []

    known_courses = _get_known_courses(cfg)
    logger.info(f"inbox: {len(files)}개 파일 발견 (알려진 과목: {len(known_courses)}개)")

    if known_courses:
        logger.info(f"  과목 목록: {', '.join(known_courses)}")

    results: list[dict] = []

    for file in sorted(files):
        logger.info(f"\n--- {file.name} ---")

        course = _detect_course(file.name, known_courses)
        if course:
            logger.info(f"  과목 감지: {course}")
        else:
            logger.warning(f"  과목 감지 실패: {file.name}")
            if known_courses:
                print(f"\n  알려진 과목: {', '.join(known_courses)}")
            course = _ask_user("과목명을 입력하세요 (건너뛰려면 Enter)")
            if not course:
                logger.info("  건너뜀")
                continue

        date = _detect_date(file.name)
        if date:
            logger.info(f"  날짜 감지: {date}")
        else:
            logger.warning(f"  날짜 감지 실패: {file.name}")
            date = _ask_user("날짜를 입력하세요 (YYYY-MM-DD, 건너뛰려면 Enter)")
            if not date:
                logger.info("  건너뜀")
                continue
            if not re.match(r"\d{4}-\d{2}-\d{2}$", date):
                logger.error(f"  잘못된 날짜 형식: {date}")
                continue

        dest_dir = Path(cfg.daglo.input_dir) / course
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{date}{file.suffix.lower()}"

        if dest.exists():
            logger.warning(f"  이미 존재: {dest} (덮어쓰기)")

        shutil.move(str(file), str(dest))
        logger.info(f"  이동: {file.name} -> {course}/{dest.name}")

        results.append({
            "file": file.name,
            "course": course,
            "date": date,
            "dest": dest,
        })

    if results:
        logger.info(f"\ninbox 분류 완료: {len(results)}개 파일 처리")
    return results
