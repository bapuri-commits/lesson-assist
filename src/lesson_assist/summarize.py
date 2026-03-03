from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from loguru import logger
from openai import OpenAI

from .config import SummarizeConfig
from .prompts import (
    INTEGRATED_SUMMARY_SYSTEM,
    INTEGRATED_SUMMARY_USER,
    PART_SUMMARY_SYSTEM,
    PART_SUMMARY_USER,
)
from .segment import Part


@dataclass
class PartSummary:
    part_index: int
    time_range: str
    summary: str


@dataclass
class SummaryResult:
    part_summaries: list[PartSummary]
    integrated_summary: str
    course: str
    date: str

    def save(self, out_dir: Path, file_id: str) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{file_id}_summary.json"
        payload = {
            "course": self.course,
            "date": self.date,
            "integrated_summary": self.integrated_summary,
            "part_summaries": [
                {"part_index": ps.part_index, "time_range": ps.time_range, "summary": ps.summary}
                for ps in self.part_summaries
            ],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"요약 결과 저장: {path}")
        return path


def _call_llm(client: OpenAI, cfg: SummarizeConfig, system: str, user: str) -> str:
    """OpenAI API를 호출하고 응답 텍스트를 반환한다."""
    for attempt in range(cfg.max_retries):
        try:
            resp = client.chat.completions.create(
                model=cfg.model,
                temperature=cfg.temperature,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            return resp.choices[0].message.content
        except Exception as e:
            logger.warning(f"LLM 호출 실패 (시도 {attempt + 1}/{cfg.max_retries}): {e}")
            if attempt == cfg.max_retries - 1:
                raise
    return ""


def summarize_parts(
    parts: list[Part],
    cfg: SummarizeConfig,
    api_key: str,
) -> list[PartSummary]:
    """각 파트를 개별 요약한다."""
    client = OpenAI(api_key=api_key)
    summaries: list[PartSummary] = []

    for part in parts:
        logger.info(f"Part {part.index} 요약 중 ({part.time_range_str()})…")
        user_msg = PART_SUMMARY_USER.format(
            part_index=part.index,
            time_range=part.time_range_str(),
            text=part.text,
        )
        result = _call_llm(client, cfg, PART_SUMMARY_SYSTEM, user_msg)
        summaries.append(PartSummary(
            part_index=part.index,
            time_range=part.time_range_str(),
            summary=result,
        ))
        logger.info(f"Part {part.index} 요약 완료 ({len(result)}자)")

    return summaries


def summarize_integrated(
    part_summaries: list[PartSummary],
    course: str,
    date: str,
    cfg: SummarizeConfig,
    api_key: str,
) -> str:
    """파트별 요약을 통합 요약한다."""
    client = OpenAI(api_key=api_key)

    parts_text = "\n\n".join(
        f"### Part {ps.part_index} ({ps.time_range})\n{ps.summary}"
        for ps in part_summaries
    )

    logger.info("통합 요약 생성 중…")
    user_msg = INTEGRATED_SUMMARY_USER.format(
        course=course,
        date=date,
        part_summaries=parts_text,
    )
    result = _call_llm(client, cfg, INTEGRATED_SUMMARY_SYSTEM, user_msg)
    logger.info(f"통합 요약 완료 ({len(result)}자)")
    return result


def summarize(
    parts: list[Part],
    course: str,
    date: str,
    cfg: SummarizeConfig,
    api_key: str,
) -> SummaryResult:
    """파트별 요약 + 통합 요약을 수행한다."""
    part_summaries = summarize_parts(parts, cfg, api_key)
    integrated = summarize_integrated(part_summaries, course, date, cfg, api_key)
    return SummaryResult(
        part_summaries=part_summaries,
        integrated_summary=integrated,
        course=course,
        date=date,
    )
