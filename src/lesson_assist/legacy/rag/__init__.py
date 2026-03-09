"""강의 컨텍스트 RAG — 벡터 저장/검색.

ChromaDB를 우선 시도하고, Python 호환 문제 등으로 실패하면
JSON 파일 기반 fallback 저장소를 사용한다.
"""
from .context import build_rag_context

_USE_JSON_FALLBACK = False


def LectureStore(cfg, api_key: str):
    """RAG store 팩토리. ChromaDB 또는 JSON fallback을 반환한다."""
    global _USE_JSON_FALLBACK

    if not _USE_JSON_FALLBACK:
        try:
            from .store import LectureStore as ChromaStore
            store = ChromaStore(cfg, api_key)
            # ChromaDB 초기화 테스트
            _ = store.client
            return store
        except Exception as e:
            from loguru import logger
            logger.warning(f"ChromaDB 사용 불가 → JSON fallback으로 전환: {e}")
            _USE_JSON_FALLBACK = True

    from .json_store import JsonLectureStore
    return JsonLectureStore(cfg, api_key)


__all__ = ["LectureStore", "build_rag_context"]
