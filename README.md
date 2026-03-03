# lesson-assist

수업 녹음 파일을 넣으면 **전사 → 요약 → Obsidian 노트**가 자동 생성되는 CLI 도구.

## 요구사항

- Python 3.10+
- NVIDIA GPU + CUDA (faster-whisper 가속)
- ffmpeg (오디오 변환)
- OpenAI API 키

## 설치

```bash
git clone https://github.com/your/lesson-assist.git
cd lesson-assist
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

## 설정

```bash
copy config.yaml.example config.yaml
```

`config.yaml`에서 `vault_path`를 본인의 Obsidian vault 경로로 수정.

환경변수:
```bash
set OPENAI_API_KEY=sk-...
```

## 사용법

```bash
# 기본 실행
python -m lesson_assist --audio "D:\Recordings\lecture.m4a" --course "자료구조"

# 대화형 교정 모드
python -m lesson_assist --audio "lecture.m4a" --course "자료구조" --interactive

# 교정 건너뛰고 바로 요약
python -m lesson_assist --audio "lecture.m4a" --course "자료구조" --skip-review

# 교정 파일 수정 후 재실행
python -m lesson_assist --audio "lecture.m4a" --course "자료구조" --review
```

### 주요 옵션

| 옵션 | 설명 |
|------|------|
| `--audio` | 녹음 파일 경로 (필수) |
| `--course` | 과목명 (필수) |
| `--vault` | Obsidian vault 경로 |
| `--date` | 강의 날짜 YYYY-MM-DD (기본: 오늘) |
| `--skip-review` | 교정 단계 건너뛰기 |
| `--review` | 교정 파일 반영 후 재실행 |
| `--interactive` | 대화형 교정 모드 |
| `--no-daily` | 데일리 노트 연동 비활성화 |
| `-v` | 상세 로그 |

## 파이프라인 흐름

```
녹음파일 → 전사(faster-whisper) → 품질검토(저신뢰 후보) → 분할(~25분)
    → 요약(GPT-4o) → 액션추출(과제/시험/일정) → Obsidian 노트 → 데일리 연동
```

## 출력물

- `3_Areas/Lectures/{과목명}/{날짜}_{과목명}.md` — 강의 노트
- `data/transcripts/` — 전사 원문 + 세그먼트 JSON
- `data/reviews/` — 교정 후보 JSONL
- `data/parts/` — 파트별 텍스트
- `data/summaries/` — 요약 + 액션 아이템 JSON
