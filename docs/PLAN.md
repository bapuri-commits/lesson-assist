# lesson-assist v2 구현 계획

> 상세 설계: `PIPELINE_V2.md` 참조

## 레거시 정책

v1 코드는 **삭제하지 않고 `src/lesson_assist/legacy/`로 이동**한다.
다글로나 NotebookLM 사용이 어려울 경우 레거시 모듈을 fallback으로 재활용할 수 있다.

```
src/lesson_assist/legacy/
├── __init__.py
├── transcribe.py          # faster-whisper 전사
├── _transcribe_worker.py  # RunPod 백엔드
├── summarize.py           # GPT-4o 요약
├── prompts.py             # GPT-4o 프롬프트
├── review.py              # 저신뢰 후보 교정
├── preprocess.py          # ffmpeg 오디오 전처리
├── actions.py             # 액션 아이템 추출
├── anchors.py             # Visual Anchors
├── exam_sheet.py          # 시험 대비 A4
├── eclass.py              # eclass 연동
├── material_loader.py     # PPT/PDF→RAG
├── subtitle.py            # SRT/VTT 생성
├── segment.py             # 전사본 분할
├── session.py             # 세션 상태 관리
├── pipeline.py            # v1 파이프라인
├── obsidian_writer.py     # v1 노트 생성
├── __main__.py            # v1 CLI (process/exam)
├── config.py              # v1 설정
└── rag/
    ├── __init__.py
    ├── store.py
    ├── json_store.py
    └── context.py
```

**fallback 시나리오:**
- 다글로 접속 불가 → `legacy.transcribe` + `legacy.preprocess`로 로컬 전사
- NotebookLM 사용 불가 → `legacy.summarize` + `legacy.prompts`로 GPT-4o 요약
- 전체 v1 복원 → `legacy.__main__`을 직접 실행 (`python -m lesson_assist.legacy`)

---

## Step 1: 프로젝트 뼈대 + 설정

**목표:** v2 CLI 구조가 동작하고, v1 코드가 legacy/에 보존된 상태.

| 작업 | 설명 |
|------|------|
| 레거시 이동 | v1 모듈 전체를 `legacy/`로 이동. `__init__.py` 추가 |
| config.yaml | v2 설정 구조 (school_sync 경로, daglo/notebooklm 폴더, obsidian vault) |
| config.py | v2 설정 dataclass + 로드 함수 (v1 config와 별도) |
| __main__.py | `pack` / `note` 서브커맨드 구조 + `legacy` 서브커맨드 (v1 호출) |
| 디렉토리 | `input/daglo/`, `input/from_notebooklm/`, `output/notebooklm/` |
| .gitignore | input/, output/ 추가 |
| requirements.txt | pyyaml, loguru만 (torch/whisper/chromadb 제거) |
| pyproject.toml | 버전 0.3.0 |

**완료 기준:** `python -m lesson_assist pack --help`, `python -m lesson_assist note --help` 동작.

---

## Step 2: Phase 2 구현 — NotebookLM 패키징

**목표:** 다글로 SRT + school_sync 데이터 → NotebookLM 업로드 셋 생성.

| 작업 | 설명 |
|------|------|
| srt_parser.py | 다글로 SRT 파싱 + 정제 (타임스탬프 유지, 세그먼트 병합) |
| ~~context_builder.py~~ | school_sync `context_export.py`로 이동됨 (lesson-assist는 파일 읽기만) |
| guide_generator.py | NotebookLM 가이드 프롬프트 자동 생성 (과목/날짜별) |
| packer.py | 위 모듈 오케스트레이션 + README 생성 |
| 폴더 열기 | pack 완료 시 수업자료 폴더 + 패키지 폴더 자동 열기 (explorer) |
| pipeline.py | pack 경로 구현 |

**완료 기준:** `python -m lesson_assist pack --course "자료구조"` → `output/notebooklm/` 생성 + 폴더 2개 열림.

---

## Step 3: Phase 4 구현 — Obsidian 노트 생성

**목표:** NotebookLM 학습 결과 → Obsidian 강의노트/학습노트 생성.

| 작업 | 설명 |
|------|------|
| importer.py | 드롭 폴더 감지 + 파일명 파싱 (과목/날짜/타입) |
| formatter.py | NotebookLM 원문 → Obsidian 템플릿 (frontmatter, 위키링크, 섹션 구조) |
| obsidian_writer.py | v2 노트 생성 (강의노트 + 학습노트 두 템플릿) |
| pipeline.py | note 경로 구현 |

**완료 기준:** `input/from_notebooklm/`에 파일 → `python -m lesson_assist note --all` → The Record에 노트 생성.

---

## Step 4: 데일리 노트 연동

**목표:** 강의노트 생성 시 데일리 노트에 자동 연결.

| 작업 | 설명 |
|------|------|
| daily_linker.py | v1 로직 재활용, 데이터 소스만 변경 (ActionsResult 의존 제거) |
| 주차 매칭 | school_sync syllabus에서 날짜 → 주차/토픽 조회 |

**완료 기준:** 노트 생성 시 데일리 노트 `## 공부 기록`에 링크 추가.

---

## Step 5: 통합 테스트 + 문서

**목표:** E2E 검증, 문서 정리.

| 작업 | 설명 |
|------|------|
| E2E 테스트 | 실제 다글로 SRT → pack → NotebookLM → note 전체 흐름 |
| README.md | v2 기준 사용법 재작성 |
| DESIGN.md | "v1 아카이브" 표시, PIPELINE_V2.md로 안내 |
| config.yaml.example | v2 기준 예시 |

**완료 기준:** 전체 워크플로우 1회 완주, README로 재현 가능.

---

## 의존 관계

```
Step 1 (뼈대)
  ↓
Step 2 (pack) ←── 여기까지 완성하면 실전 투입 가능
  ↓
Step 3 (note) ←── NotebookLM 사용 경험 쌓인 후 진행 가능
  ↓
Step 4 (데일리)
  ↓
Step 5 (테스트/문서)
```
