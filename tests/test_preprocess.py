"""preprocess 모듈 테스트."""
from pathlib import Path

from lesson_assist.preprocess import is_audio, is_video


class TestFileTypeDetection:
    def test_audio_formats(self):
        assert is_audio(Path("lecture.m4a"))
        assert is_audio(Path("lecture.mp3"))
        assert is_audio(Path("lecture.wav"))
        assert is_audio(Path("lecture.flac"))
        assert not is_audio(Path("lecture.mp4"))
        assert not is_audio(Path("lecture.txt"))

    def test_video_formats(self):
        assert is_video(Path("lecture.mp4"))
        assert is_video(Path("lecture.mkv"))
        assert is_video(Path("lecture.webm"))
        assert is_video(Path("lecture.avi"))
        assert not is_video(Path("lecture.m4a"))
        assert not is_video(Path("lecture.txt"))

    def test_case_insensitive(self):
        assert is_audio(Path("lecture.M4A"))
        assert is_video(Path("lecture.MP4"))
