"""기존 flat 데이터를 새 과목/날짜 계층 구조로 마이그레이션한다.

사용법:
    python migrate_data.py              # 기본 data/ 디렉토리
    python migrate_data.py --data-dir path/to/data
    python migrate_data.py --dry-run    # 실제 이동 없이 미리보기
"""
import argparse
import re
import shutil
from pathlib import Path


FILE_ID_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})_(.+?)_(.+)$")
FILE_ID_SIMPLE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(.+)$")


def parse_file_id(filename: str) -> tuple[str, str, str] | None:
    """파일명에서 (날짜, 과목, 나머지)를 추출한다."""
    stem = Path(filename).stem
    m = FILE_ID_PATTERN.match(stem)
    if m:
        return m.group(1), m.group(2), m.group(3)
    return None


def migrate(data_dir: Path, dry_run: bool = False) -> None:
    moves: list[tuple[Path, Path]] = []

    # transcripts/
    transcripts_dir = data_dir / "transcripts"
    if transcripts_dir.exists():
        for f in transcripts_dir.iterdir():
            if not f.is_file():
                continue
            parsed = parse_file_id(f.name)
            if not parsed:
                continue
            date, course, rest = parsed

            if rest == "raw":
                target = data_dir / course / date / "transcript_raw.txt"
            elif rest == "segments":
                target = data_dir / course / date / "transcript_segments.json"
            else:
                target = data_dir / course / date / f.name
            moves.append((f, target))

    # reviews/
    reviews_dir = data_dir / "reviews"
    if reviews_dir.exists():
        for f in reviews_dir.iterdir():
            if not f.is_file():
                continue
            parsed = parse_file_id(f.name)
            if not parsed:
                continue
            date, course, _ = parsed
            target = data_dir / course / date / "review.jsonl"
            moves.append((f, target))

    # parts/
    parts_dir = data_dir / "parts"
    if parts_dir.exists():
        for f in parts_dir.iterdir():
            if not f.is_file():
                continue
            parsed = parse_file_id(f.name)
            if not parsed:
                continue
            date, course, rest = parsed
            part_match = re.match(r"part_(\d+)", rest)
            if part_match:
                target = data_dir / course / date / "parts" / f"part_{part_match.group(1)}.txt"
            else:
                target = data_dir / course / date / "parts" / f.name
            moves.append((f, target))

    # subtitles/
    subtitles_dir = data_dir / "subtitles"
    if subtitles_dir.exists():
        for f in subtitles_dir.iterdir():
            if not f.is_file():
                continue
            stem = f.stem
            m = FILE_ID_SIMPLE.match(stem)
            if not m:
                continue
            date, course = m.group(1), m.group(2)
            target = data_dir / course / date / f"subtitle{f.suffix}"
            moves.append((f, target))

    # summaries/
    summaries_dir = data_dir / "summaries"
    if summaries_dir.exists():
        for f in summaries_dir.iterdir():
            if not f.is_file():
                continue
            parsed = parse_file_id(f.name)
            if not parsed:
                continue
            date, course, rest = parsed
            if rest == "summary":
                target = data_dir / course / date / "summary_v1.json"
            elif rest == "actions":
                target = data_dir / course / date / "actions_v1.json"
            else:
                target = data_dir / course / date / f.name
            moves.append((f, target))

    # chroma_db/ → _rag/
    chroma_dir = data_dir / "chroma_db"
    if chroma_dir.exists():
        for f in chroma_dir.iterdir():
            if f.is_file():
                target = data_dir / "_rag" / f.name
                moves.append((f, target))

    # logs/ → _logs/
    logs_dir = data_dir / "logs"
    if logs_dir.exists():
        for f in logs_dir.iterdir():
            if f.is_file():
                target = data_dir / "_logs" / f.name
                moves.append((f, target))

    if not moves:
        print("마이그레이션할 파일이 없습니다.")
        return

    print(f"마이그레이션 대상: {len(moves)}개 파일")
    print()

    for src, dst in moves:
        rel_src = src.relative_to(data_dir)
        rel_dst = dst.relative_to(data_dir)
        print(f"  {rel_src}  →  {rel_dst}")

    if dry_run:
        print(f"\n[DRY RUN] 실제 이동하지 않음.")
        return

    print()
    for src, dst in moves:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))

    # 빈 디렉토리 정리
    for old_dir in [transcripts_dir, reviews_dir, parts_dir, subtitles_dir, summaries_dir, chroma_dir, logs_dir]:
        if old_dir.exists() and not any(old_dir.iterdir()):
            old_dir.rmdir()
            print(f"  빈 디렉토리 삭제: {old_dir.name}/")

    print(f"\n마이그레이션 완료: {len(moves)}개 파일 이동됨.")


def main():
    parser = argparse.ArgumentParser(description="lesson-assist 데이터 마이그레이션")
    parser.add_argument("--data-dir", default="data", help="데이터 디렉토리 경로")
    parser.add_argument("--dry-run", action="store_true", help="실제 이동 없이 미리보기")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"디렉토리가 존재하지 않습니다: {data_dir}")
        return

    migrate(data_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
