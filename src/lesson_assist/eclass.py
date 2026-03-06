"""eclass_crawler 데이터 연동 레이어.

eclass_crawler가 생성한 JSON 데이터를 읽어서
lesson-assist 파이프라인에 활용할 수 있는 형태로 제공한다.

연동 포인트:
1. 실라버스 주차 매칭 → 요약 프롬프트에 주제 주입
2. 다운로드한 강의자료 경로 → RAG 컨텍스트
3. 캘린더 이벤트 → 액션 아이템 교차검증
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

from .config import EclassConfig


class EclassData:
    """eclass_crawler 출력 데이터를 로드하고 쿼리하는 인터페이스."""

    def __init__(self, cfg: EclassConfig):
        self.cfg = cfg
        self._semester_data: dict | None = None
        self._course_data: dict[str, dict] = {}

    @property
    def available(self) -> bool:
        return bool(self.cfg.enabled and self.cfg.data_dir and Path(self.cfg.data_dir).exists())

    def _find_semester_json(self) -> Path | None:
        data_dir = Path(self.cfg.data_dir)
        # school_sync: raw/eclass/*_semester.json
        eclass_dir = data_dir / "raw" / "eclass"
        if eclass_dir.exists():
            candidates = sorted(eclass_dir.glob("*_semester.json"), reverse=True)
            if candidates:
                return candidates[0]
        # 레거시 fallback: data_dir/*_semester.json
        candidates = sorted(data_dir.glob("*_semester.json"), reverse=True)
        return candidates[0] if candidates else None

    def _load_semester(self) -> dict:
        if self._semester_data is not None:
            return self._semester_data

        sem_path = self._find_semester_json()
        if not sem_path:
            logger.warning(f"eclass 학기 데이터 없음: {self.cfg.data_dir}")
            self._semester_data = {}
            return self._semester_data

        self._semester_data = json.loads(sem_path.read_text(encoding="utf-8"))
        logger.info(f"eclass 학기 데이터 로드: {sem_path.name}")
        return self._semester_data

    def _load_course(self, course_name: str) -> dict:
        if course_name in self._course_data:
            return self._course_data[course_name]

        mapped = self.cfg.course_mapping.get(course_name, course_name)

        # school_sync: raw/eclass/courses/*.json, 레거시: courses/*.json
        courses_dir = Path(self.cfg.data_dir) / "raw" / "eclass" / "courses"
        if not courses_dir.exists():
            courses_dir = Path(self.cfg.data_dir) / "courses"
        if not courses_dir.exists():
            return {}

        for p in courses_dir.glob("*.json"):
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("name", "") == mapped or mapped in p.stem:
                self._course_data[course_name] = data
                return data

        return {}

    def get_week_topic(self, course: str, date: str) -> str | None:
        """날짜 기반으로 실라버스에서 해당 주차 주제를 찾는다."""
        course_data = self._load_course(course)
        syllabus = course_data.get("syllabus", {})
        if not syllabus:
            return None

        try:
            lecture_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return None

        # 실라버스의 주차별 계획에서 해당 날짜에 맞는 주차를 찾는다
        # 학기 시작일 기반으로 주차 계산
        week_plans = {}
        for key, value in syllabus.items():
            if "주" in key and isinstance(value, str):
                try:
                    week_num = int("".join(c for c in key if c.isdigit()))
                    week_plans[week_num] = value
                except ValueError:
                    continue

        if not week_plans:
            return None

        year = lecture_date.year
        if lecture_date.month >= 8:
            # 2학기: 9월 첫째 주 월요일 기준
            semester_start = datetime(year, 9, 1)
        else:
            # 1학기: 3월 첫째 주 월요일 기준
            semester_start = datetime(year, 3, 1)
        while semester_start.weekday() != 0:
            semester_start += timedelta(days=1)

        week_num = ((lecture_date - semester_start).days // 7) + 1
        if week_num < 1:
            return None
        topic = week_plans.get(week_num)

        if topic:
            logger.info(f"eclass 주차 매칭: {course} {date} → {week_num}주차: {topic}")
        return topic

    def get_calendar_events(self, course: str | None = None) -> list[dict]:
        """캘린더 이벤트(과제 마감, 시험 등)를 반환한다."""
        semester = self._load_semester()
        events = semester.get("calendar_events", [])

        if course:
            mapped = self.cfg.course_mapping.get(course, course)
            events = [e for e in events if mapped in e.get("course_name", "")]

        return events

    def get_downloaded_materials(self, course: str) -> list[Path]:
        """과목의 다운로드된 강의자료 경로 목록을 반환한다."""
        mapped = self.cfg.course_mapping.get(course, course)
        downloads_dir = Path(self.cfg.data_dir) / "downloads"
        if not downloads_dir.exists():
            return []

        course_dir = None
        for d in downloads_dir.iterdir():
            if d.is_dir() and (mapped in d.name or d.name == mapped):
                course_dir = d
                break

        if not course_dir:
            return []

        materials = list(course_dir.glob("*"))
        logger.debug(f"eclass 자료: {course} → {len(materials)}개 파일")
        return materials

    def get_recent_notices(self, course: str, limit: int = 5) -> list[dict]:
        """과목의 최근 게시판 공지를 반환한다."""
        course_data = self._load_course(course)
        boards = course_data.get("boards", {})

        notices: list[dict] = []
        for board_name, board_data in boards.items():
            posts = board_data.get("posts", [])
            for post in posts[:limit]:
                notices.append({
                    "board": board_name,
                    "title": post.get("제목", post.get("title", post.get("col_1", ""))),
                    "date": post.get("작성일", post.get("date", post.get("col_3", ""))),
                    "author": post.get("작성자", post.get("author", "")),
                    "link": post.get("_link", ""),
                })

        return notices[:limit]
