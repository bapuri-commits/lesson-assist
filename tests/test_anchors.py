"""anchors 모듈 테스트."""
from lesson_assist.anchors import AnchorCandidate, attach_image, detect_anchors
from lesson_assist.config import AnchorsConfig


class TestDetectAnchors:
    def test_detects_visual_keywords(self, sample_transcript):
        cfg = AnchorsConfig()
        result = detect_anchors(sample_transcript, cfg, "자료구조", "2026-03-03")
        keywords_found = set()
        for c in result.candidates:
            keywords_found.update(c.matched_keywords)
        assert "칠판" in keywords_found or "그림" in keywords_found
        assert "수식" in keywords_found or "여기" in keywords_found or "표" in keywords_found

    def test_merge_nearby(self, sample_transcript):
        cfg = AnchorsConfig(merge_gap_seconds=15.0)
        result = detect_anchors(sample_transcript, cfg, "자료구조", "2026-03-03")
        timestamps = [c.timestamp for c in result.candidates]
        for i in range(1, len(timestamps)):
            assert timestamps[i] - timestamps[i - 1] >= 5.0

    def test_context_text_populated(self, sample_transcript):
        cfg = AnchorsConfig()
        result = detect_anchors(sample_transcript, cfg, "자료구조", "2026-03-03")
        for c in result.candidates:
            assert len(c.context_text) > 0

    def test_to_markdown(self, sample_transcript):
        cfg = AnchorsConfig()
        result = detect_anchors(sample_transcript, cfg, "자료구조", "2026-03-03")
        md = result.to_markdown_section()
        assert "## Visual Anchors" in md
        assert "- [ ]" in md

    def test_empty_when_no_keywords(self):
        from lesson_assist.transcribe import Segment, TranscriptResult
        transcript = TranscriptResult(
            segments=[
                Segment(id=0, start=0.0, end=10.0, text="일반적인 텍스트입니다.", avg_logprob=-0.3, no_speech_prob=0.1),
            ],
            audio_duration=10.0,
            model="large-v3",
            language="ko",
        )
        cfg = AnchorsConfig()
        result = detect_anchors(transcript, cfg, "과목", "2026-03-03")
        assert len(result.candidates) == 0
        assert result.to_markdown_section() == ""


class TestAttachImage:
    def test_attach_to_nearest(self, sample_transcript):
        cfg = AnchorsConfig()
        result = detect_anchors(sample_transcript, cfg, "자료구조", "2026-03-03")
        if result.candidates:
            ts = result.candidates[0].timestamp
            success = attach_image(result, "photo.jpg", ts + 5.0)
            assert success
            assert result.candidates[0].image_path == "photo.jpg"

    def test_fail_when_too_far(self, sample_transcript):
        cfg = AnchorsConfig()
        result = detect_anchors(sample_transcript, cfg, "자료구조", "2026-03-03")
        if result.candidates:
            success = attach_image(result, "photo.jpg", 9999.0, tolerance_seconds=10.0)
            assert not success
