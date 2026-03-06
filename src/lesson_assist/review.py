from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from loguru import logger

from .config import ReviewConfig
from .transcribe import Segment, TranscriptResult


@dataclass
class ReviewCandidate:
    """교정이 필요할 수 있는 저신뢰 세그먼트."""
    idx: int
    start: str
    end: str
    original: str
    reason: str
    avg_logprob: float
    no_speech_prob: float
    corrected: str = ""
    action: str = "pending"  # pending | accepted | skipped


def extract_candidates(transcript: TranscriptResult, cfg: ReviewConfig) -> list[ReviewCandidate]:
    """전사 결과에서 저신뢰 후보를 추출한다."""
    candidates: list[ReviewCandidate] = []

    for seg in transcript.segments:
        reasons: list[str] = []

        if seg.avg_logprob < cfg.logprob_threshold:
            reasons.append(f"logprob={seg.avg_logprob:.2f}")

        if seg.no_speech_prob > cfg.no_speech_threshold:
            reasons.append(f"no_speech={seg.no_speech_prob:.2f}")

        text = seg.text.strip()
        if 0 < len(text) < cfg.min_segment_chars:
            reasons.append(f"너무 짧음({len(text)}자)")

        if _has_repetition(text, cfg.max_repeat_count):
            reasons.append("반복 패턴")

        if reasons:
            candidates.append(ReviewCandidate(
                idx=seg.id,
                start=seg.start_str,
                end=seg.end_str,
                original=text,
                reason=", ".join(reasons),
                avg_logprob=seg.avg_logprob,
                no_speech_prob=seg.no_speech_prob,
            ))

    logger.info(f"교정 후보 {len(candidates)}개 추출 (전체 {len(transcript.segments)}개 세그먼트 중)")
    return candidates


def _has_repetition(text: str, threshold: int) -> bool:
    """동일 단어/구가 threshold회 이상 연속 반복되는지 검사."""
    words = text.split()
    if len(words) < threshold:
        return False
    for i in range(len(words) - threshold + 1):
        window = words[i : i + threshold]
        if len(set(window)) == 1:
            return True
    return False


def save_review(candidates: list[ReviewCandidate], path_or_dir: Path, file_id: str | None = None) -> Path:
    """교정 후보를 JSONL 파일로 저장한다.

    path_or_dir가 .jsonl로 끝나면 직접 경로, 아니면 디렉토리+file_id 방식(레거시).
    """
    if path_or_dir.suffix == ".jsonl":
        path = path_or_dir
    else:
        path = path_or_dir / f"{file_id}_review.jsonl"

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for c in candidates:
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")
    logger.info(f"교정 파일 저장: {path}")
    return path


def load_review(path: Path) -> list[ReviewCandidate]:
    """교정 JSONL 파일을 로드한다."""
    candidates = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                candidates.append(ReviewCandidate(**json.loads(line)))
    return candidates


def apply_corrections(transcript: TranscriptResult, candidates: list[ReviewCandidate]) -> TranscriptResult:
    """교정된 후보를 전사 결과에 반영한다."""
    corrections = {c.idx: c for c in candidates if c.action == "accepted" and c.corrected}
    if not corrections:
        return transcript

    new_segments = []
    for seg in transcript.segments:
        if seg.id in corrections:
            corrected = corrections[seg.id]
            new_segments.append(Segment(
                id=seg.id,
                start=seg.start,
                end=seg.end,
                text=corrected.corrected,
                avg_logprob=seg.avg_logprob,
                no_speech_prob=seg.no_speech_prob,
            ))
            logger.debug(f"교정 적용: [{seg.start_str}] {seg.text!r} → {corrected.corrected!r}")
        else:
            new_segments.append(seg)

    applied = len(corrections)
    logger.info(f"교정 {applied}개 적용 완료")
    return TranscriptResult(
        segments=new_segments,
        audio_duration=transcript.audio_duration,
        model=transcript.model,
        language=transcript.language,
    )


def print_candidates(candidates: list[ReviewCandidate]) -> None:
    """터미널에 교정 후보 목록을 출력한다."""
    if not candidates:
        logger.info("교정 후보 없음 — 전사 품질 양호")
        return

    print(f"\n{'='*60}")
    print(f" 교정 후보: {len(candidates)}개")
    print(f"{'='*60}")
    for i, c in enumerate(candidates, 1):
        print(f"\n [{i}] {c.start}~{c.end}  ({c.reason})")
        print(f"     \"{c.original}\"")
    print(f"\n{'='*60}\n")
