"""Visual Anchors — 시각 자료 의존 구간 탐지.

전사 텍스트에서 판서/슬라이드/그림 등 시각 자료에 의존하는 구간을 자동 탐지하고,
앵커 체크리스트를 생성한다. Phase 3에서 이미지 반자동 연결에 사용.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from loguru import logger

from .config import AnchorsConfig
from .transcribe import Segment, TranscriptResult


@dataclass
class AnchorCandidate:
    """시각 자료 의존 구간 하나."""
    timestamp: float
    time_str: str
    trigger_text: str
    context_text: str
    matched_keywords: list[str]
    image_path: str | None = None

    def to_markdown(self) -> str:
        checked = "x" if self.image_path else " "
        lines = [f"- [{checked}] **[{self.time_str}]** \"{self.trigger_text}\""]
        lines.append(f"  > 주변 텍스트: \"{self.context_text}\"")
        if self.image_path:
            lines.append(f"  > 첨부: ![[{self.image_path}]]")
        else:
            lines.append("  > 첨부: (없음)")
        return "\n".join(lines)


@dataclass
class AnchorsResult:
    """Visual Anchors 탐지 결과."""
    candidates: list[AnchorCandidate]
    course: str
    date: str

    def to_markdown_section(self) -> str:
        if not self.candidates:
            return ""
        lines = ["## Visual Anchors", "### 후보 (자동 생성)", ""]
        for c in self.candidates:
            lines.append(c.to_markdown())
        return "\n".join(lines)


def _fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def _build_keyword_pattern(keywords: list[str]) -> re.Pattern:
    escaped = [re.escape(kw) for kw in sorted(keywords, key=len, reverse=True)]
    return re.compile("|".join(escaped))


def _get_context_text(
    segments: list[Segment],
    center_idx: int,
    context_seconds: float,
) -> str:
    """중심 세그먼트 전후 context_seconds 범위의 텍스트를 결합한다."""
    center = segments[center_idx]
    start_time = center.start - context_seconds
    end_time = center.end + context_seconds

    context_parts: list[str] = []
    for seg in segments:
        if seg.end < start_time:
            continue
        if seg.start > end_time:
            break
        text = seg.text.strip()
        if text:
            context_parts.append(text)

    combined = " ".join(context_parts)
    if len(combined) > 200:
        combined = combined[:197] + "…"
    return combined


def detect_anchors(
    transcript: TranscriptResult,
    cfg: AnchorsConfig,
    course: str,
    date: str,
) -> AnchorsResult:
    """전사 결과에서 Visual Anchor 후보를 탐지한다."""
    pattern = _build_keyword_pattern(cfg.keywords)
    segments = transcript.segments
    raw_hits: list[tuple[int, list[str]]] = []

    for i, seg in enumerate(segments):
        text = seg.text.strip()
        if not text:
            continue
        matches = pattern.findall(text)
        if matches:
            raw_hits.append((i, matches))

    merged = _merge_nearby_hits(raw_hits, segments, cfg.merge_gap_seconds)

    candidates: list[AnchorCandidate] = []
    for seg_idx, keywords in merged:
        seg = segments[seg_idx]
        trigger = seg.text.strip()
        if len(trigger) > 80:
            trigger = trigger[:77] + "…"

        context = _get_context_text(segments, seg_idx, cfg.context_seconds)

        candidates.append(AnchorCandidate(
            timestamp=seg.start,
            time_str=_fmt_time(seg.start),
            trigger_text=trigger,
            context_text=context,
            matched_keywords=list(set(keywords)),
        ))

    logger.info(f"Visual Anchors: {len(candidates)}개 후보 탐지 (원시 {len(raw_hits)}개에서 병합)")
    return AnchorsResult(candidates=candidates, course=course, date=date)


def _merge_nearby_hits(
    hits: list[tuple[int, list[str]]],
    segments: list[Segment],
    gap_seconds: float,
) -> list[tuple[int, list[str]]]:
    """가까운 히트를 병합하여 중복 앵커를 줄인다."""
    if not hits:
        return []

    merged: list[tuple[int, list[str]]] = []
    current_idx, current_kws = hits[0]

    for next_idx, next_kws in hits[1:]:
        time_gap = segments[next_idx].start - segments[current_idx].end
        if time_gap <= gap_seconds:
            current_kws = current_kws + next_kws
        else:
            merged.append((current_idx, current_kws))
            current_idx, current_kws = next_idx, next_kws

    merged.append((current_idx, current_kws))
    return merged


def attach_image(
    anchors: AnchorsResult,
    image_path: str,
    timestamp: float,
    tolerance_seconds: float = 60.0,
) -> bool:
    """타임스탬프가 가장 가까운 앵커에 이미지를 첨부한다.

    Phase 3 이미지 반자동 연결에서 호출.
    """
    if not anchors.candidates:
        return False

    best: AnchorCandidate | None = None
    best_diff = float("inf")

    for c in anchors.candidates:
        diff = abs(c.timestamp - timestamp)
        if diff < best_diff:
            best_diff = diff
            best = c

    if best is not None and best_diff <= tolerance_seconds:
        best.image_path = image_path
        logger.info(f"이미지 첨부: {image_path} → [{best.time_str}] (차이: {best_diff:.0f}초)")
        return True

    logger.warning(f"이미지 매칭 실패: {image_path} (가장 가까운 앵커와 {best_diff:.0f}초 차이)")
    return False
