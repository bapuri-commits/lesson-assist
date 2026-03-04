"""eclass 연동 모듈 테스트."""
import json
import shutil
import tempfile
from pathlib import Path

from lesson_assist.config import EclassConfig
from lesson_assist.eclass import EclassData


def _make_eclass_dir():
    """테스트용 eclass 데이터 디렉토리 생성."""
    td = Path(tempfile.mkdtemp(prefix="la_eclass_test_"))

    courses_dir = td / "courses"
    courses_dir.mkdir()

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
    (td / "2026-1_semester.json").write_text(
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
