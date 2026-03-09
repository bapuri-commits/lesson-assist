"""lesson-assist v2 설정."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class SchoolSyncConfig:
    root: str = ""
    context_dir: str = "output/context"
    downloads_dir: str = "output/downloads"

    @property
    def context_path(self) -> Path:
        return Path(self.root) / self.context_dir

    @property
    def downloads_path(self) -> Path:
        return Path(self.root) / self.downloads_dir


@dataclass
class DagloConfig:
    input_dir: str = "input/daglo"


@dataclass
class NotebookLMConfig:
    output_dir: str = "output/notebooklm"
    auto_open: bool = True
    guide_extras: dict[str, str] = field(default_factory=dict)


@dataclass
class FromNotebookLMConfig:
    input_dir: str = "input/from_notebooklm"


@dataclass
class ObsidianConfig:
    vault_path: str = ""
    lecture_dir: str = "3_Areas/Lectures"
    daily_dir: str = "1_Daily"


@dataclass
class CourseConfig:
    guide_extra: str = ""


@dataclass
class AppConfig:
    school_sync: SchoolSyncConfig = field(default_factory=SchoolSyncConfig)
    daglo: DagloConfig = field(default_factory=DagloConfig)
    notebooklm: NotebookLMConfig = field(default_factory=NotebookLMConfig)
    from_notebooklm: FromNotebookLMConfig = field(default_factory=FromNotebookLMConfig)
    obsidian: ObsidianConfig = field(default_factory=ObsidianConfig)
    courses: dict[str, CourseConfig] = field(default_factory=dict)

    def get_course_config(self, course: str) -> CourseConfig:
        return self.courses.get(course, CourseConfig())


def _build_dataclass(cls, raw: dict):
    return cls(**{k: v for k, v in raw.items() if k in cls.__dataclass_fields__})


def load_config(config_path: str | None = None) -> AppConfig:
    raw: dict = {}
    if config_path:
        p = Path(config_path)
    else:
        candidates = [
            Path("config.yaml"),
            Path(__file__).resolve().parents[2] / "config.yaml",
        ]
        p = next((c for c in candidates if c.exists()), None)

    if p and p.exists():
        with open(p, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

    cfg = AppConfig()

    if ss := raw.get("school_sync"):
        cfg.school_sync = _build_dataclass(SchoolSyncConfig, ss)
    if dg := raw.get("daglo"):
        cfg.daglo = _build_dataclass(DagloConfig, dg)
    if nlm := raw.get("notebooklm"):
        cfg.notebooklm = _build_dataclass(NotebookLMConfig, nlm)
    if fnlm := raw.get("from_notebooklm"):
        cfg.from_notebooklm = _build_dataclass(FromNotebookLMConfig, fnlm)
    if obs := raw.get("obsidian"):
        cfg.obsidian = _build_dataclass(ObsidianConfig, obs)
    if courses := raw.get("courses"):
        for name, course_raw in courses.items():
            if isinstance(course_raw, dict):
                cfg.courses[name] = _build_dataclass(CourseConfig, course_raw)

    return cfg
