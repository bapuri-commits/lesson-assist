"""영상/오디오 전처리.

영상 파일(mp4, mkv, webm)에서 오디오 트랙을 추출하고,
온라인 수업의 경우 시간대별 스크린샷을 생성한다.
"""
from __future__ import annotations

import subprocess
import shutil
from pathlib import Path

from loguru import logger


AUDIO_EXTS = {".m4a", ".mp3", ".wav", ".flac", ".ogg", ".aac", ".wma"}
VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".avi", ".mov"}


def ensure_ffmpeg() -> str:
    """ffmpeg 실행 파일 경로를 반환하거나 없으면 에러."""
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg가 PATH에 없습니다. ffmpeg를 설치하세요.")
    return path


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTS


def is_audio(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTS


def extract_audio(video_path: Path, output_dir: Path | None = None) -> Path:
    """영상에서 오디오 트랙을 WAV로 추출한다."""
    ffmpeg = ensure_ffmpeg()

    if output_dir is None:
        output_dir = video_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    audio_path = output_dir / f"{video_path.stem}_audio.wav"
    if audio_path.exists():
        logger.info(f"이미 추출된 오디오 사용: {audio_path}")
        return audio_path

    logger.info(f"영상에서 오디오 추출: {video_path.name} → {audio_path.name}")
    cmd = [
        ffmpeg, "-i", str(video_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        "-y",
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"오디오 추출 실패: {result.stderr[-500:]}")

    logger.info(f"오디오 추출 완료: {audio_path}")
    return audio_path


def extract_screenshots(
    video_path: Path,
    timestamps: list[float],
    output_dir: Path,
    file_id: str,
) -> list[Path]:
    """영상에서 특정 타임스탬프의 스크린샷을 추출한다.

    온라인 수업 녹화 영상에서 Visual Anchors 시점의 화면을 캡처하는 데 사용.
    """
    ffmpeg = ensure_ffmpeg()
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    for ts in timestamps:
        m, s = divmod(int(ts), 60)
        h, m = divmod(m, 60)
        time_str = f"{h:02d}:{m:02d}:{s:02d}"
        filename = f"{file_id}_{int(ts)}s.jpg"
        out_path = output_dir / filename

        if out_path.exists():
            paths.append(out_path)
            continue

        cmd = [
            ffmpeg, "-ss", time_str,
            "-i", str(video_path),
            "-vframes", "1",
            "-q:v", "2",
            "-y",
            str(out_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and out_path.exists():
            paths.append(out_path)
        else:
            logger.warning(f"스크린샷 추출 실패: {time_str}")

    logger.info(f"스크린샷 {len(paths)}/{len(timestamps)}개 추출")
    return paths


def concat_audio(audio_paths: list[Path], output_dir: Path) -> Path:
    """여러 오디오 파일을 순서대로 합쳐서 하나의 WAV로 만든다.

    같은 강의가 여러 파일로 쪼개진 경우 사용.
    ffmpeg의 concat demuxer를 사용한다.
    """
    if len(audio_paths) == 1:
        return audio_paths[0]

    ffmpeg = ensure_ffmpeg()
    output_dir.mkdir(parents=True, exist_ok=True)

    stems = "_".join(p.stem[:20] for p in audio_paths[:3])
    out_path = output_dir / f"{stems}_merged.wav"

    if out_path.exists():
        logger.info(f"이미 합쳐진 파일 사용: {out_path}")
        return out_path

    # ffmpeg concat demuxer용 리스트 파일 생성
    list_path = output_dir / "_concat_list.txt"
    with open(list_path, "w", encoding="utf-8") as f:
        for p in audio_paths:
            # ffmpeg concat demuxer는 forward slash를 요구 (Windows 백슬래시 호환 문제)
            normalized = str(p.resolve()).replace("\\", "/")
            escaped = normalized.replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")

    logger.info(f"오디오 합치기: {len(audio_paths)}개 파일 → {out_path.name}")
    cmd = [
        ffmpeg,
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_path),
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        "-y",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    list_path.unlink(missing_ok=True)

    if result.returncode != 0:
        raise RuntimeError(f"오디오 합치기 실패: {result.stderr[-500:]}")

    logger.info(f"오디오 합치기 완료: {out_path}")
    return out_path


def prepare_input(input_path: Path, output_dir: Path | None = None) -> tuple[Path, bool]:
    """입력 파일을 처리 가능한 오디오로 변환한다.

    Returns:
        (audio_path, is_video) — 오디오 경로와 원본이 영상이었는지 여부
    """
    if is_audio(input_path):
        return input_path, False
    elif is_video(input_path):
        audio = extract_audio(input_path, output_dir)
        return audio, True
    else:
        raise ValueError(f"지원하지 않는 파일 형식: {input_path.suffix}")
