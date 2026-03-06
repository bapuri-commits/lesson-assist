"""session 모듈 테스트."""
import shutil
import tempfile
from pathlib import Path

from lesson_assist.session import SessionDir


def _make_temp():
    return Path(tempfile.mkdtemp(prefix="la_session_"))


class TestSessionDir:
    def test_creates_directory(self):
        td = _make_temp()
        try:
            s = SessionDir(td, "자료구조", "2026-03-05")
            assert s.root.exists()
            assert s.root == td / "자료구조" / "2026-03-05"
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_transcript_paths(self):
        td = _make_temp()
        try:
            s = SessionDir(td, "자료구조", "2026-03-05")
            assert s.transcript_raw.name == "transcript_raw.txt"
            assert s.transcript_segments.name == "transcript_segments.json"
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_summary_versioning(self):
        td = _make_temp()
        try:
            s = SessionDir(td, "자료구조", "2026-03-05")

            ver, path = s.next_summary_version()
            assert ver == 1
            assert path.name == "summary_v1.json"

            path.write_text("{}", encoding="utf-8")

            ver2, path2 = s.next_summary_version()
            assert ver2 == 2
            assert path2.name == "summary_v2.json"
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_transcript_revision(self):
        td = _make_temp()
        try:
            s = SessionDir(td, "자료구조", "2026-03-05")

            rev, path = s.next_transcript_revision()
            assert rev == 1
            path.write_text("{}", encoding="utf-8")

            rev2, path2 = s.next_transcript_revision()
            assert rev2 == 2
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_latest_transcript_no_revision(self):
        td = _make_temp()
        try:
            s = SessionDir(td, "자료구조", "2026-03-05")
            assert s.latest_transcript == s.transcript_segments
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_latest_transcript_with_revision(self):
        td = _make_temp()
        try:
            s = SessionDir(td, "자료구조", "2026-03-05")
            r1 = s.transcript_revision(1)
            r1.write_text("{}", encoding="utf-8")
            assert s.latest_transcript == r1
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_materials_roundtrip(self):
        td = _make_temp()
        try:
            s = SessionDir(td, "자료구조", "2026-03-05")

            assert s.load_materials() == []

            fake_file = td / "slide.pptx"
            fake_file.write_text("fake", encoding="utf-8")
            s.save_materials([fake_file])

            loaded = s.load_materials()
            assert len(loaded) == 1
            assert loaded[0].name == "slide.pptx"
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_parts_dir(self):
        td = _make_temp()
        try:
            s = SessionDir(td, "자료구조", "2026-03-05")
            assert s.parts_dir.exists()
            assert s.part_file(1).name == "part_01.txt"
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_subtitle_path(self):
        td = _make_temp()
        try:
            s = SessionDir(td, "자료구조", "2026-03-05")
            assert s.subtitle("srt").name == "subtitle.srt"
            assert s.subtitle("vtt").name == "subtitle.vtt"
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_shared_dirs(self):
        td = _make_temp()
        try:
            s = SessionDir(td, "자료구조", "2026-03-05")
            assert s.rag_dir == td / "_rag"
            assert s.logs_dir == td / "_logs"
            assert s.rag_dir.exists()
            assert s.logs_dir.exists()
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_actions_path(self):
        td = _make_temp()
        try:
            s = SessionDir(td, "자료구조", "2026-03-05")
            assert s.actions(1).name == "actions_v1.json"
            assert s.actions(2).name == "actions_v2.json"
        finally:
            shutil.rmtree(td, ignore_errors=True)
