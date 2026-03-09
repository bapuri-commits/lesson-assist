"""세션 디렉토리 및 버전 관리.

한 강의 세션(과목+날짜)의 모든 산출물 경로를 중앙에서 관리한다.
다른 모듈은 경로를 직접 조립하지 않고 SessionDir에 위임한다.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from loguru import logger


class SessionDir:
    """한 강의 세션(과목+날짜)의 모든 경로를 관리한다."""

    def __init__(self, base_dir: str | Path, course: str, date: str):
        self.base = Path(base_dir)
        self.course = course
        self.date = date
        self.root = self.base / course / date
        self.root.mkdir(parents=True, exist_ok=True)

    # ── 전사 (원본은 불변) ──

    @property
    def transcript_raw(self) -> Path:
        return self.root / "transcript_raw.txt"

    @property
    def transcript_segments(self) -> Path:
        return self.root / "transcript_segments.json"

    def transcript_revision(self, rev: int) -> Path:
        return self.root / f"transcript_segments_r{rev}.json"

    def next_transcript_revision(self) -> tuple[int, Path]:
        existing = sorted(self.root.glob("transcript_segments_r*.json"))
        if not existing:
            rev = 1
        else:
            nums = [int(re.search(r"_r(\d+)", p.stem).group(1)) for p in existing if re.search(r"_r(\d+)", p.stem)]
            rev = max(nums) + 1 if nums else 1
        return rev, self.transcript_revision(rev)

    @property
    def latest_transcript(self) -> Path:
        """최신 전사본 경로: 리비전이 있으면 가장 높은 리비전, 없으면 원본."""
        revisions = sorted(self.root.glob("transcript_segments_r*.json"))
        if revisions:
            return revisions[-1]
        return self.transcript_segments

    # ── 교정 ──

    @property
    def review_file(self) -> Path:
        return self.root / "review.jsonl"

    # ── 파트 ──

    @property
    def parts_dir(self) -> Path:
        d = self.root / "parts"
        d.mkdir(exist_ok=True)
        return d

    def part_file(self, index: int) -> Path:
        return self.parts_dir / f"part_{index:02d}.txt"

    # ── 자막 ──

    def subtitle(self, fmt: str) -> Path:
        return self.root / f"subtitle.{fmt}"

    # ── 요약 버전 ──

    def summary(self, version: int) -> Path:
        return self.root / f"summary_v{version}.json"

    def next_summary_version(self) -> tuple[int, Path]:
        existing = sorted(self.root.glob("summary_v*.json"))
        if not existing:
            ver = 1
        else:
            nums = [int(re.search(r"_v(\d+)", p.stem).group(1)) for p in existing if re.search(r"_v(\d+)", p.stem)]
            ver = max(nums) + 1 if nums else 1
        return ver, self.summary(ver)

    def actions(self, version: int) -> Path:
        return self.root / f"actions_v{version}.json"

    # ── 수업자료 매핑 ──

    @property
    def materials_config(self) -> Path:
        return self.root / "materials.yaml"

    def load_materials(self) -> list[Path]:
        if not self.materials_config.exists():
            return []
        data = yaml.safe_load(self.materials_config.read_text(encoding="utf-8")) or {}
        paths = data.get("materials", [])
        return [Path(p) for p in paths if Path(p).exists()]

    def save_materials(self, paths: list[Path]) -> None:
        data = {"materials": [str(p.resolve()) for p in paths]}
        self.materials_config.write_text(
            yaml.dump(data, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )
        logger.info(f"수업자료 매핑 저장: {self.materials_config} ({len(paths)}개)")

    # ── 공유 디렉토리 (과목/날짜 계층 밖) ──

    @property
    def rag_dir(self) -> Path:
        d = self.base / "_rag"
        d.mkdir(exist_ok=True)
        return d

    @property
    def logs_dir(self) -> Path:
        d = self.base / "_logs"
        d.mkdir(exist_ok=True)
        return d
