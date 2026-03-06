from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from loguru import logger
from openai import OpenAI

from .config import SummarizeConfig
from .prompts import ACTIONS_SYSTEM, ACTIONS_USER
from .transcribe import TranscriptResult


@dataclass
class ActionItem:
    type: str       # 과제 | 시험 | 일정 | 공지
    content: str
    deadline: str | None
    priority: str   # high | medium | low


@dataclass
class ActionsResult:
    items: list[ActionItem]
    course: str
    date: str

    def save(self, out_dir: Path, file_id: str) -> Path:
        """레거시 호환 저장."""
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{file_id}_actions.json"
        return self.save_to(path)

    def save_to(self, path: Path) -> Path:
        """지정된 경로에 액션 아이템을 저장한다."""
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "course": self.course,
            "date": self.date,
            "items": [
                {"type": i.type, "content": i.content, "deadline": i.deadline, "priority": i.priority}
                for i in self.items
            ],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"액션 아이템 저장: {path} ({len(self.items)}개)")
        return path


def extract_actions(
    transcript: TranscriptResult,
    course: str,
    date: str,
    cfg: SummarizeConfig,
    api_key: str,
) -> ActionsResult:
    """전사 전문에서 과제/시험/일정/공지 액션 아이템을 추출한다."""
    client = OpenAI(api_key=api_key)

    # 전사 전문이 너무 길면 앞뒤 + 중간 샘플링으로 토큰 절약
    full_text = transcript.full_text
    if len(full_text) > 30000:
        # 앞 10000자 + 뒤 10000자 + 중간에서 키워드 주변 추출
        full_text = _truncate_with_keyword_context(full_text)

    user_msg = ACTIONS_USER.format(course=course, date=date, text=full_text)

    logger.info("액션 아이템 추출 중…")
    for attempt in range(cfg.max_retries):
        try:
            resp = client.chat.completions.create(
                model=cfg.model,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": ACTIONS_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
            )
            raw = resp.choices[0].message.content
            items = _parse_actions(raw)
            logger.info(f"액션 아이템 {len(items)}개 추출 완료")
            return ActionsResult(items=items, course=course, date=date)
        except Exception as e:
            logger.warning(f"액션 추출 실패 (시도 {attempt + 1}/{cfg.max_retries}): {e}")
            if attempt == cfg.max_retries - 1:
                raise

    return ActionsResult(items=[], course=course, date=date)


def _parse_actions(raw: str) -> list[ActionItem]:
    """LLM 응답에서 JSON 배열을 파싱한다."""
    # ```json ... ``` 블록 추출
    cleaned = raw.strip()
    if "```" in cleaned:
        start = cleaned.find("[")
        end = cleaned.rfind("]") + 1
        if start != -1 and end > start:
            cleaned = cleaned[start:end]

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning(f"액션 JSON 파싱 실패: {raw[:200]}")
        return []

    if not isinstance(data, list):
        return []

    items = []
    for d in data:
        items.append(ActionItem(
            type=d.get("type", "공지"),
            content=d.get("content", ""),
            deadline=d.get("deadline"),
            priority=d.get("priority", "medium"),
        ))
    return items


_ACTION_KEYWORDS = ["과제", "레포트", "제출", "숙제", "시험", "퀴즈", "중간고사", "기말",
                    "범위", "휴강", "보강", "공지", "이클래스", "마감"]


def _truncate_with_keyword_context(text: str, max_len: int = 25000) -> str:
    """긴 텍스트에서 액션 키워드 주변을 우선 포함하여 잘라낸다."""
    head = text[:8000]
    tail = text[-8000:]
    middle = text[8000:-8000]

    keyword_chunks = []
    for kw in _ACTION_KEYWORDS:
        idx = 0
        while True:
            pos = middle.find(kw, idx)
            if pos == -1:
                break
            start = max(0, pos - 300)
            end = min(len(middle), pos + 300)
            keyword_chunks.append(middle[start:end])
            idx = pos + len(kw)

    middle_sample = "\n…\n".join(keyword_chunks[:10]) if keyword_chunks else middle[:4000]
    result = head + "\n…(중략)…\n" + middle_sample + "\n…(중략)…\n" + tail
    return result[:max_len]
