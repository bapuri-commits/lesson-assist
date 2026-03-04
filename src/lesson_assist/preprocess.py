"""영상/오디오 전처리.

영상 파일(mp4, mkv, webm)에서 오디오 트랙을 추출하고,
오디오 전처리(잡음 제거, 무음 제거, 정규화)를 수행한다.
온라인 수업의 경우 시간대별 스크린샷을 생성한다.
"""
from __future__ import annotations

import json
import subprocess
import shutil
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from .config import CleanAudioConfig


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


@dataclass
class CleanStats:
    """전처리 결과 통계."""
    original_duration: float
    cleaned_duration: float
    removed_seconds: float
    original_size_mb: float
    cleaned_size_mb: float
    filters_applied: list[str]

    @property
    def reduction_pct(self) -> float:
        if self.original_duration == 0:
            return 0.0
        return (self.removed_seconds / self.original_duration) * 100

    def log_summary(self) -> None:
        logger.info(f"  원본: {self.original_duration:.0f}초 ({self.original_size_mb:.1f}MB)")
        logger.info(f"  결과: {self.cleaned_duration:.0f}초 ({self.cleaned_size_mb:.1f}MB)")
        logger.info(f"  제거: {self.removed_seconds:.0f}초 ({self.reduction_pct:.1f}%)")
        logger.info(f"  적용 필터: {', '.join(self.filters_applied)}")


def _get_duration(audio_path: Path) -> float:
    """ffprobe로 오디오 길이(초)를 구한다."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 0.0
    cmd = [
        ffprobe, "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return 0.0
    try:
        info = json.loads(result.stdout)
        return float(info["format"]["duration"])
    except (json.JSONDecodeError, KeyError, ValueError):
        return 0.0


def _check_afftdn_available() -> bool:
    """ffmpeg에 afftdn 필터가 있는지 확인한다."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    result = subprocess.run(
        [ffmpeg, "-filters"], capture_output=True, text=True,
    )
    return "afftdn" in result.stdout


def _build_filter_chain(cfg: CleanAudioConfig) -> tuple[str, list[str]]:
    """설정에 따라 ffmpeg 오디오 필터 체인을 조립한다."""
    filters: list[str] = []
    names: list[str] = []

    if cfg.highpass_freq > 0:
        filters.append(f"highpass=f={cfg.highpass_freq}")
        names.append(f"highpass({cfg.highpass_freq}Hz)")

    if cfg.lowpass_freq > 0:
        filters.append(f"lowpass=f={cfg.lowpass_freq}")
        names.append(f"lowpass({cfg.lowpass_freq}Hz)")

    if cfg.denoise and _check_afftdn_available():
        strength = abs(cfg.denoise_strength)
        filters.append(f"afftdn=nf=-{strength}")
        names.append(f"denoise(nf=-{strength})")

    if cfg.remove_silence:
        threshold = f"{cfg.silence_threshold_db}dB"
        dur = cfg.min_silence_duration
        filters.append(
            f"silenceremove=stop_periods=-1"
            f":stop_duration={dur}"
            f":stop_threshold={threshold}"
        )
        names.append(f"silence_remove(>{dur}s, <{threshold})")

    if cfg.normalize:
        filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")
        names.append("loudnorm")

    return ",".join(filters), names


def _settings_hash(cfg: CleanAudioConfig) -> str:
    """설정값으로 짧은 해시를 만들어 캐시 무효화에 사용한다."""
    import hashlib
    key = (
        f"{cfg.highpass_freq}_{cfg.lowpass_freq}_{cfg.denoise}_{cfg.denoise_strength}"
        f"_{cfg.remove_silence}_{cfg.silence_threshold_db}_{cfg.min_silence_duration}"
        f"_{cfg.normalize}"
    )
    return hashlib.md5(key.encode()).hexdigest()[:8]


def clean_audio(
    audio_path: Path,
    cfg: CleanAudioConfig,
    output_dir: Path | None = None,
) -> tuple[Path, CleanStats]:
    """오디오 전처리: 잡음 제거 + 긴 공백 제거 + 음량 정규화.

    Returns:
        (cleaned_audio_path, stats)
    """
    filter_chain, filter_names = _build_filter_chain(cfg)

    original_duration = _get_duration(audio_path)
    original_size = audio_path.stat().st_size / (1024 * 1024) if audio_path.exists() else 0.0

    if not filter_chain:
        logger.info("전처리 필터 없음 — 원본 사용")
        return audio_path, CleanStats(
            original_duration=original_duration,
            cleaned_duration=original_duration,
            removed_seconds=0,
            original_size_mb=original_size,
            cleaned_size_mb=original_size,
            filters_applied=[],
        )

    ffmpeg = ensure_ffmpeg()

    if output_dir is None:
        output_dir = audio_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    cfg_hash = _settings_hash(cfg)
    out_path = output_dir / f"{audio_path.stem}_cleaned_{cfg_hash}.wav"

    if out_path.exists():
        cleaned_duration = _get_duration(out_path)
        cleaned_size = out_path.stat().st_size / (1024 * 1024)
        stats = CleanStats(
            original_duration=original_duration,
            cleaned_duration=cleaned_duration,
            removed_seconds=max(0.0, original_duration - cleaned_duration),
            original_size_mb=original_size,
            cleaned_size_mb=cleaned_size,
            filters_applied=["(캐시 사용)"],
        )
        logger.info(f"이미 전처리된 파일 사용: {out_path.name}")
        stats.log_summary()
        return out_path, stats

    logger.info(f"오디오 전처리 시작: {audio_path.name}")
    logger.info(f"  필터: {filter_chain}")

    cmd = [
        ffmpeg, "-i", str(audio_path),
        "-af", filter_chain,
        "-ar", "16000",
        "-ac", "1",
        "-acodec", "pcm_s16le",
        "-y",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning(f"전처리 실패, 원본 사용: {result.stderr[-300:]}")
        return audio_path, CleanStats(
            original_duration=original_duration,
            cleaned_duration=original_duration,
            removed_seconds=0,
            original_size_mb=original_size,
            cleaned_size_mb=original_size,
            filters_applied=["FAILED"],
        )

    cleaned_duration = _get_duration(out_path)
    cleaned_size = out_path.stat().st_size / (1024 * 1024)

    stats = CleanStats(
        original_duration=original_duration,
        cleaned_duration=cleaned_duration,
        removed_seconds=max(0.0, original_duration - cleaned_duration),
        original_size_mb=original_size,
        cleaned_size_mb=cleaned_size,
        filters_applied=filter_names,
    )

    logger.info("전처리 완료:")
    stats.log_summary()
    return out_path, stats


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
