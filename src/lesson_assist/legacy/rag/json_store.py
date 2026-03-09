"""JSON 파일 기반 벡터 저장소.

ChromaDB가 Python 버전 호환 문제 등으로 사용 불가할 때 fallback으로 사용.
OpenAI 임베딩 + numpy 코사인 유사도로 동작한다.
한 학기 분량(~30 강의)에서 충분한 성능.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from loguru import logger
from openai import OpenAI

from ..config import RAGConfig


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    a_arr = np.array(a)
    b_arr = np.array(b)
    dot = np.dot(a_arr, b_arr)
    norm = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
    if norm == 0:
        return 0.0
    return float(dot / norm)


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
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


class JsonLectureStore:
    """JSON 파일 기반 벡터 저장소. LectureStore와 동일 인터페이스."""

    def __init__(self, cfg: RAGConfig, api_key: str):
        self.cfg = cfg
        self._openai = OpenAI(api_key=api_key)
        self._db_path = Path(cfg.db_path)
        self._db_path.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, list[dict]] = {}

    def _collection_file(self, course: str) -> Path:
        import hashlib
        import re
        safe = re.sub(r"[^a-zA-Z0-9]", "", course)
        h = hashlib.md5(course.encode()).hexdigest()[:8]
        return self._db_path / f"lecture_{safe}_{h}.json"

    def _load_collection(self, course: str) -> list[dict]:
        if course in self._data:
            return self._data[course]
        fp = self._collection_file(course)
        if fp.exists():
            self._data[course] = json.loads(fp.read_text(encoding="utf-8"))
        else:
            self._data[course] = []
        return self._data[course]

    def _save_collection(self, course: str) -> None:
        fp = self._collection_file(course)
        fp.write_text(
            json.dumps(self._data.get(course, []), ensure_ascii=False),
            encoding="utf-8",
        )

    def _embed(self, texts: list[str]) -> list[list[float]]:
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
        collection = self._load_collection(course)

        # 동일 날짜 기존 데이터 삭제
        collection[:] = [e for e in collection if e.get("date") != date]

        texts: list[str] = []
        metas: list[dict] = []

        for i, chunk in enumerate(_chunk_text(integrated_summary, self.cfg.chunk_size, self.cfg.chunk_overlap)):
            texts.append(chunk)
            metas.append({"course": course, "date": date, "type": "integrated_summary", "chunk_index": i})

        if part_summaries:
            for pi, pt in enumerate(part_summaries):
                for i, chunk in enumerate(_chunk_text(pt, self.cfg.chunk_size, self.cfg.chunk_overlap)):
                    texts.append(chunk)
                    metas.append({"course": course, "date": date, "type": "part_summary", "part_index": pi + 1, "chunk_index": i})

        if not texts:
            return 0

        embeddings = self._embed(texts)
        for text, emb, meta in zip(texts, embeddings, metas):
            collection.append({"text": text, "embedding": emb, **meta})

        self._save_collection(course)
        logger.info(f"RAG 저장 (JSON): {course} {date} → {len(texts)}개 청크")
        return len(texts)

    def add_material(
        self,
        course: str,
        pages: list[str],
        source_filename: str,
    ) -> int:
        collection = self._load_collection(course)

        if any(e.get("source") == source_filename for e in collection):
            logger.debug(f"이미 저장된 자료: {source_filename}")
            return 0

        texts: list[str] = []
        metas: list[dict] = []
        for page in pages:
            for i, chunk in enumerate(_chunk_text(page, self.cfg.chunk_size, self.cfg.chunk_overlap)):
                texts.append(chunk)
                metas.append({"course": course, "date": "_material", "type": "eclass_material", "source": source_filename, "chunk_index": i})

        if not texts:
            return 0

        embeddings = self._embed(texts)
        for text, emb, meta in zip(texts, embeddings, metas):
            collection.append({"text": text, "embedding": emb, **meta})

        self._save_collection(course)
        logger.info(f"자료 RAG 저장 (JSON): {source_filename} → {len(texts)}개 청크")
        return len(texts)

    def query(
        self,
        course: str,
        query_text: str,
        top_k: int | None = None,
        exclude_date: str | None = None,
    ) -> list[dict]:
        collection = self._load_collection(course)
        if not collection:
            return []

        k = top_k or self.cfg.top_k
        query_emb = self._embed([query_text])[0]

        scored: list[tuple[float, dict]] = []
        for entry in collection:
            if exclude_date and entry.get("date") == exclude_date:
                continue
            if "embedding" not in entry:
                continue
            sim = _cosine_similarity(query_emb, entry["embedding"])
            scored.append((sim, entry))

        scored.sort(key=lambda x: x[0], reverse=True)

        return [
            {"text": e["text"], "date": e.get("date", ""), "type": e.get("type", ""), "distance": 1.0 - sim}
            for sim, e in scored[:k]
        ]

    def get_course_dates(self, course: str) -> list[str]:
        collection = self._load_collection(course)
        return sorted(set(e["date"] for e in collection if e.get("date") and e["date"] != "_material"))
