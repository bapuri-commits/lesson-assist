"""이전 강의 컨텍스트 조합.

RAG 검색 결과를 요약 프롬프트에 주입할 컨텍스트로 포맷팅한다.
"""
from __future__ import annotations

from loguru import logger

from ..config import RAGConfig
from .store import LectureStore


def build_rag_context(
    store: LectureStore,
    course: str,
    current_date: str,
    query_texts: list[str],
    max_context_chars: int = 3000,
) -> str:
    """이전 강의 요약에서 관련 컨텍스트를 검색하여 문자열로 반환한다.

    Args:
        store: LectureStore 인스턴스
        course: 과목명
        current_date: 현재 강의 날짜 (검색에서 제외)
        query_texts: 검색 쿼리로 사용할 텍스트 목록 (파트 텍스트 등)
        max_context_chars: 최대 컨텍스트 문자 수

    Returns:
        프롬프트에 주입할 이전 강의 컨텍스트 문자열. 없으면 빈 문자열.
    """
    if not query_texts:
        return ""

    all_hits: list[dict] = []
    seen_texts: set[str] = set()

    for qt in query_texts:
        truncated = qt[:500] if len(qt) > 500 else qt
        hits = store.query(
            course=course,
            query_text=truncated,
            exclude_date=current_date,
        )
        for h in hits:
            text_key = h["text"][:100]
            if text_key not in seen_texts:
                seen_texts.add(text_key)
                all_hits.append(h)

    all_hits.sort(key=lambda x: x["distance"])

    if not all_hits:
        logger.debug(f"RAG 컨텍스트: {course} 이전 강의 없음")
        return ""

    context_parts: list[str] = []
    total_len = 0

    for hit in all_hits:
        entry = f"[{hit['date']}] {hit['text']}"
        if total_len + len(entry) > max_context_chars:
            break
        context_parts.append(entry)
        total_len += len(entry)

    context = "\n\n".join(context_parts)
    dates_used = sorted(set(
        hit["date"] for hit in all_hits[:len(context_parts)]
    ))
    logger.info(f"RAG 컨텍스트: {len(context_parts)}개 청크, 참조 날짜: {dates_used}")

    return context
