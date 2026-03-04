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
class AnchorsConfig:
    """Visual Anchors 탐지 설정."""
    keywords: list[str] = field(default_factory=lambda: [
        "칠판", "판서", "보면", "그림", "수식", "도표",
        "이렇게", "슬라이드", "다이어그램",
        "그래프", "화면", "PPT", "피피티", "프레젠테이션",
        "여기 보면", "이거 보면", "저기 보면", "화면에",
    ])
    context_seconds: float = 30.0
    merge_gap_seconds: float = 15.0


@dataclass
class RAGConfig:
    """강의 컨텍스트 RAG 설정."""
    enabled: bool = True
    db_path: str = "data/chroma_db"
    embedding_model: str = "text-embedding-3-small"
    top_k: int = 5
    chunk_size: int = 500
    chunk_overlap: int = 50


@dataclass
class EclassConfig:
    """eclass_crawler 연동 설정."""
    enabled: bool = False
    data_dir: str = ""
    course_mapping: dict[str, str] = field(default_factory=dict)


@dataclass
class ExamSheetConfig:
    """시험 대비 A4 생성 설정."""
    model: str = "gpt-4o"
    temperature: float = 0.2
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
    anchors: AnchorsConfig = field(default_factory=AnchorsConfig)
    rag: RAGConfig = field(default_factory=RAGConfig)
    eclass: EclassConfig = field(default_factory=EclassConfig)
    exam_sheet: ExamSheetConfig = field(default_factory=ExamSheetConfig)


def _build_dataclass(cls, raw: dict):
    """dataclass에 정의된 필드만 골라서 인스턴스를 생성한다."""
    return cls(**{k: v for k, v in raw.items() if k in cls.__dataclass_fields__})


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
        cfg.transcribe = _build_dataclass(TranscribeConfig, tc)
    if rc := raw.get("review"):
        cfg.review = _build_dataclass(ReviewConfig, rc)
    if sc := raw.get("segment"):
        cfg.segment = _build_dataclass(SegmentConfig, sc)
    if sm := raw.get("summarize"):
        cfg.summarize = _build_dataclass(SummarizeConfig, sm)
    if ac := raw.get("anchors"):
        cfg.anchors = _build_dataclass(AnchorsConfig, ac)
    if rg := raw.get("rag"):
        cfg.rag = _build_dataclass(RAGConfig, rg)
    if ec := raw.get("eclass"):
        cfg.eclass = _build_dataclass(EclassConfig, ec)
    if es := raw.get("exam_sheet"):
        cfg.exam_sheet = _build_dataclass(ExamSheetConfig, es)

    return cfg
