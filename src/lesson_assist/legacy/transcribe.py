from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from loguru import logger

from .config import TranscribeConfig


def _register_cuda_dlls() -> None:
    """pip으로 설치된 NVIDIA DLL 경로를 PATH에 추가한다."""
    if sys.platform != "win32":
        return
    dll_dirs: list[str] = []
    try:
        import nvidia.cublas
        dll_dirs.append(str(Path(nvidia.cublas.__path__[0]) / "bin"))
    except ImportError:
        pass
    try:
        import nvidia.cudnn
        dll_dirs.append(str(Path(nvidia.cudnn.__path__[0]) / "bin"))
    except ImportError:
        pass
    for d in dll_dirs:
        if Path(d).exists():
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
            os.add_dll_directory(d)


@dataclass
class Segment:
    """전사된 하나의 세그먼트."""
    id: int
    start: float
    end: float
    text: str
    avg_logprob: float
    no_speech_prob: float

    @property
    def duration(self) -> float:
        return self.end - self.start

    def time_str(self, t: float) -> str:
        m, s = divmod(int(t), 60)
        return f"{m:02d}:{s:02d}"

    @property
    def start_str(self) -> str:
        return self.time_str(self.start)

    @property
    def end_str(self) -> str:
        return self.time_str(self.end)


@dataclass
class TranscriptResult:
    """전사 결과 전체."""
    segments: list[Segment]
    audio_duration: float
    model: str
    language: str

    @property
    def full_text(self) -> str:
        return " ".join(seg.text.strip() for seg in self.segments if seg.text.strip())

    def save(self, out_dir: Path, file_id: str) -> tuple[Path, Path]:
        """raw text와 segments json을 저장하고 경로 튜플을 반환한다. (레거시 호환)"""
        out_dir.mkdir(parents=True, exist_ok=True)
        raw_path = out_dir / f"{file_id}_raw.txt"
        seg_path = out_dir / f"{file_id}_segments.json"
        self.save_to(seg_path, raw_path)
        return raw_path, seg_path

    def save_to(self, seg_path: Path, raw_path: Path | None = None) -> None:
        """지정된 경로에 segments json(+ 선택적 raw text)을 저장한다."""
        seg_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "audio_duration": self.audio_duration,
            "model": self.model,
            "language": self.language,
            "segments": [asdict(s) for s in self.segments],
        }
        seg_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        if raw_path is not None:
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(self.full_text, encoding="utf-8")

        logger.info(f"전사 결과 저장: {seg_path}")

    @classmethod
    def load(cls, seg_path: Path) -> TranscriptResult:
        """저장된 segments json에서 복원한다."""
        data = json.loads(seg_path.read_text(encoding="utf-8"))
        segments = [Segment(**s) for s in data["segments"]]
        return cls(
            segments=segments,
            audio_duration=data["audio_duration"],
            model=data["model"],
            language=data["language"],
        )


def transcribe(audio_path: Path, cfg: TranscribeConfig, out_dir: Path | None = None, file_id: str | None = None) -> TranscriptResult:
    """오디오를 전사한다.

    backend에 따라 로컬 GPU 또는 RunPod 서버리스를 사용한다.
    로컬 CUDA 사용 시 서브프로세스에서 전사를 수행한다.
    """
    if cfg.backend == "runpod":
        return _transcribe_runpod(audio_path, cfg)

    if cfg.device == "cuda" and out_dir and file_id:
        return _transcribe_subprocess(audio_path, cfg, out_dir, file_id)
    return _transcribe_direct(audio_path, cfg)


def _transcribe_subprocess(audio_path: Path, cfg: TranscribeConfig, out_dir: Path, file_id: str) -> TranscriptResult:
    """서브프로세스에서 전사를 실행하고 결과를 로드한다."""
    seg_path = out_dir / f"{file_id}_segments.json"

    worker = Path(__file__).parent / "_transcribe_worker.py"
    cmd = [
        sys.executable, str(worker),
        "--audio", str(audio_path),
        "--out-dir", str(out_dir),
        "--file-id", file_id,
        "--model", cfg.model,
        "--language", cfg.language,
        "--device", cfg.device,
        "--compute-type", cfg.compute_type,
        "--beam-size", str(cfg.beam_size),
        "--vad-filter", str(cfg.vad_filter),
    ]

    logger.info(f"전사 시작 (서브프로세스): model={cfg.model}, device={cfg.device}")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")

    # 서브프로세스 stdout을 로깅
    if result.stdout:
        for line in result.stdout.strip().split("\n"):
            logger.info(f"  [worker] {line}")

    if not seg_path.exists():
        logger.error(f"전사 실패: 결과 파일 없음")
        if result.stderr:
            logger.error(f"  stderr: {result.stderr[-500:]}")
        raise RuntimeError("전사 서브프로세스가 결과를 생성하지 못했습니다")

    # 크래시 코드는 무시 — 파일이 저장됐으면 성공
    if result.returncode != 0:
        logger.debug(f"서브프로세스 exit code: {result.returncode} (결과 파일 존재, 무시)")

    transcript = TranscriptResult.load(seg_path)
    logger.info(f"전사 결과 로드: {len(transcript.segments)}개 세그먼트, {transcript.audio_duration:.0f}초")
    return transcript


def _transcribe_direct(audio_path: Path, cfg: TranscribeConfig) -> TranscriptResult:
    """현재 프로세스에서 직접 전사한다 (CPU 모드용)."""
    if cfg.device == "cuda":
        _register_cuda_dlls()

    from faster_whisper import WhisperModel

    logger.info(f"전사 시작: model={cfg.model}, device={cfg.device}, file={audio_path.name}")

    model = WhisperModel(
        cfg.model,
        device=cfg.device,
        compute_type=cfg.compute_type,
    )

    segments_iter, info = model.transcribe(
        str(audio_path),
        language=cfg.language,
        beam_size=cfg.beam_size,
        vad_filter=cfg.vad_filter,
        word_timestamps=True,
    )

    segments: list[Segment] = []
    for i, seg in enumerate(segments_iter):
        segments.append(Segment(
            id=i,
            start=seg.start,
            end=seg.end,
            text=seg.text,
            avg_logprob=seg.avg_logprob,
            no_speech_prob=seg.no_speech_prob,
        ))
        if (i + 1) % 50 == 0:
            logger.debug(f"  … {i + 1}개 세그먼트 처리")

    duration = info.duration if hasattr(info, "duration") else (segments[-1].end if segments else 0.0)
    logger.info(f"전사 완료: {len(segments)}개 세그먼트, {duration:.0f}초")

    return TranscriptResult(
        segments=segments,
        audio_duration=duration,
        model=cfg.model,
        language=cfg.language,
    )


def _transcribe_runpod(audio_path: Path, cfg: TranscribeConfig) -> TranscriptResult:
    """RunPod 서버리스 엔드포인트에서 전사를 수행한다."""
    import base64
    import time
    import requests

    rp = cfg.runpod
    if not rp.api_key or not rp.endpoint_id:
        raise ValueError("RunPod 설정이 없습니다. config.yaml에 transcribe.runpod.api_key와 endpoint_id를 설정하세요.")

    logger.info(f"RunPod 전사 시작: model={cfg.model}, endpoint={rp.endpoint_id}")

    audio_b64 = base64.b64encode(audio_path.read_bytes()).decode("ascii")

    url = f"https://api.runpod.ai/v2/{rp.endpoint_id}/run"
    headers = {"Authorization": f"Bearer {rp.api_key}", "Content-Type": "application/json"}
    payload = {
        "input": {
            "audio_base64": audio_b64,
            "model": cfg.model,
            "language": cfg.language,
            "beam_size": cfg.beam_size,
            "vad_filter": cfg.vad_filter,
        }
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    job = resp.json()
    job_id = job["id"]
    logger.info(f"RunPod 작업 제출: {job_id}")

    status_url = f"https://api.runpod.ai/v2/{rp.endpoint_id}/status/{job_id}"
    deadline = time.time() + rp.timeout
    poll_interval = 5

    while time.time() < deadline:
        time.sleep(poll_interval)
        sr = requests.get(status_url, headers=headers, timeout=30)
        sr.raise_for_status()
        status_data = sr.json()
        status = status_data.get("status")

        if status == "COMPLETED":
            output = status_data["output"]
            segments = [
                Segment(
                    id=s["id"], start=s["start"], end=s["end"],
                    text=s["text"], avg_logprob=s.get("avg_logprob", 0.0),
                    no_speech_prob=s.get("no_speech_prob", 0.0),
                )
                for s in output["segments"]
            ]
            result = TranscriptResult(
                segments=segments,
                audio_duration=output.get("audio_duration", segments[-1].end if segments else 0.0),
                model=cfg.model,
                language=cfg.language,
            )
            logger.info(f"RunPod 전사 완료: {len(segments)}개 세그먼트, {result.audio_duration:.0f}초")
            return result

        if status == "FAILED":
            error = status_data.get("error", "알 수 없는 오류")
            raise RuntimeError(f"RunPod 전사 실패: {error}")

        logger.debug(f"RunPod 상태: {status} (경과 {time.time() - (deadline - rp.timeout):.0f}초)")
        poll_interval = min(poll_interval * 1.5, 30)

    raise TimeoutError(f"RunPod 전사 타임아웃 ({rp.timeout}초)")
