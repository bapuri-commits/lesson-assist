"""다글로 SRT/TXT 파싱 및 정제."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from loguru import logger


@dataclass
class SrtSegment:
    index: int
    start: str      # "00:01:23,456"
    end: str        # "00:01:25,789"
    text: str

    @property
    def start_simple(self) -> str:
        """HH:MM:SS 형식 (밀리초 제거)."""
        return self.start.split(",")[0]


_TIMESTAMP_RE = re.compile(
    r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})"
)


def parse_srt(path: Path) -> list[SrtSegment]:
    """SRT 파일을 파싱하여 세그먼트 리스트로 반환한다."""
    text = path.read_text(encoding="utf-8-sig")
    blocks = re.split(r"\n\s*\n", text.strip())
    segments: list[SrtSegment] = []

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 2:
            continue

        ts_match = None
        text_start_idx = 0
        for i, line in enumerate(lines):
            m = _TIMESTAMP_RE.search(line)
            if m:
                ts_match = m
                text_start_idx = i + 1
                break

        if not ts_match:
            continue

        seg_text = " ".join(lines[text_start_idx:]).strip()
        if not seg_text:
            continue

        segments.append(SrtSegment(
            index=len(segments) + 1,
            start=ts_match.group(1).replace(".", ","),
            end=ts_match.group(2).replace(".", ","),
            text=seg_text,
        ))

    logger.info(f"SRT 파싱: {path.name} -> {len(segments)}개 세그먼트")
    return segments


def parse_txt(path: Path) -> str:
    """TXT 파일을 읽어 정제된 텍스트로 반환한다."""
    text = path.read_text(encoding="utf-8-sig").strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    logger.info(f"TXT 로드: {path.name} -> {len(text)}자")
    return text


def _merge_short_segments(segments: list[SrtSegment], min_chars: int = 10) -> list[SrtSegment]:
    """짧은 세그먼트를 이전 세그먼트에 병합한다."""
    if not segments:
        return segments

    merged: list[SrtSegment] = [segments[0]]
    for seg in segments[1:]:
        prev = merged[-1]
        if len(prev.text) < min_chars:
            merged[-1] = SrtSegment(
                index=prev.index,
                start=prev.start,
                end=seg.end,
                text=f"{prev.text} {seg.text}",
            )
        else:
            merged.append(seg)

    return merged


def format_for_notebooklm(segments: list[SrtSegment]) -> str:
    """SRT 세그먼트를 NotebookLM 최적화 텍스트로 변환한다.

    타임스탬프를 유지하여 시간대별 참조 가능하도록 한다.
    """
    segments = _merge_short_segments(segments)
    lines: list[str] = []
    for seg in segments:
        lines.append(f"[{seg.start_simple}] {seg.text}")
    return "\n".join(lines)


def find_daglo_files(daglo_dir: Path, course: str, date: str | None = None) -> dict[str, Path]:
    """다글로 입력 폴더에서 과목/날짜에 맞는 파일을 찾는다.

    Returns:
        {"srt": Path, "txt": Path} — 존재하는 파일만 포함
    """
    course_dir = daglo_dir / course
    if not course_dir.exists():
        return {}

    result: dict[str, Path] = {}

    if date:
        srt = course_dir / f"{date}.srt"
        txt = course_dir / f"{date}.txt"
        if srt.exists():
            result["srt"] = srt
        if txt.exists():
            result["txt"] = txt
    else:
        srts = sorted(course_dir.glob("*.srt"), reverse=True)
        txts = sorted(course_dir.glob("*.txt"), reverse=True)
        if srts:
            result["srt"] = srts[0]
        if txts:
            result["txt"] = txts[0]

    return result


def extract_date_from_filename(path: Path) -> str | None:
    """파일명에서 YYYY-MM-DD 날짜를 추출한다."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", path.stem)
    return m.group(1) if m else None
