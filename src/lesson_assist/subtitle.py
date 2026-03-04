"""SRT/VTT 자막 생성.

전사 세그먼트를 SRT 및 WebVTT 형식으로 출력한다.
나중에 녹화 영상과 매칭하거나 복습 시 활용.
"""
from __future__ import annotations

from pathlib import Path

from loguru import logger

from .transcribe import TranscriptResult


def _format_srt_time(seconds: float) -> str:
    """초를 SRT 타임코드 형식(HH:MM:SS,mmm)으로 변환."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_vtt_time(seconds: float) -> str:
    """초를 VTT 타임코드 형식(HH:MM:SS.mmm)으로 변환."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def generate_srt(transcript: TranscriptResult) -> str:
    """전사 결과를 SRT 포맷 문자열로 변환."""
    lines: list[str] = []
    counter = 0
    for seg in transcript.segments:
        text = seg.text.strip()
        if not text:
            continue
        counter += 1
        lines.append(str(counter))
        lines.append(f"{_format_srt_time(seg.start)} --> {_format_srt_time(seg.end)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def generate_vtt(transcript: TranscriptResult) -> str:
    """전사 결과를 WebVTT 포맷 문자열로 변환."""
    lines: list[str] = ["WEBVTT", ""]
    counter = 0
    for seg in transcript.segments:
        text = seg.text.strip()
        if not text:
            continue
        counter += 1
        lines.append(str(counter))
        lines.append(f"{_format_vtt_time(seg.start)} --> {_format_vtt_time(seg.end)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def save_subtitles(
    transcript: TranscriptResult,
    out_dir: Path,
    file_id: str,
    formats: list[str] | None = None,
) -> list[Path]:
    """SRT/VTT 자막 파일을 저장한다.

    Args:
        formats: 저장할 포맷 목록. 기본값 ["srt", "vtt"].
    """
    if formats is None:
        formats = ["srt", "vtt"]

    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    for fmt in formats:
        if fmt == "srt":
            content = generate_srt(transcript)
        elif fmt == "vtt":
            content = generate_vtt(transcript)
        else:
            logger.warning(f"지원하지 않는 자막 포맷: {fmt}")
            continue

        path = out_dir / f"{file_id}.{fmt}"
        path.write_text(content, encoding="utf-8")
        paths.append(path)
        logger.info(f"자막 저장: {path}")

    return paths
