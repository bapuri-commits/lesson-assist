"""Jupyter Notebook (.ipynb) -> 마크다운 변환.

코랩/Jupyter 노트북에서 학습에 필요한 내용만 추출하여
NotebookLM에 올리기 좋은 마크다운으로 변환한다.

추출 대상:
  - 마크다운 셀: 그대로 (교수님의 설명, 개념 정리)
  - 코드 셀: 코드 블록으로 (실습 예제)
  - 출력 셀: 텍스트 출력만 (이미지/바이너리 제외)
제거 대상:
  - 메타데이터 (kernel info, execution count, cell id 등)
  - 이미지 출력 (base64 data)
"""
from __future__ import annotations

import json
from pathlib import Path

from loguru import logger


def convert_ipynb_to_md(ipynb_path: Path) -> str:
    """ipynb 파일을 마크다운 문자열로 변환한다."""
    data = json.loads(ipynb_path.read_text(encoding="utf-8-sig"))

    cells = data.get("cells", [])
    if not cells:
        logger.warning(f"빈 노트북: {ipynb_path.name}")
        return ""

    sections: list[str] = []

    for cell in cells:
        cell_type = cell.get("cell_type", "")
        source = "".join(cell.get("source", []))

        if not source.strip():
            continue

        if cell_type == "markdown":
            sections.append(source)

        elif cell_type == "code":
            sections.append(f"```python\n{source}\n```")

            text_output = _extract_text_output(cell)
            if text_output:
                sections.append(f"**실행 결과:**\n```\n{text_output}\n```")

    if not sections:
        return ""

    header = f"# {ipynb_path.stem}\n\n> 원본: {ipynb_path.name} (Jupyter Notebook)\n"
    return header + "\n\n".join(sections)


def _extract_text_output(cell: dict) -> str:
    """코드 셀의 출력에서 텍스트만 추출한다."""
    outputs = cell.get("outputs", [])
    if not outputs:
        return ""

    text_parts: list[str] = []

    for output in outputs:
        output_type = output.get("output_type", "")

        if output_type == "stream":
            text_parts.append("".join(output.get("text", [])))

        elif output_type in ("execute_result", "display_data"):
            out_data = output.get("data", {})
            if "text/plain" in out_data:
                plain = "".join(out_data["text/plain"])
                text_parts.append(plain)

        elif output_type == "error":
            ename = output.get("ename", "Error")
            evalue = output.get("evalue", "")
            text_parts.append(f"[Error: {ename}] {evalue}")

    result = "\n".join(text_parts).strip()
    if len(result) > 2000:
        result = result[:2000] + "\n... (출력 생략)"
    return result


def find_ipynb_files(downloads_dir: Path, course: str) -> list[Path]:
    """school_sync downloads에서 과목의 .ipynb 파일을 찾는다."""
    if not downloads_dir.exists():
        return []

    results: list[Path] = []
    for course_dir in downloads_dir.iterdir():
        if not course_dir.is_dir():
            continue
        if course not in course_dir.name:
            continue
        for f in course_dir.rglob("*.ipynb"):
            results.append(f)

    return sorted(results)


def convert_and_save(ipynb_path: Path, output_dir: Path) -> Path | None:
    """ipynb를 변환하여 output_dir에 .md로 저장한다.

    이미 변환된 파일이 있고 원본보다 새로우면 스킵한다.
    """
    md_path = output_dir / f"{ipynb_path.stem}.md"

    if md_path.exists() and md_path.stat().st_mtime >= ipynb_path.stat().st_mtime:
        logger.info(f"  ipynb 변환 스킵 (최신): {md_path.name}")
        return md_path

    md_content = convert_ipynb_to_md(ipynb_path)
    if not md_content:
        return None

    md_path.write_text(md_content, encoding="utf-8")
    logger.info(f"  ipynb 변환: {ipynb_path.name} -> {md_path.name} ({len(md_content)}자)")
    return md_path
