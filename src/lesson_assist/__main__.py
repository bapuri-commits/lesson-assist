"""CLI 진입점.

사용법:
    python -m lesson_assist --audio "path/to/lecture.m4a" --course "자료구조"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger


def main():
    parser = argparse.ArgumentParser(
        prog="lesson-assist",
        description="수업 녹음 → 전사 → 요약 → Obsidian 노트 자동 생성",
    )
    parser.add_argument("--audio", required=True, help="녹음 파일 경로")
    parser.add_argument("--course", required=True, help="과목명")
    parser.add_argument("--vault", default=None, help="Obsidian vault 경로 (config.yaml 우선)")
    parser.add_argument("--date", default=None, help="강의 날짜 (YYYY-MM-DD, 기본: 오늘)")
    parser.add_argument("--config", default=None, help="config.yaml 경로")
    parser.add_argument("--model", default=None, help="Whisper 모델 (기본: large-v3)")
    parser.add_argument("--llm", default=None, help="요약 LLM 모델 (기본: gpt-4o)")
    parser.add_argument("--skip-review", action="store_true", help="교정 단계 건너뛰기")
    parser.add_argument("--review", action="store_true", help="교정 파일 반영 후 요약부터 재실행")
    parser.add_argument("--interactive", action="store_true", help="대화형 교정 모드")
    parser.add_argument("--part-minutes", type=int, default=None, help="파트 분할 기준 (분)")
    parser.add_argument("--no-daily", action="store_true", help="데일리 노트 연동 비활성화")
    parser.add_argument("--no-raw", action="store_true", help="노트에 원문 포함하지 않음")
    parser.add_argument("--output-dir", default=None, help="중간 산출물 저장 경로")
    parser.add_argument("--verbose", "-v", action="store_true", help="상세 로그 출력")

    args = parser.parse_args()

    # 설정 로드
    from .config import load_config

    cfg = load_config(args.config)

    # 로깅 설정
    logger.remove()
    level = "DEBUG" if args.verbose else "INFO"
    logger.add(sys.stderr, level=level, format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | {message}")
    log_dir = Path(cfg.output_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(str(log_dir / "pipeline_{time:YYYY-MM-DD}.log"), level="DEBUG", rotation="1 day", encoding="utf-8")

    # CLI 인자로 오버라이드
    if args.vault:
        cfg.vault_path = args.vault
    if args.model:
        cfg.transcribe.model = args.model
    if args.llm:
        cfg.summarize.model = args.llm
    if args.part_minutes:
        cfg.segment.part_minutes = args.part_minutes
    if args.output_dir:
        cfg.output_dir = args.output_dir

    audio_path = Path(args.audio).resolve()

    logger.info(f"lesson-assist 시작")
    logger.info(f"  오디오: {audio_path}")
    logger.info(f"  과목: {args.course}")
    logger.info(f"  날짜: {args.date or '오늘'}")
    logger.info(f"  전사 모델: {cfg.transcribe.model}")
    logger.info(f"  요약 모델: {cfg.summarize.model}")
    logger.info(f"  볼트: {cfg.vault_path}")

    from .pipeline import run_pipeline

    try:
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
        )
        logger.info(f"노트 생성 완료: {note_path}")
    except KeyboardInterrupt:
        logger.warning("사용자에 의해 중단됨")
        sys.exit(1)
    except Exception as e:
        logger.error(f"파이프라인 실패: {e}")
        raise


if __name__ == "__main__":
    main()
