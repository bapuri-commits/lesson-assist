"""ChromaDB 기반 강의 요약 벡터 저장소.

과목별 컬렉션으로 관리하며, 강의 요약을 청크 단위로 임베딩하여 저장한다.
새 강의 요약 시 이전 강의의 관련 부분을 컨텍스트로 검색한다.
"""
from __future__ import annotations

from pathlib import Path

from loguru import logger
from openai import OpenAI

from ..config import RAGConfig


def _sanitize_collection_name(name: str) -> str:
    """ChromaDB 컬렉션 이름 규칙에 맞게 정규화.

    ChromaDB 요구사항: [a-zA-Z0-9][a-zA-Z0-9._-]{1,61}[a-zA-Z0-9]
    한국어 과목명은 해시로 변환하여 ASCII로 만든다.
    """
    import hashlib
    import re

    has_non_ascii = bool(re.search(r"[^\x00-\x7F]", name))
    if has_non_ascii:
        ascii_part = re.sub(r"[^a-zA-Z0-9]", "", name)
        hash_suffix = hashlib.md5(name.encode()).hexdigest()[:12]
        sanitized = f"{ascii_part}_{hash_suffix}" if ascii_part else f"col_{hash_suffix}"
    else:
        sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", name)

    sanitized = re.sub(r"_+", "_", sanitized).strip("_-.")
    if not sanitized or not sanitized[0].isalnum():
        sanitized = "c" + sanitized
    if not sanitized[-1].isalnum():
        sanitized = sanitized + "0"
    if len(sanitized) < 3:
        sanitized = sanitized + "_col"
    if len(sanitized) > 63:
        sanitized = sanitized[:63]
        if not sanitized[-1].isalnum():
            sanitized = sanitized[:62] + "0"
    return sanitized


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """텍스트를 겹침 있는 청크로 분할한다."""
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        if end >= len(text):
            break
        start = end - overlap

    return chunks


class LectureStore:
    """과목별 강의 요약 벡터 저장소."""

    def __init__(self, cfg: RAGConfig, api_key: str):
        self.cfg = cfg
        self.api_key = api_key
        self._client = None
        self._openai = OpenAI(api_key=api_key)

    @property
    def client(self):
        if self._client is None:
            import chromadb
            db_path = Path(self.cfg.db_path)
            db_path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(db_path))
        return self._client

    def _get_collection(self, course: str):
        name = _sanitize_collection_name(f"lecture_{course}")
        return self.client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    def _embed(self, texts: list[str]) -> list[list[float]]:
        """OpenAI 임베딩 API로 텍스트를 벡터화한다."""
        resp = self._openai.embeddings.create(
            model=self.cfg.embedding_model,
            input=texts,
        )
        return [d.embedding for d in resp.data]

    def add_lecture(
        self,
        course: str,
        date: str,
        integrated_summary: str,
        part_summaries: list[str] | None = None,
    ) -> int:
        """강의 요약을 벡터 DB에 저장한다.

        Returns:
            저장된 청크 수.
        """
        collection = self._get_collection(course)

        texts_to_store: list[str] = []
        metadatas: list[dict] = []

        summary_chunks = _chunk_text(
            integrated_summary,
            self.cfg.chunk_size,
            self.cfg.chunk_overlap,
        )
        for i, chunk in enumerate(summary_chunks):
            texts_to_store.append(chunk)
            metadatas.append({
                "course": course,
                "date": date,
                "type": "integrated_summary",
                "chunk_index": i,
            })

        if part_summaries:
            for part_idx, part_text in enumerate(part_summaries):
                part_chunks = _chunk_text(
                    part_text,
                    self.cfg.chunk_size,
                    self.cfg.chunk_overlap,
                )
                for i, chunk in enumerate(part_chunks):
                    texts_to_store.append(chunk)
                    metadatas.append({
                        "course": course,
                        "date": date,
                        "type": "part_summary",
                        "part_index": part_idx + 1,
                        "chunk_index": i,
                    })

        if not texts_to_store:
            return 0

        embeddings = self._embed(texts_to_store)
        safe_course = _sanitize_collection_name(course)
        ids = [f"{date}_{safe_course}_{i}" for i in range(len(texts_to_store))]

        # 동일 날짜의 기존 청크를 모두 삭제 (stale 청크 방지)
        try:
            existing = collection.get(where={"date": date})
            if existing and existing["ids"]:
                collection.delete(ids=existing["ids"])
        except Exception:
            pass

        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts_to_store,
            metadatas=metadatas,
        )

        logger.info(f"RAG 저장: {course} {date} → {len(texts_to_store)}개 청크")
        return len(texts_to_store)

    def add_material(
        self,
        course: str,
        pages: list[str],
        source_filename: str,
    ) -> int:
        """강의자료(PDF/PPT) 텍스트를 벡터 DB에 저장한다.

        이미 같은 파일명으로 저장된 데이터가 있으면 건너뛴다.

        Returns:
            저장된 청크 수.
        """
        collection = self._get_collection(course)

        # 중복 방지: 같은 source_filename이 이미 있으면 스킵
        try:
            existing = collection.get(where={"source": source_filename})
            if existing and existing["ids"]:
                logger.debug(f"이미 저장된 자료: {source_filename} ({len(existing['ids'])}개 청크)")
                return 0
        except Exception:
            pass

        texts_to_store: list[str] = []
        metadatas: list[dict] = []

        for page_text in pages:
            chunks = _chunk_text(page_text, self.cfg.chunk_size, self.cfg.chunk_overlap)
            for i, chunk in enumerate(chunks):
                texts_to_store.append(chunk)
                metadatas.append({
                    "course": course,
                    "date": "_material",
                    "type": "eclass_material",
                    "source": source_filename,
                    "chunk_index": i,
                })

        if not texts_to_store:
            return 0

        embeddings = self._embed(texts_to_store)
        safe_name = _sanitize_collection_name(source_filename)
        ids = [f"mat_{safe_name}_{i}" for i in range(len(texts_to_store))]

        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts_to_store,
            metadatas=metadatas,
        )

        logger.info(f"자료 RAG 저장: {source_filename} → {len(texts_to_store)}개 청크")
        return len(texts_to_store)

    def query(
        self,
        course: str,
        query_text: str,
        top_k: int | None = None,
        exclude_date: str | None = None,
    ) -> list[dict]:
        """과목의 이전 강의에서 관련 청크를 검색한다.

        Returns:
            [{"text": str, "date": str, "type": str, "distance": float}, ...]
        """
        collection = self._get_collection(course)

        if collection.count() == 0:
            return []

        k = top_k or self.cfg.top_k
        query_embedding = self._embed([query_text])[0]

        where_filter = None
        if exclude_date:
            where_filter = {"date": {"$ne": exclude_date}}

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(k, collection.count()),
            where=where_filter,
        )

        hits: list[dict] = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                dist = results["distances"][0][i] if results["distances"] else 0.0
                hits.append({
                    "text": doc,
                    "date": meta.get("date", ""),
                    "type": meta.get("type", ""),
                    "distance": dist,
                })

        logger.debug(f"RAG 검색: {course} → {len(hits)}개 결과")
        return hits

    def get_course_dates(self, course: str) -> list[str]:
        """과목에 저장된 강의 날짜 목록을 반환한다."""
        collection = self._get_collection(course)
        if collection.count() == 0:
            return []

        all_meta = collection.get()
        dates = set()
        if all_meta and all_meta["metadatas"]:
            for meta in all_meta["metadatas"]:
                if "date" in meta:
                    dates.add(meta["date"])
        return sorted(dates)
