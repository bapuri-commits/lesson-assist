"""전사 서브프로세스 워커.

CUDA ctranslate2가 Windows에서 프로세스 종료 시 크래시하는 문제를 우회하기 위해
별도 프로세스에서 실행된다. 결과를 파일로 저장한 뒤 종료한다.
"""
import argparse
import json
import os
import sys
from pathlib import Path


def _register_cuda_dlls():
    if sys.platform != "win32":
        return
    try:
        import nvidia.cublas
        d = str(Path(nvidia.cublas.__path__[0]) / "bin")
        if Path(d).exists():
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
            os.add_dll_directory(d)
    except ImportError:
        pass
    try:
        import nvidia.cudnn
        d = str(Path(nvidia.cudnn.__path__[0]) / "bin")
        if Path(d).exists():
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
            os.add_dll_directory(d)
    except ImportError:
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--file-id", required=True)
    parser.add_argument("--model", default="large-v3")
    parser.add_argument("--language", default="ko")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--compute-type", default="float16")
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--vad-filter", default="True")
    args = parser.parse_args()

    if args.device == "cuda":
        _register_cuda_dlls()

    from faster_whisper import WhisperModel

    print(f"전사 시작: model={args.model}, device={args.device}", flush=True)

    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)

    vad = args.vad_filter.lower() in ("true", "1", "yes")
    segments_iter, info = model.transcribe(
        args.audio,
        language=args.language,
        beam_size=args.beam_size,
        vad_filter=vad,
        word_timestamps=True,
    )

    segments = []
    for i, seg in enumerate(segments_iter):
        segments.append({
            "id": i,
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
            "avg_logprob": seg.avg_logprob,
            "no_speech_prob": seg.no_speech_prob,
        })
        if (i + 1) % 50 == 0:
            print(f"  … {i + 1}개 세그먼트 처리", flush=True)

    duration = info.duration if hasattr(info, "duration") else (segments[-1]["end"] if segments else 0.0)
    print(f"전사 완료: {len(segments)}개 세그먼트, {duration:.0f}초", flush=True)

    # 결과 저장 (크래시 전에 반드시 완료)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "audio_duration": duration,
        "model": args.model,
        "language": args.language,
        "segments": segments,
    }

    seg_path = out_dir / f"{args.file_id}_segments.json"
    seg_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    raw_text = " ".join(s["text"].strip() for s in segments if s["text"].strip())
    raw_path = out_dir / f"{args.file_id}_raw.txt"
    raw_path.write_text(raw_text, encoding="utf-8")

    print(f"저장 완료: {seg_path}", flush=True)


if __name__ == "__main__":
    main()
