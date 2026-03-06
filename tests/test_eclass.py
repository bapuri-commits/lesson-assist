"""eclass 연동 모듈 테스트."""
import json
import shutil
import tempfile
from pathlib import Path

from lesson_assist.config import EclassConfig
from lesson_assist.eclass import EclassData


def _make_eclass_dir(school_sync_layout: bool = False):
    """테스트용 eclass 데이터 디렉토리 생성."""
    td = Path(tempfile.mkdtemp(prefix="la_eclass_test_"))

    if school_sync_layout:
        courses_dir = td / "raw" / "eclass" / "courses"
        semester_parent = td / "raw" / "eclass"
    else:
        courses_dir = td / "courses"
        semester_parent = td

    courses_dir.mkdir(parents=True)

    course_data = {
        "id": 12345,
        "name": "자료구조(01)",
        "professor": "김교수",
        "syllabus": {
            "1주": "오리엔테이션",
            "2주": "배열과 연결 리스트",
            "3주": "스택과 큐",
            "4주": "트리",
        },
        "boards": {
            "공지사항": {
                "board_id": 1,
                "posts": [
                    {"col_1": "중간고사 안내", "col_3": "2026-04-01"},
                    {"col_1": "과제 제출 안내", "col_3": "2026-03-15"},
                ],
            }
        },
    }
    (courses_dir / "자료구조_01_.json").write_text(
        json.dumps(course_data, ensure_ascii=False), encoding="utf-8"
    )

    semester_data = {
        "semester": "2026-1",
        "calendar_events": [
            {"name": "자료구조 과제 1", "course_name": "자료구조(01)", "time_start": 1711900800},
        ],
    }
    (semester_parent / "2026-1_semester.json").write_text(
        json.dumps(semester_data, ensure_ascii=False), encoding="utf-8"
    )

    return td


class TestEclassData:
    def test_not_available_when_disabled(self):
        cfg = EclassConfig(enabled=False)
        eclass = EclassData(cfg)
        assert not eclass.available

    def test_available_when_configured(self):
        td = _make_eclass_dir()
        try:
            cfg = EclassConfig(
                enabled=True,
                data_dir=str(td),
                course_mapping={"자료구조": "자료구조(01)"},
            )
            eclass = EclassData(cfg)
            assert eclass.available
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_get_recent_notices(self):
        td = _make_eclass_dir()
        try:
            cfg = EclassConfig(
                enabled=True,
                data_dir=str(td),
                course_mapping={"자료구조": "자료구조(01)"},
            )
            eclass = EclassData(cfg)
            notices = eclass.get_recent_notices("자료구조")
            assert len(notices) == 2
            assert notices[0]["title"] == "중간고사 안내"
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_get_calendar_events(self):
        td = _make_eclass_dir()
        try:
            cfg = EclassConfig(
                enabled=True,
                data_dir=str(td),
                course_mapping={"자료구조": "자료구조(01)"},
            )
            eclass = EclassData(cfg)
            events = eclass.get_calendar_events("자료구조")
            assert len(events) == 1
            assert "과제" in events[0]["name"]
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_school_sync_layout(self):
        """school_sync의 raw/eclass/ 경로 구조 지원."""
        td = _make_eclass_dir(school_sync_layout=True)
        try:
            cfg = EclassConfig(
                enabled=True,
                data_dir=str(td),
                course_mapping={"자료구조": "자료구조(01)"},
            )
            eclass = EclassData(cfg)
            assert eclass.available
            notices = eclass.get_recent_notices("자료구조")
            assert len(notices) == 2
            events = eclass.get_calendar_events("자료구조")
            assert len(events) == 1
        finally:
            shutil.rmtree(td, ignore_errors=True)
