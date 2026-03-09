"""CLI 진입점.

사용법:
    # 기본 파이프라인 (오디오)
    python -m lesson_assist process --audio "path/to/lecture.m4a" --course "자료구조"

    # 영상 입력 (온라인 수업)
    python -m lesson_assist process --input "path/to/lecture.mp4" --course "자료구조"

    # 시험 대비 A4 생성
    python -m lesson_assist exam --course "자료구조"
    python -m lesson_assist exam --course "자료구조" --range 2026-03-03 2026-04-15

    # 하위 호환: 서브커맨드 없이 --audio 직접 사용
    python -m lesson_assist --audio "path/to/lecture.m4a" --course "자료구조"
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from loguru import logger


def _setup_logging(cfg, verbose: bool):
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(
        sys.stderr, level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | {message}",
    )
    log_dir = Path(cfg.output_dir) / "_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        str(log_dir / "pipeline_{time:YYYY-MM-DD}.log"),
        level="DEBUG", rotation="1 day", encoding="utf-8",
    )


def _add_common_args(parser: argparse.ArgumentParser):
    parser.add_argument("--config", default=None, help="config.yaml 경로")
    parser.add_argument("--verbose", "-v", action="store_true", help="상세 로그 출력")
    parser.add_argument("--output-dir", default=None, help="중간 산출물 저장 경로")


def _add_process_args(parser: argparse.ArgumentParser):
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--audio", nargs="+", help="녹음 파일 경로 (여러 개 가능 — 순서대로 합침)")
    input_group.add_argument("--input", help="입력 파일 경로 (오디오 또는 영상)")
    input_group.add_argument("--transcript", help="외부 전사 파일 경로 (TXT/SRT/VTT — 다글로 등에서 내보낸 파일)")
    parser.add_argument("--course", required=True, help="과목명")
    parser.add_argument("--vault", default=None, help="Obsidian vault 경로")
    parser.add_argument("--date", default=None, help="강의 날짜 (YYYY-MM-DD, 기본: 오늘)")
    parser.add_argument("--model", default=None, help="Whisper 모델 (기본: large-v3)")
    parser.add_argument("--llm", default=None, help="요약 LLM 모델 (기본: gpt-4o)")
    parser.add_argument("--skip-review", action="store_true", help="교정 단계 건너뛰기")
    parser.add_argument("--review", action="store_true", help="교정 파일 반영 후 재실행")
    parser.add_argument("--interactive", action="store_true", help="대화형 교정 모드")
    parser.add_argument("--part-minutes", type=int, default=None, help="파트 분할 기준 (분)")
    parser.add_argument("--no-daily", action="store_true", help="데일리 노트 연동 비활성화")
    parser.add_argument("--no-raw", action="store_true", help="노트에 원문 포함하지 않음")
    parser.add_argument("--no-rag", action="store_true", help="RAG 컨텍스트 비활성화")
    parser.add_argument("--no-anchors", action="store_true", help="Visual Anchors 비활성화")
    parser.add_argument("--no-subtitle", action="store_true", help="자막 생성 비활성화")
    parser.add_argument("--no-clean", action="store_true", help="오디오 전처리 비활성화")
    parser.add_argument("--materials", nargs="+", default=None, help="수업자료 파일 경로 (여러 개 가능)")
    parser.add_argument("--backend", default=None, choices=["local", "runpod"], help="전사 백엔드 (기본: config 설정)")
    _add_common_args(parser)


def _add_exam_args(parser: argparse.ArgumentParser):
    parser.add_argument("--course", required=True, help="과목명")
    parser.add_argument("--range", nargs=2, metavar=("START", "END"), help="날짜 범위 (YYYY-MM-DD YYYY-MM-DD)")
    parser.add_argument("--vault", default=None, help="Obsidian vault 경로")
    _add_common_args(parser)


def cmd_process(args, cfg):
    """process 서브커맨드 처리."""
    if args.vault:
        cfg.vault_path = args.vault
    if args.model:
        cfg.transcribe.model = args.model
    if args.llm:
        cfg.summarize.model = args.llm
    if args.part_minutes:
        cfg.segment.part_minutes = args.part_minutes

    audio_path = None
    transcript_path = None

    if getattr(args, "transcript", None):
        transcript_path = Path(args.transcript).resolve()
        logger.info("lesson-assist 시작 (외부 전사 임포트)")
        logger.info(f"  전사 파일: {transcript_path}")
    elif args.audio:
        if isinstance(args.audio, list) and len(args.audio) > 1:
            from .preprocess import concat_audio
            paths = [Path(f).resolve() for f in args.audio]
            out_dir = Path(cfg.output_dir) / "merged_audio"
            audio_path = concat_audio(paths, out_dir)
            logger.info(f"  {len(paths)}개 파일 합침 → {audio_path.name}")
        else:
            raw = args.audio[0] if isinstance(args.audio, list) else args.audio
            audio_path = Path(raw).resolve()
        logger.info("lesson-assist 시작")
        logger.info(f"  입력: {audio_path}")
    else:
        audio_path = Path(args.input).resolve()
        logger.info("lesson-assist 시작")
        logger.info(f"  입력: {audio_path}")
    logger.info(f"  과목: {args.course}")
    logger.info(f"  날짜: {args.date or '오늘'}")
    logger.info(f"  전사 모델: {cfg.transcribe.model}")
    logger.info(f"  요약 모델: {cfg.summarize.model}")
    logger.info(f"  볼트: {cfg.vault_path}")
    backend = getattr(args, "backend", None)
    if backend:
        cfg.transcribe.backend = backend

    material_paths = None
    if getattr(args, "materials", None):
        material_paths = [Path(m).resolve() for m in args.materials]

    logger.info(f"  RAG: {'OFF' if args.no_rag else 'ON'}")
    logger.info(f"  Visual Anchors: {'OFF' if args.no_anchors else 'ON'}")
    logger.info(f"  오디오 전처리: {'OFF' if args.no_clean else 'ON'}")
    if material_paths:
        logger.info(f"  수업자료: {len(material_paths)}개 지정")

    from .pipeline import run_pipeline

    note_path = run_pipeline(
        audio_path=audio_path,
        course=args.course,
        cfg=cfg,
        date=args.date,
        skip_review=args.skip_review,
        review_mode=args.review,
        interactive=args.interactive,
        no_daily=args.no_daily,
        include_raw=not args.no_raw,
        no_rag=args.no_rag,
        no_anchors=args.no_anchors,
        no_subtitle=args.no_subtitle,
        no_clean=args.no_clean,
        material_paths=material_paths,
        transcript_path=transcript_path,
    )
    logger.info(f"노트 생성 완료: {note_path}")


def cmd_exam(args, cfg):
    """exam 서브커맨드 처리."""
    if args.vault:
        cfg.vault_path = args.vault

    logger.info(f"시험 대비 A4 생성: {args.course}")

    date_range = tuple(args.range) if args.range else None

    from .pipeline import run_exam_sheet

    out_path = run_exam_sheet(
        course=args.course,
        cfg=cfg,
        date_range=date_range,
    )
    logger.info(f"시험 대비 A4 저장: {out_path}")


def main():
    parser = argparse.ArgumentParser(
        prog="lesson-assist",
        description="수업 녹음 → 전사 → 요약 → Obsidian 노트 자동 생성",
    )
    subparsers = parser.add_subparsers(dest="command")

    # process 서브커맨드
    process_parser = subparsers.add_parser("process", help="강의 녹음/영상 처리")
    _add_process_args(process_parser)

    # exam 서브커맨드
    exam_parser = subparsers.add_parser("exam", help="시험 대비 A4 생성")
    _add_exam_args(exam_parser)

    # 하위 호환: 서브커맨드 없이 --audio 직접 사용
    parser.add_argument("--audio", nargs="+", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--input", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--transcript", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--course", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--vault", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--date", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--config", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--model", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--llm", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--skip-review", action="store_true", default=False, help=argparse.SUPPRESS)
    parser.add_argument("--review", action="store_true", default=False, help=argparse.SUPPRESS)
    parser.add_argument("--interactive", action="store_true", default=False, help=argparse.SUPPRESS)
    parser.add_argument("--part-minutes", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--no-daily", action="store_true", default=False, help=argparse.SUPPRESS)
    parser.add_argument("--no-raw", action="store_true", default=False, help=argparse.SUPPRESS)
    parser.add_argument("--no-rag", action="store_true", default=False, help=argparse.SUPPRESS)
    parser.add_argument("--no-anchors", action="store_true", default=False, help=argparse.SUPPRESS)
    parser.add_argument("--no-subtitle", action="store_true", default=False, help=argparse.SUPPRESS)
    parser.add_argument("--no-clean", action="store_true", default=False, help=argparse.SUPPRESS)
    parser.add_argument("--materials", nargs="+", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--backend", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--verbose", "-v", action="store_true", default=False, help=argparse.SUPPRESS)
    parser.add_argument("--output-dir", default=None, help=argparse.SUPPRESS)

    args = parser.parse_args()

    from .config import load_config

    config_path = getattr(args, "config", None)
    cfg = load_config(config_path)

    if args.output_dir:
        cfg.output_dir = args.output_dir

    _setup_logging(cfg, getattr(args, "verbose", False))

    try:
        if args.command == "process":
            cmd_process(args, cfg)
        elif args.command == "exam":
            cmd_exam(args, cfg)
        elif args.audio or args.input or args.transcript:
            if not args.course:
                parser.error("--course는 필수입니다.")
            cmd_process(args, cfg)
        else:
            parser.print_help()
            sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("사용자에 의해 중단됨")
        sys.exit(1)
    except Exception as e:
        logger.error(f"실패: {e}")
        raise


if __name__ == "__main__":
    main()
