"""school_sync 정규화 데이터에서 과목별 학습 컨텍스트를 생성한다."""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

from loguru import logger

from .config import SchoolSyncConfig


def build_context(school_sync: SchoolSyncConfig, course: str) -> str:
    """특정 과목의 학습 컨텍스트 마크다운을 생성한다.

    포함: 강의계획서, 과제/마감, 공지사항 (학습 관련만)
    제외: 성적, 출석, 학교 행사 (학사 관리는 ask.py 영역)
    """
    norm_dir = school_sync.normalized_dir
    if not norm_dir.exists():
        logger.warning(f"school_sync normalized 디렉토리 없음: {norm_dir}")
        return ""

    sections: list[str] = []

    syllabus_md = _build_syllabus_section(norm_dir, course)
    if syllabus_md:
        sections.append(syllabus_md)

    assignments_md = _build_assignments_section(norm_dir, course)
    if assignments_md:
        sections.append(assignments_md)

    notices_md = _build_notices_section(norm_dir, course)
    if notices_md:
        sections.append(notices_md)

    if not sections:
        logger.warning(f"과목 '{course}'에 대한 학습 컨텍스트 데이터 없음")
        return ""

    header = f"# {course} 학습 컨텍스트\n\n> school_sync에서 자동 생성됨\n"
    return header + "\n---\n\n".join(sections)


def _load_json(path: Path) -> list | dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"JSON 로드 실패 ({path.name}): {e}")
        return None


def _build_syllabus_section(norm_dir: Path, course: str) -> str:
    data = _load_json(norm_dir / "academics" / "syllabus.json")
    if not data or not isinstance(data, list):
        return ""

    course_syl = [s for s in data if s.get("course_name", "") == course]
    if not course_syl:
        short_match = [s for s in data if course in s.get("course_name", "")]
        course_syl = short_match

    if not course_syl:
        return ""

    lines = ["## 강의계획서\n"]
    for entry in course_syl:
        fields = entry.get("fields", {})
        if not fields:
            continue

        for key, value in fields.items():
            if not value or value.strip() == "-":
                continue
            lines.append(f"### {key}\n")
            lines.append(f"{value}\n")

    return "\n".join(lines) if len(lines) > 1 else ""


def _build_assignments_section(norm_dir: Path, course: str) -> str:
    sections: list[str] = []

    assignments = _load_json(norm_dir / "academics" / "assignments.json")
    if assignments and isinstance(assignments, list):
        course_assignments = [a for a in assignments
                              if course in a.get("course_name", "")]
        if course_assignments:
            lines = ["## 과제/활동\n"]
            for a in course_assignments:
                deadline = a.get("deadline", "")
                deadline_str = f" (마감: {deadline})" if deadline else ""
                lines.append(f"- **{a.get('title', '?')}**{deadline_str}")
                if a.get("info"):
                    lines.append(f"  - {a['info']}")
            sections.append("\n".join(lines))

    deadlines = _load_json(norm_dir / "academics" / "deadlines.json")
    if deadlines and isinstance(deadlines, list):
        course_deadlines = [d for d in deadlines
                            if course in d.get("course_name", "")]
        if course_deadlines:
            lines = ["## 마감 일정\n"]
            for d in course_deadlines:
                lines.append(f"- {d.get('due_at', '?')} | {d.get('title', '?')} ({d.get('source', '')})")
            sections.append("\n".join(lines))

    return "\n\n".join(sections)


def _build_notices_section(norm_dir: Path, course: str) -> str:
    data = _load_json(norm_dir / "info" / "notices.json")
    if not data or not isinstance(data, list):
        return ""

    two_weeks_ago = (date.today() - timedelta(days=14)).isoformat()
    course_notices = [
        n for n in data
        if course in n.get("course_name", "")
        and n.get("date", "") >= two_weeks_ago
    ]

    if not course_notices:
        return ""

    lines = ["## 최근 공지사항\n"]
    for n in course_notices[:10]:
        lines.append(f"- [{n.get('date', '')}] **{n.get('title', '?')}**")
        if n.get("board_name"):
            lines.append(f"  - 게시판: {n['board_name']}")

    return "\n".join(lines)


def get_week_topic(school_sync: SchoolSyncConfig, course: str, target_date: str) -> tuple[int, str] | None:
    """강의계획서에서 날짜에 해당하는 주차와 토픽을 조회한다.

    Returns:
        (week_number, topic) 또는 None
    """
    norm_dir = school_sync.normalized_dir
    data = _load_json(norm_dir / "academics" / "syllabus.json")
    if not data or not isinstance(data, list):
        return None

    course_syl = [s for s in data if course in s.get("course_name", "")]
    if not course_syl:
        return None

    for entry in course_syl:
        fields = entry.get("fields", {})
        for key, value in fields.items():
            m = re.match(r"(\d{1,2})주차", key)
            if m:
                week = int(m.group(1))
                return (week, value.strip())

    return None
