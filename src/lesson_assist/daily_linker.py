"""The Record 데일리 노트와 강의 노트를 연동한다.

데일리 노트 경로: {vault}/1_Daily/YYYY-MM/YYYY-MM-DD.md
템플릿: {vault}/Templates/daily.md
"""
from __future__ import annotations

import re
from pathlib import Path

from loguru import logger

from .actions import ActionsResult


def link_to_daily(
    vault_path: str,
    course: str,
    date: str,
    summary_oneliner: str,
    actions: ActionsResult,
) -> Path | None:
    """데일리 노트에 강의 요약 링크와 액션 아이템을 삽입한다."""
    vault = Path(vault_path)
    year_month = date[:7]  # YYYY-MM
    daily_dir = vault / "1_Daily" / year_month
    daily_path = daily_dir / f"{date}.md"

    if not daily_path.exists():
        daily_path = _create_daily_note(vault, daily_dir, daily_path, date)
        if daily_path is None:
            logger.warning(f"데일리 노트 생성 실패: {date}")
            return None

    content = daily_path.read_text(encoding="utf-8")

    note_link = f"[[{date}_{course}|{course}]]"
    duplicate_marker = f"{date}_{course}"
    if duplicate_marker in content:
        logger.info(f"데일리 노트에 이미 {course} 링크 존재, 스킵")
        return daily_path

    # 공부 기록 섹션에 강의 링크 추가
    study_entry = f"- 📖 {note_link} — {summary_oneliner}"
    content = _insert_under_section(content, "## 공부 기록", study_entry)

    # 액션 아이템 → Todo / 일정 섹션
    for item in actions.items:
        if item.type in ("과제", "공지"):
            deadline_str = f" (마감: {item.deadline})" if item.deadline else ""
            todo_entry = f"- [ ] {course} {item.content}{deadline_str}"
            content = _insert_under_section(content, "## Todo", todo_entry)
        elif item.type in ("시험", "일정"):
            date_str = item.deadline or "미정"
            schedule_entry = f"| {date_str} | {course} {item.content} |"
            content = _insert_under_section(content, "## 일정", schedule_entry)

    daily_path.write_text(content, encoding="utf-8")
    logger.info(f"데일리 노트 연동 완료: {daily_path}")
    return daily_path


def _insert_under_section(content: str, section_header: str, entry: str) -> str:
    """마크다운 섹션 헤더 바로 아래에 엔트리를 삽입한다."""
    lines = content.split("\n")
    insert_idx = None

    for i, line in enumerate(lines):
        if line.strip() == section_header:
            insert_idx = i + 1
            # 빈 줄 건너뛰기
            while insert_idx < len(lines) and lines[insert_idx].strip() == "":
                insert_idx += 1
            break

    if insert_idx is None:
        # 섹션이 없으면 파일 끝에 추가
        lines.append("")
        lines.append(section_header)
        lines.append(entry)
    else:
        lines.insert(insert_idx, entry)

    return "\n".join(lines)


def _create_daily_note(vault: Path, daily_dir: Path, daily_path: Path, date: str) -> Path | None:
    """Templates/daily.md를 기반으로 데일리 노트를 생성한다."""
    template_path = vault / "Templates" / "daily.md"
    if not template_path.exists():
        logger.warning(f"데일리 템플릿 없음: {template_path}")
        return _create_minimal_daily(daily_dir, daily_path, date)

    template = template_path.read_text(encoding="utf-8")

    # Templater 문법 치환
    content = template
    content = re.sub(r"<%\s*tp\.date\.now\(['\"]([^'\"]+)['\"]\)\s*%>", date, content)
    content = re.sub(r"<%\s*tp\.file\.cursor\(\)\s*%>", "", content)
    # 월 표시용
    content = content.replace("<% tp.date.now('YYYY-MM') %>", date[:7])
    content = content.replace("<% tp.date.now('YYYY') %>", date[:4])

    daily_dir.mkdir(parents=True, exist_ok=True)
    daily_path.write_text(content, encoding="utf-8")
    logger.info(f"데일리 노트 생성: {daily_path}")
    return daily_path


def _create_minimal_daily(daily_dir: Path, daily_path: Path, date: str) -> Path:
    """템플릿 없이 최소한의 데일리 노트를 생성한다."""
    daily_dir.mkdir(parents=True, exist_ok=True)
    content = f"""---
date: {date}
tags: [daily]
---

# {date}

## Todo

## 일정

| 날짜 | 내용 |
|------|------|

## 개발 로그

## 공부 기록

## 메모
"""
    daily_path.write_text(content, encoding="utf-8")
    logger.info(f"최소 데일리 노트 생성: {daily_path}")
    return daily_path
