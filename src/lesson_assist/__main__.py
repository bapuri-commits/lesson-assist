"""lesson-assist v2 CLI.

사용법:
    # Phase 2: NotebookLM 패키징
    python -m lesson_assist pack --course "자료구조" --date 2026-03-10
    python -m lesson_assist pack --course "자료구조"
    python -m lesson_assist pack --all

    # Phase 4: Obsidian 노트 생성
    python -m lesson_assist note --course "자료구조" --date 2026-03-10
    python -m lesson_assist note --all

    # v1 레거시 (fallback)
    python -m lesson_assist legacy process --audio "lecture.m4a" --course "자료구조"
    python -m lesson_assist legacy exam --course "자료구조"
"""
from __future__ import annotations

import argparse
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from loguru import logger


def _setup_logging(verbose: bool):
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(
        sys.stderr, level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | {message}",
    )


def _add_common_args(parser: argparse.ArgumentParser):
    parser.add_argument("--config", default=None, help="config.yaml 경로")
    parser.add_argument("--verbose", "-v", action="store_true", help="상세 로그 출력")


def _build_pack_parser(subparsers):
    parser = subparsers.add_parser(
        "pack",
        help="다글로 전사본 + school_sync 데이터 -> NotebookLM 업로드 패키지 생성",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--course", help="과목명")
    group.add_argument("--all", action="store_true", help="모든 과목의 미처리 SRT 패키징")
    parser.add_argument("--date", default=None, help="날짜 (YYYY-MM-DD, 기본: 최신 미처리 자동 감지)")
    parser.add_argument("--no-open", action="store_true", help="완료 시 폴더 자동 열기 비활성화")
    _add_common_args(parser)
    return parser


def _build_note_parser(subparsers):
    parser = subparsers.add_parser(
        "note",
        help="NotebookLM 학습 결과 -> Obsidian 강의노트/학습노트 생성",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--course", help="과목명")
    group.add_argument("--all", action="store_true", help="드롭 폴더의 모든 미처리 파일")
    parser.add_argument("--date", default=None, help="날짜 (YYYY-MM-DD)")
    parser.add_argument("--vault", default=None, help="Obsidian vault 경로 (기본: config)")
    parser.add_argument("--no-daily", action="store_true", help="데일리 노트 연동 비활성화")
    _add_common_args(parser)
    return parser


def _build_legacy_parser(subparsers):
    parser = subparsers.add_parser(
        "legacy",
        help="v1 파이프라인 실행 (faster-whisper + GPT-4o fallback)",
    )
    parser.add_argument("legacy_args", nargs=argparse.REMAINDER, help="v1 CLI 인자")
    return parser


def cmd_pack(args, cfg):
    from .packer import pack_all, pack_course

    auto_open = cfg.notebooklm.auto_open and not getattr(args, "no_open", False)

    if getattr(args, "all", False):
        pack_all(cfg, auto_open=auto_open)
    else:
        pack_course(args.course, cfg, date=args.date, auto_open=auto_open)


def cmd_note(args, cfg):
    logger.info("lesson-assist note 시작")
    # Step 3에서 구현
    logger.warning("note 명령은 아직 구현되지 않았습니다. (Step 3에서 구현 예정)")


def cmd_legacy(args):
    """v1 레거시 CLI로 위임."""
    legacy_argv = args.legacy_args
    if legacy_argv and legacy_argv[0] == "--":
        legacy_argv = legacy_argv[1:]

    if not legacy_argv:
        print("사용법: python -m lesson_assist legacy process --audio ... --course ...")
        print("        python -m lesson_assist legacy exam --course ...")
        return

    original_argv = sys.argv
    try:
        sys.argv = ["lesson-assist"] + legacy_argv
        from .legacy.__main__ import main as legacy_main
        legacy_main()
    finally:
        sys.argv = original_argv


def main():
    parser = argparse.ArgumentParser(
        prog="lesson-assist",
        description="수업 학습 파이프라인 - 다글로 + NotebookLM 기반",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
서브커맨드:
  pack      다글로 전사본 + school_sync 데이터 -> NotebookLM 패키지
  note      NotebookLM 학습 결과 -> Obsidian 노트
  legacy    v1 파이프라인 (faster-whisper + GPT-4o fallback)
        """,
    )
    subparsers = parser.add_subparsers(dest="command")

    _build_pack_parser(subparsers)
    _build_note_parser(subparsers)
    _build_legacy_parser(subparsers)

    args = parser.parse_args()

    if args.command == "legacy":
        cmd_legacy(args)
        return

    if args.command in ("pack", "note"):
        _setup_logging(getattr(args, "verbose", False))

        from .config import load_config
        config_path = getattr(args, "config", None)
        cfg = load_config(config_path)

        if args.command == "pack":
            cmd_pack(args, cfg)
        elif args.command == "note":
            if args.vault:
                cfg.obsidian.vault_path = args.vault
            cmd_note(args, cfg)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
