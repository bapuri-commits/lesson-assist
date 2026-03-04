from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from loguru import logger
from openai import OpenAI

from .config import SummarizeConfig
from .prompts import (
    INTEGRATED_SUMMARY_SYSTEM,
    INTEGRATED_SUMMARY_USER,
    PART_SUMMARY_RAG_PREFIX,
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


def extract_key_terms(text: str, top_n: int = 15) -> str:
    """텍스트에서 빈도 기반으로 핵심 용어를 추출하여 쿼리 문자열을 만든다.

    교수 잡담/인사로 시작해도 강의 전체에서 자주 등장하는 전문 용어가
    상위에 오므로 RAG 검색 품질이 안정적이다.
    """
    words = re.findall(r"[가-힣a-zA-Z]{2,}", text)
    stopwords = {
        "그래서", "그런데", "그리고", "그러면", "그러니까", "왜냐하면",
        "이거는", "이것은", "여기서", "저기서", "우리가", "이렇게",
        "그렇게", "이거를", "그러한", "이러한", "일단은", "하지만",
        "그래도", "거기서", "여기에", "이건", "이게", "저건",
        "네", "예", "아", "음", "자", "이제", "그", "거", "뭐",
        "있는", "하는", "되는", "않는", "없는", "같은", "라는",
        "합니다", "됩니다", "입니다", "습니다", "겠습니다",
    }
    filtered = [w for w in words if w not in stopwords]
    freq = Counter(filtered)
    top_terms = [term for term, _ in freq.most_common(top_n)]
    return " ".join(top_terms)


def summarize_parts(
    parts: list[Part],
    cfg: SummarizeConfig,
    api_key: str,
    rag_store=None,
    course: str = "",
    current_date: str = "",
) -> list[PartSummary]:
    """각 파트를 개별 요약한다.

    rag_store가 주어지면 각 파트마다 개별 RAG 검색을 수행하여
    해당 파트에 맞는 이전 강의 컨텍스트를 주입한다.
    """
    client = OpenAI(api_key=api_key)
    summaries: list[PartSummary] = []

    for part in parts:
        logger.info(f"Part {part.index} 요약 중 ({part.time_range_str()})…")

        user_msg = ""

        if rag_store is not None:
            per_part_context = _get_per_part_rag_context(
                rag_store, course, current_date, part,
            )
            if per_part_context:
                user_msg = PART_SUMMARY_RAG_PREFIX.format(rag_context=per_part_context)
                logger.debug(f"  Part {part.index} RAG 컨텍스트: {len(per_part_context)}자")

        user_msg += PART_SUMMARY_USER.format(
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


def _get_per_part_rag_context(store, course: str, current_date: str, part: Part) -> str:
    """파트 텍스트에서 핵심 용어를 추출하여 RAG 검색을 수행한다."""
    try:
        from .rag.context import build_rag_context

        key_terms = extract_key_terms(part.text)
        if not key_terms:
            return ""

        return build_rag_context(
            store=store,
            course=course,
            current_date=current_date,
            query_texts=[key_terms],
            max_context_chars=2000,
        )
    except Exception as e:
        logger.debug(f"  Part {part.index} RAG 검색 실패: {e}")
        return ""


def summarize_integrated(
    part_summaries: list[PartSummary],
    course: str,
    date: str,
    cfg: SummarizeConfig,
    api_key: str,
    week_topic: str | None = None,
) -> str:
    """파트별 요약을 통합 요약한다."""
    client = OpenAI(api_key=api_key)

    parts_text = "\n\n".join(
        f"### Part {ps.part_index} ({ps.time_range})\n{ps.summary}"
        for ps in part_summaries
    )

    logger.info("통합 요약 생성 중…")

    topic_hint = ""
    if week_topic:
        topic_hint = f"\n\n참고 — 이번 주차 실라버스 주제: {week_topic}"

    user_msg = INTEGRATED_SUMMARY_USER.format(
        course=course,
        date=date,
        part_summaries=parts_text,
    ) + topic_hint

    result = _call_llm(client, cfg, INTEGRATED_SUMMARY_SYSTEM, user_msg)
    logger.info(f"통합 요약 완료 ({len(result)}자)")
    return result


def summarize(
    parts: list[Part],
    course: str,
    date: str,
    cfg: SummarizeConfig,
    api_key: str,
    rag_store=None,
    week_topic: str | None = None,
) -> SummaryResult:
    """파트별 요약 + 통합 요약을 수행한다."""
    part_summaries = summarize_parts(
        parts, cfg, api_key,
        rag_store=rag_store,
        course=course,
        current_date=date,
    )
    integrated = summarize_integrated(
        part_summaries, course, date, cfg, api_key, week_topic=week_topic,
    )
    return SummaryResult(
        part_summaries=part_summaries,
        integrated_summary=integrated,
        course=course,
        date=date,
    )
