from __future__ import annotations

from pathlib import Path

from loguru import logger

from .actions import ActionsResult
from .review import ReviewCandidate
from .summarize import SummaryResult
from .transcribe import TranscriptResult


def write_note(
    summary: SummaryResult,
    transcript: TranscriptResult,
    actions: ActionsResult,
    review_candidates: list[ReviewCandidate],
    vault_path: str,
    course: str,
    date: str,
    audio_filename: str,
    summarize_model: str = "gpt-4o",
    include_raw: bool = True,
) -> Path:
    """Obsidian 강의 노트 마크다운을 생성한다."""
    note_dir = Path(vault_path) / "3_Areas" / "Lectures" / course
    note_dir.mkdir(parents=True, exist_ok=True)
    note_path = note_dir / f"{date}_{course}.md"

    duration_min = int(transcript.audio_duration / 60)

    lines: list[str] = []

    # Frontmatter
    lines.append("---")
    lines.append(f"date: {date}")
    lines.append(f"course: {course}")
    lines.append(f"source_audio: {audio_filename}")
    lines.append(f"duration_min: {duration_min}")
    lines.append(f"transcribe_model: {transcript.model}")
    lines.append(f"summarize_model: {summarize_model}")
    lines.append(f"tags: [lecture, {course}]")
    lines.append("---")
    lines.append("")

    # 제목
    lines.append(f"# {date} {course}")
    lines.append("")

    # 통합 요약
    lines.append("## 통합 요약")
    lines.append("")
    lines.append(summary.integrated_summary)
    lines.append("")

    # 파트별 요약
    lines.append("## 파트별 요약")
    lines.append("")
    for ps in summary.part_summaries:
        lines.append(f"### Part {ps.part_index} ({ps.time_range})")
        lines.append("")
        lines.append(ps.summary)
        lines.append("")

    # 액션 아이템
    if actions.items:
        lines.append("## 액션 아이템")
        lines.append("")
        for item in actions.items:
            deadline_str = f" (마감: {item.deadline})" if item.deadline else ""
            lines.append(f"- [ ] **[{item.type}]** {item.content}{deadline_str}")
        lines.append("")

    # 교정 후보 (미처리분)
    pending = [c for c in review_candidates if c.action == "pending"]
    if pending:
        lines.append("## 교정 후보")
        lines.append("")
        lines.append("> 전사 품질이 낮은 구간입니다. 필요시 원문을 확인하고 교정하세요.")
        lines.append("")
        for c in pending[:20]:  # 최대 20개
            lines.append(f"- **[{c.start}~{c.end}]** ({c.reason})")
            lines.append(f"  - \"{c.original}\"")
        lines.append("")

    # 원문
    if include_raw:
        lines.append("## 원문")
        lines.append("")
        lines.append("> [!note]- 전체 전사 원문 (접기)")
        for seg in transcript.segments:
            lines.append(f"> [{seg.start_str}] {seg.text.strip()}")
        lines.append("")

    content = "\n".join(lines)
    note_path.write_text(content, encoding="utf-8")
    logger.info(f"강의 노트 생성: {note_path}")
    return note_path
