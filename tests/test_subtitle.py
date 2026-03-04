"""subtitle 모듈 테스트."""
from lesson_assist.subtitle import generate_srt, generate_vtt


class TestGenerateSRT:
    def test_basic_output(self, sample_transcript):
        srt = generate_srt(sample_transcript)
        lines = srt.strip().split("\n")
        assert lines[0] == "1"
        assert "-->" in lines[1]
        assert "이진 탐색 트리" in lines[2]

    def test_time_format(self, sample_transcript):
        srt = generate_srt(sample_transcript)
        assert "00:00:00,000 --> 00:00:05,000" in srt

    def test_empty_segments_skipped(self, sample_transcript):
        sample_transcript.segments[0].text = "   "
        srt = generate_srt(sample_transcript)
        lines = srt.strip().split("\n")
        assert lines[0] == "1"
        assert "칠판" in srt

    def test_all_segments_present(self, sample_transcript):
        srt = generate_srt(sample_transcript)
        non_empty = [s for s in sample_transcript.segments if s.text.strip()]
        count = srt.count("-->")
        assert count == len(non_empty)


class TestGenerateVTT:
    def test_header(self, sample_transcript):
        vtt = generate_vtt(sample_transcript)
        assert vtt.startswith("WEBVTT")

    def test_dot_separator(self, sample_transcript):
        vtt = generate_vtt(sample_transcript)
        assert "00:00:00.000 --> 00:00:05.000" in vtt

    def test_content_matches_srt(self, sample_transcript):
        srt = generate_srt(sample_transcript)
        vtt = generate_vtt(sample_transcript)
        srt_count = srt.count("-->")
        vtt_count = vtt.count("-->")
        assert srt_count == vtt_count
