from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from .config import SegmentConfig
from .transcribe import Segment, TranscriptResult


@dataclass
class Part:
    """분할된 파트 하나."""
    index: int
    start: float
    end: float
    segments: list[Segment]

    @property
    def text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments if s.text.strip())

    @property
    def duration_min(self) -> float:
        return (self.end - self.start) / 60

    def time_range_str(self) -> str:
        def fmt(t: float) -> str:
            m, s = divmod(int(t), 60)
            return f"{m:02d}:{s:02d}"
        return f"{fmt(self.start)} ~ {fmt(self.end)}"


def segment_transcript(transcript: TranscriptResult, cfg: SegmentConfig) -> list[Part]:
    """전사 결과를 ~N분 단위 파트로 분할한다.
    
    분할 지점은 세그먼트 경계 중 가장 긴 무음 구간을 선택하여
    문장 중간 절단을 방지한다.
    """
    segs = transcript.segments
    if not segs:
        return []

    total_duration = transcript.audio_duration
    part_seconds = cfg.part_minutes * 60
    min_part_seconds = cfg.min_part_minutes * 60

    if total_duration <= part_seconds + min_part_seconds:
        part = Part(index=1, start=segs[0].start, end=segs[-1].end, segments=list(segs))
        logger.info(f"분할 불필요: 전체 {total_duration / 60:.1f}분 → 파트 1개")
        return [part]

    parts: list[Part] = []
    current_start_idx = 0
    part_num = 1

    while current_start_idx < len(segs):
        target_end_time = segs[current_start_idx].start + part_seconds

        if target_end_time >= segs[-1].end:
            part = Part(
                index=part_num,
                start=segs[current_start_idx].start,
                end=segs[-1].end,
                segments=segs[current_start_idx:],
            )
            parts.append(part)
            break

        # target_end_time ± 2분 범위에서 가장 긴 무음 갭을 찾는다
        window_start = target_end_time - 120
        window_end = target_end_time + 120

        best_split_idx = None
        best_gap = -1.0

        for i in range(current_start_idx + 1, len(segs)):
            if segs[i].start < window_start:
                continue
            if segs[i].start > window_end:
                break

            gap = segs[i].start - segs[i - 1].end
            if gap > best_gap:
                best_gap = gap
                best_split_idx = i

        if best_split_idx is None:
            # 윈도우 내 세그먼트가 없으면 시간 기준으로 가장 가까운 세그먼트에서 분할
            best_split_idx = _find_nearest_segment(segs, target_end_time, current_start_idx + 1)

        # 잔여 파트가 min_part_seconds보다 짧으면 병합
        remaining_duration = segs[-1].end - segs[best_split_idx].start
        if remaining_duration < min_part_seconds:
            part = Part(
                index=part_num,
                start=segs[current_start_idx].start,
                end=segs[-1].end,
                segments=segs[current_start_idx:],
            )
            parts.append(part)
            break

        part = Part(
            index=part_num,
            start=segs[current_start_idx].start,
            end=segs[best_split_idx - 1].end,
            segments=segs[current_start_idx:best_split_idx],
        )
        parts.append(part)
        current_start_idx = best_split_idx
        part_num += 1

    logger.info(f"분할 완료: {len(parts)}개 파트")
    for p in parts:
        logger.debug(f"  Part {p.index}: {p.time_range_str()} ({p.duration_min:.1f}분, {len(p.segments)}세그먼트)")

    return parts


def _find_nearest_segment(segs: list[Segment], target_time: float, start_idx: int) -> int:
    """target_time에 가장 가까운 세그먼트 시작 인덱스를 반환한다."""
    best_idx = start_idx
    best_diff = abs(segs[start_idx].start - target_time)
    for i in range(start_idx, len(segs)):
        diff = abs(segs[i].start - target_time)
        if diff < best_diff:
            best_diff = diff
            best_idx = i
        elif diff > best_diff:
            break
    return best_idx


def save_parts(parts: list[Part], session_or_dir, file_id: str | None = None) -> list[Path]:
    """파트별 텍스트를 저장한다.

    session_or_dir: SessionDir 인스턴스 또는 Path(레거시).
    """
    from .session import SessionDir

    if isinstance(session_or_dir, SessionDir):
        out_dir = session_or_dir.parts_dir
    else:
        out_dir = Path(session_or_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

    paths = []
    for part in parts:
        if isinstance(session_or_dir, SessionDir):
            path = session_or_dir.part_file(part.index)
        else:
            path = out_dir / f"{file_id}_part_{part.index:02d}.txt"
        header = f"# Part {part.index} ({part.time_range_str()})\n\n"
        path.write_text(header + part.text, encoding="utf-8")
        paths.append(path)
    logger.info(f"파트 텍스트 저장: {len(paths)}개 파일")
    return paths
