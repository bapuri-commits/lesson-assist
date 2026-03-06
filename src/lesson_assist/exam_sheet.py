"""시험 대비 A4 1장 압축 문서 생성.

과목별 누적 강의 요약을 기반으로 시험 직전 5분 복습용 문서를 생성한다.
단일 강의 또는 범위 지정(예: 1~5강)으로 생성 가능.
"""
from __future__ import annotations

import json
from pathlib import Path

from loguru import logger
from openai import OpenAI

from .config import ExamSheetConfig
from .prompts import EXAM_SHEET_SYSTEM, EXAM_SHEET_RANGE_USER, EXAM_SHEET_USER


def _call_llm(client: OpenAI, cfg: ExamSheetConfig, system: str, user: str) -> str:
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
            logger.warning(f"시험 대비 A4 생성 실패 (시도 {attempt + 1}/{cfg.max_retries}): {e}")
            if attempt == cfg.max_retries - 1:
                raise
    return ""


def generate_exam_sheet(
    course: str,
    summaries_dir: Path,
    cfg: ExamSheetConfig,
    api_key: str,
    date_range: tuple[str, str] | None = None,
    output_dir: Path | None = None,
) -> Path:
    """과목의 강의 요약들을 합쳐 시험 대비 A4 문서를 생성한다.

    Args:
        course: 과목명
        summaries_dir: 요약 JSON 파일이 있는 디렉토리
        cfg: ExamSheetConfig
        api_key: OpenAI API key
        date_range: (시작일, 종료일) 범위. None이면 전체.
        output_dir: 출력 디렉토리. None이면 summaries_dir.
    """
    # 새 구조: data/{course}/{date}/summary_v*.json
    summary_files = sorted(summaries_dir.glob("*/summary_v*.json"))

    # 레거시 fallback: data/summaries/*_{course}_summary.json
    if not summary_files:
        legacy_dir = summaries_dir.parent / "summaries"
        summary_files = sorted(legacy_dir.glob(f"*_{course}_summary.json"))

    if not summary_files:
        raise FileNotFoundError(f"{course} 요약 파일 없음: {summaries_dir}")

    # 날짜별로 가장 높은 버전만 사용
    best_per_date: dict[str, Path] = {}
    for sf in summary_files:
        data = json.loads(sf.read_text(encoding="utf-8"))
        lecture_date = data.get("date", "")
        if lecture_date:
            if lecture_date not in best_per_date or sf.name > best_per_date[lecture_date].name:
                best_per_date[lecture_date] = sf

    combined_parts: list[str] = []
    dates_included: list[str] = []

    for lecture_date in sorted(best_per_date):
        if date_range:
            if lecture_date < date_range[0] or lecture_date > date_range[1]:
                continue

        data = json.loads(best_per_date[lecture_date].read_text(encoding="utf-8"))
        dates_included.append(lecture_date)
        combined_parts.append(
            f"### {lecture_date} 강의\n{data.get('integrated_summary', '')}"
        )

    if not combined_parts:
        raise ValueError(f"{course} 범위 내 요약 없음")

    summaries_text = "\n\n---\n\n".join(combined_parts)

    # GPT-4o 컨텍스트 윈도우(~120k 토큰) 대비 안전 한도
    # 한국어 1자 ≈ 1.5~2 토큰, 프롬프트+응답 여유 고려
    MAX_SUMMARY_CHARS = 80000
    if len(summaries_text) > MAX_SUMMARY_CHARS:
        logger.warning(
            f"요약 텍스트가 {len(summaries_text)}자로 한도({MAX_SUMMARY_CHARS}자) 초과. "
            f"최근 강의 우선으로 잘라냅니다."
        )
        # 최근 강의가 뒤에 있으므로 앞쪽을 자름
        summaries_text = "…(이전 강의 일부 생략)…\n\n" + summaries_text[-MAX_SUMMARY_CHARS:]

    client = OpenAI(api_key=api_key)

    if date_range:
        range_desc = f"{date_range[0]} ~ {date_range[1]}"
        user_msg = EXAM_SHEET_RANGE_USER.format(
            course=course,
            range_desc=range_desc,
            summaries=summaries_text,
        )
    else:
        user_msg = EXAM_SHEET_USER.format(
            course=course,
            lecture_count=len(combined_parts),
            summaries=summaries_text,
        )

    logger.info(f"시험 대비 A4 생성: {course}, {len(dates_included)}개 강의")
    result = _call_llm(client, cfg, EXAM_SHEET_SYSTEM, user_msg)

    out = output_dir or summaries_dir
    out.mkdir(parents=True, exist_ok=True)

    range_suffix = f"_{date_range[0]}_{date_range[1]}" if date_range else ""
    filename = f"{course}_exam_sheet{range_suffix}.md"
    out_path = out / filename

    dates_yaml = "\n".join(f"  - {d}" for d in dates_included)
    frontmatter = f"""---
course: {course}
type: exam_sheet
lectures: {len(dates_included)}
dates:
{dates_yaml}
generated_model: {cfg.model}
---

# {course} 시험 대비 A4

"""
    out_path.write_text(frontmatter + result, encoding="utf-8")
    logger.info(f"시험 대비 A4 저장: {out_path}")
    return out_path
