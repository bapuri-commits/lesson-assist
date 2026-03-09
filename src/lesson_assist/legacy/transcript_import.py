"""외부 전사 파일(TXT/SRT) 임포트.

다글로 등 외부 서비스에서 내보낸 전사 결과를 TranscriptResult로 변환한다.
"""
from __future__ import annotations

import re
from pathlib import Path

from loguru import logger

from .transcribe import Segment, TranscriptResult


def _parse_srt_time(time_str: str) -> float:
    """SRT 타임코드(HH:MM:SS,mmm)를 초 단위 float로 변환."""
    time_str = time_str.strip().replace(",", ".")
    parts = time_str.split(":")
    h, m = int(parts[0]), int(parts[1])
    s = float(parts[2])
    return h * 3600 + m * 60 + s


def import_srt(path: Path) -> TranscriptResult:
    """SRT 파일을 TranscriptResult로 변환한다."""
    content = path.read_text(encoding="utf-8")
    blocks = re.split(r"\n\s*\n", content.strip())

    segments: list[Segment] = []
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue

        time_match = re.match(
            r"(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})",
            lines[1],
        )
        if not time_match:
            continue

        start = _parse_srt_time(time_match.group(1))
        end = _parse_srt_time(time_match.group(2))
        text = " ".join(lines[2:]).strip()

        if not text:
            continue

        segments.append(Segment(
            id=len(segments),
            start=start,
            end=end,
            text=text,
            avg_logprob=0.0,
            no_speech_prob=0.0,
        ))

    duration = segments[-1].end if segments else 0.0
    logger.info(f"SRT 임포트: {len(segments)}개 세그먼트, {duration:.0f}초")
    return TranscriptResult(
        segments=segments,
        audio_duration=duration,
        model="external-srt",
        language="ko",
    )


def import_txt(path: Path) -> TranscriptResult:
    """일반 텍스트 파일을 TranscriptResult로 변환한다.

    타임스탬프 없이 텍스트만 있는 경우, 문장 단위로 분할하여
    균등 간격의 가상 타임스탬프를 부여한다.
    """
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return TranscriptResult(segments=[], audio_duration=0.0, model="external-txt", language="ko")

    sentences = re.split(r"(?<=[.!?。])\s+", content)
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        sentences = [content]

    segments: list[Segment] = []
    for i, sentence in enumerate(sentences):
        segments.append(Segment(
            id=i,
            start=0.0,
            end=0.0,
            text=sentence,
            avg_logprob=0.0,
            no_speech_prob=0.0,
        ))

    logger.info(f"TXT 임포트: {len(segments)}개 세그먼트 (타임스탬프 없음)")
    return TranscriptResult(
        segments=segments,
        audio_duration=0.0,
        model="external-txt",
        language="ko",
    )


def import_vtt(path: Path) -> TranscriptResult:
    """VTT 파일을 TranscriptResult로 변환한다."""
    content = path.read_text(encoding="utf-8")
    content = re.sub(r"^WEBVTT\s*\n\s*\n?", "", content, count=1)
    blocks = re.split(r"\n\s*\n", content.strip())

    segments: list[Segment] = []
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 2:
            continue

        time_line_idx = -1
        for i, line in enumerate(lines):
            if "-->" in line:
                time_line_idx = i
                break
        if time_line_idx == -1:
            continue

        time_match = re.match(
            r"(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})",
            lines[time_line_idx],
        )
        if not time_match:
            continue

        start = _parse_srt_time(time_match.group(1))
        end = _parse_srt_time(time_match.group(2))
        text = " ".join(lines[time_line_idx + 1:]).strip()

        if not text:
            continue

        segments.append(Segment(
            id=len(segments),
            start=start,
            end=end,
            text=text,
            avg_logprob=0.0,
            no_speech_prob=0.0,
        ))

    duration = segments[-1].end if segments else 0.0
    logger.info(f"VTT 임포트: {len(segments)}개 세그먼트, {duration:.0f}초")
    return TranscriptResult(
        segments=segments,
        audio_duration=duration,
        model="external-vtt",
        language="ko",
    )


def import_transcript(path: Path) -> TranscriptResult:
    """파일 확장자에 따라 적절한 임포터를 선택한다."""
    suffix = path.suffix.lower()
    if suffix == ".srt":
        return import_srt(path)
    elif suffix == ".vtt":
        return import_vtt(path)
    elif suffix in (".txt", ".text"):
        return import_txt(path)
    elif suffix == ".json":
        return TranscriptResult.load(path)
    else:
        logger.warning(f"지원하지 않는 형식, TXT로 시도: {suffix}")
        return import_txt(path)
