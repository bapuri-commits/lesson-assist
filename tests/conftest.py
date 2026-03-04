"""공통 테스트 픽스처."""
from __future__ import annotations

import pytest

from lesson_assist.config import AppConfig, load_config
from lesson_assist.transcribe import Segment, TranscriptResult


@pytest.fixture
def sample_segments() -> list[Segment]:
    """테스트용 세그먼트 목록."""
    return [
        Segment(id=0, start=0.0, end=5.0, text="오늘은 이진 탐색 트리에 대해 알아보겠습니다.", avg_logprob=-0.3, no_speech_prob=0.1),
        Segment(id=1, start=5.0, end=12.0, text="칠판에 그림을 보면 이렇게 노드가 배치되는데요.", avg_logprob=-0.4, no_speech_prob=0.05),
        Segment(id=2, start=12.0, end=20.0, text="여기 이 수식을 보면 높이가 log n이 됩니다.", avg_logprob=-0.35, no_speech_prob=0.08),
        Segment(id=3, start=20.0, end=30.0, text="이걸 표로 정리하면 시간복잡도가 확 보이는데요.", avg_logprob=-0.5, no_speech_prob=0.1),
        Segment(id=4, start=30.0, end=40.0, text="다음 주까지 3장 연습문제 5번 7번 12번 풀어오세요.", avg_logprob=-0.3, no_speech_prob=0.05),
        Segment(id=5, start=40.0, end=50.0, text="중간고사 범위는 1장부터 5장까지입니다.", avg_logprob=-0.25, no_speech_prob=0.03),
        Segment(id=6, start=50.0, end=55.0, text="음", avg_logprob=-0.9, no_speech_prob=0.7),
        Segment(id=7, start=55.0, end=65.0, text="지난 시간에 했던 DFS를 기억하시죠.", avg_logprob=-0.4, no_speech_prob=0.1),
        Segment(id=8, start=65.0, end=80.0, text="슬라이드에 나와있는 것처럼 AVL 트리는 균형을 유지합니다.", avg_logprob=-0.35, no_speech_prob=0.06),
        Segment(id=9, start=80.0, end=90.0, text="이건 시험에 자주 나오니까 꼭 기억하세요.", avg_logprob=-0.3, no_speech_prob=0.04),
    ]


@pytest.fixture
def sample_transcript(sample_segments) -> TranscriptResult:
    """테스트용 전사 결과."""
    return TranscriptResult(
        segments=sample_segments,
        audio_duration=90.0,
        model="large-v3",
        language="ko",
    )


@pytest.fixture
def default_config() -> AppConfig:
    """테스트용 기본 설정."""
    return AppConfig(
        vault_path="",
        output_dir="test_data",
        openai_api_key="test-key",
    )
