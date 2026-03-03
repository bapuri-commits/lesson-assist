from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class TranscribeConfig:
    model: str = "large-v3"
    language: str = "ko"
    device: str = "cuda"
    compute_type: str = "float16"
    beam_size: int = 5
    vad_filter: bool = True


@dataclass
class ReviewConfig:
    logprob_threshold: float = -0.7
    no_speech_threshold: float = 0.5
    min_segment_chars: int = 2
    max_repeat_count: int = 3


@dataclass
class SegmentConfig:
    part_minutes: int = 25
    min_part_minutes: int = 5


@dataclass
class SummarizeConfig:
    model: str = "gpt-4o"
    temperature: float = 0.3
    max_retries: int = 3


@dataclass
class AppConfig:
    vault_path: str = ""
    output_dir: str = "data"
    openai_api_key: str = ""
    transcribe: TranscribeConfig = field(default_factory=TranscribeConfig)
    review: ReviewConfig = field(default_factory=ReviewConfig)
    segment: SegmentConfig = field(default_factory=SegmentConfig)
    summarize: SummarizeConfig = field(default_factory=SummarizeConfig)


def load_config(config_path: str | None = None) -> AppConfig:
    """config.yaml + 환경변수를 합쳐서 AppConfig를 반환한다."""
    raw: dict = {}
    if config_path:
        p = Path(config_path)
    else:
        candidates = [Path("config.yaml"), Path(__file__).resolve().parents[2] / "config.yaml"]
        p = next((c for c in candidates if c.exists()), None)

    if p and p.exists():
        with open(p, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

    cfg = AppConfig(
        vault_path=raw.get("vault_path", ""),
        output_dir=raw.get("output_dir", "data"),
        openai_api_key=os.environ.get("OPENAI_API_KEY", "") or raw.get("openai_api_key", ""),
    )

    if tc := raw.get("transcribe"):
        cfg.transcribe = TranscribeConfig(**{k: v for k, v in tc.items() if k in TranscribeConfig.__dataclass_fields__})
    if rc := raw.get("review"):
        cfg.review = ReviewConfig(**{k: v for k, v in rc.items() if k in ReviewConfig.__dataclass_fields__})
    if sc := raw.get("segment"):
        cfg.segment = SegmentConfig(**{k: v for k, v in sc.items() if k in SegmentConfig.__dataclass_fields__})
    if sm := raw.get("summarize"):
        cfg.summarize = SummarizeConfig(**{k: v for k, v in sm.items() if k in SummarizeConfig.__dataclass_fields__})

    return cfg
