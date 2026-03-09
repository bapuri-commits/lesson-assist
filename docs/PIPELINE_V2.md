# lesson-assist v2 — 학습 파이프라인 재설계

## 목차

1. [배경 및 동기](#배경-및-동기)
2. [v1 → v2 변경 요약](#v1--v2-변경-요약)
3. [시스템 전체 그림](#시스템-전체-그림)
4. [Phase 1: 데이터 수집](#phase-1-데이터-수집)
5. [Phase 2: NotebookLM 패키징](#phase-2-notebooklm-패키징)
6. [Phase 3: NotebookLM 학습](#phase-3-notebooklm-학습)
7. [Phase 4: NotebookLM → Obsidian 노트 생성](#phase-4-notebooklm--obsidian-노트-생성)
8. [lesson-assist 모듈 계획](#lesson-assist-모듈-계획)
9. [CLI 설계](#cli-설계)
10. [설정 파일](#설정-파일)
11. [미래 확장](#미래-확장)

---

## 배경 및 동기

### 문제 인식

v1(faster-whisper + GPT-4o)은 동작하지만 두 가지 구조적 한계가 있다:

1. **전사 품질**: faster-whisper large-v3의 한국어 학술 용어 인식률이 낮다. 품질교정(review) 파이프라인으로 보완하지만 근본적 해결이 아니다.
2. **학습 깊이**: GPT-4o 요약은 "강의 내용 정리"는 잘 하지만, "교안 12페이지의 수식에 대해 교수님이 구두로 설명한 보충 사례"처럼 여러 소스를 교차 참조하는 심화 학습에는 한계가 있다.

### 해결 방향

- **다글로**(Daglo)로 전사 엔진 대체 → 한국어 특화 전사, GPU 의존성 제거
- **NotebookLM** 도입 → 전사본 + 수업자료 + 강의계획서를 한 번에 물고 딥다이브 학습
- lesson-assist의 역할을 "전사+요약 엔진"에서 **"학습 데이터 허브 + 노트 생성기"**로 전환

### Gemini 브레인스토밍 참고

이 설계의 초기 방향성은 Gemini와의 논의(`school_sync/docs/GEMINI.md`)에서 출발했다. Gemini는 프로젝트 구조를 모르는 상태에서 "University Life OS" 개념을 제안했고, 그중 다글로 대체와 NotebookLM 도입 아이디어를 school_sync/lesson-assist 실제 구조에 맞게 재설계한 것이 이 문서다.

---

## v1 → v2 변경 요약

| 항목 | v1 | v2 |
|------|----|----|
| 전사 | faster-whisper (로컬 GPU) | **다글로** (외부 서비스, SRT/TXT export) |
| 요약 | GPT-4o (파트별 + 통합) | **NotebookLM** (수동, 멀티소스 딥다이브) |
| 학습 자료 매칭 | eclass RAG (ChromaDB + 임베딩) | **NotebookLM**에 위임 (소스 직접 업로드) |
| 시험 대비 | exam_sheet.py (GPT-4o) | **NotebookLM** Study Guide |
| Obsidian 노트 소스 | GPT-4o 요약 결과 | **NotebookLM 학습 결과** (사용자가 export) |
| GPU 필요 | CUDA + RTX 3080 Ti | **불필요** |
| API 비용 | GPT-4o ~$0.13/회 | **없음** (다글로 무료/유료, NotebookLM 무료) |
| 프로그램 역할 | 전사 → 요약 → 노트 (end-to-end 자동) | **패키징 + 노트 포맷팅** (양쪽 끝 담당) |
| 자동화 수준 | fully-auto (녹음 파일 → 노트) | **semi-auto** (다글로 export, NLM 수동, 결과 export) |

### 역할 분리 (확정)

| 영역 | 담당 | 예시 질의 |
|------|------|-----------|
| **학사 관리** | school_sync + ask.py | "과제 마감 언제야?", "GPA 계산", "졸업 요건" |
| **학습 심화** | NotebookLM | "교수님이 3주차에 설명한 증명 과정", "시험 대비 정리" |
| **데이터 수집** | school_sync 크롤링 + 다글로 | PDF/PPT 다운로드, 전사본 생성 |
| **데이터 가공 + 노트** | lesson-assist v2 | NotebookLM 패키징, Obsidian 노트 생성 |

---

## 시스템 전체 그림

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         학사 관리 (기존 유지)                             │
│   school_sync: 크롤링 → 정규화 → ask.py Q&A                             │
│   "과제 마감 언제야?" "GPA 계산해줘" "졸업 요건"                           │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                         학습 파이프라인 (v2)                              │
│                                                                          │
│  Phase 1            Phase 2           Phase 3          Phase 4           │
│  ┌──────────┐      ┌──────────┐      ┌──────────┐    ┌──────────┐      │
│  │ 데이터   │      │ 패키징   │      │ 학습     │    │ 노트     │      │
│  │ 수집     │ ───→ │(프로그램)│ ───→ │(NotebookLM)──→│ 생성     │      │
│  └──────────┘      └──────────┘      └──────────┘    └──────────┘      │
│  school_sync        lesson-assist     수동             lesson-assist     │
│  + 다글로            pack 명령                          note 명령        │
│                     (자동)             사용자 학습      (반자동)          │
│                     완료 시 폴더 열림                                    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: 데이터 수집

기존 인프라를 그대로 활용한다. 새로 만들 것은 없다.

### 1-A: school_sync 크롤링

```bash
python main.py --download    # 전체 크롤링 + 수업자료 다운로드
```

**산출물 (lesson-assist가 소비하는 데이터):**

| 데이터 | 경로 | 설명 |
|--------|------|------|
| 수업자료 (PDF/PPT) | `school_sync/output/downloads/{과목}/` | 원본 파일 그대로 |
| 강의계획서 | `school_sync/output/normalized/academics/syllabus.json` | 주차별 토픽, 교수 정보, 교재 |
| 과제/마감 | `school_sync/output/normalized/academics/assignments.json` | 과제명, 마감일, 상태 |
| 마감 일정 | `school_sync/output/normalized/academics/deadlines.json` | 타임라인 |
| 공지사항 | `school_sync/output/normalized/info/notices.json` | 과목 관련 필터 적용 |
| 수강 과목 | `school_sync/output/normalized/academics/courses.json` | 과목명 매핑용 |

### 1-B: 다글로 전사

사용자가 수동으로 수행하는 단계:

1. 수업 녹음 파일을 다글로에 업로드
2. 전사 완료 후 SRT + TXT export
3. 지정 폴더에 저장

**저장 위치:**
```
lesson-assist/input/daglo/{과목명}/
├── 2026-03-10.srt    ← SRT (타임스탬프 포함)
└── 2026-03-10.txt    ← TXT (순수 텍스트)
```

**파일명 규칙:** `YYYY-MM-DD.확장자` (과목명은 폴더명으로 결정)

---

## Phase 2: NotebookLM 패키징

**lesson-assist가 수행하는 첫 번째 자동화 구간.**

### 입력

- `input/daglo/{과목명}/` — 다글로 SRT/TXT
- `school_sync/output/` — 크롤링 데이터 (경로는 `config.yaml`에서 설정)

### 처리

#### 2-1. SRT 정제

다글로 SRT를 NotebookLM에 올리기 좋은 형태로 가공한다.

- 타임스탬프 유지: NotebookLM이 시간대별 참조에 활용할 수 있음
- 자막 번호 제거, 빈 줄 정리
- 연속된 짧은 세그먼트 병합 (가독성)

**정제 포맷 예시:**
```text
[00:00:15] 오늘은 스케줄링 알고리즘에 대해서 다루겠습니다.
[00:00:25] 지난 시간에 프로세스 상태 전이를 배웠는데, 그 연장선입니다.
[00:01:10] 교재 12페이지를 보시면 라운드 로빈 방식이 나오는데...
```

#### 2-2. 학습 컨텍스트 생성

school_sync 정규화 데이터에서 해당 과목의 학습 관련 정보를 추출하여 하나의 마크다운으로 통합한다.

**포함 데이터:**
- 강의계획서: 주차별 토픽, 교수 정보, 교재, 강의 목표/개요
- 과제: 현재 활성 과제 목록, 마감일, 상태
- 공지사항: 해당 과목 관련 공지 (최근 2주)

**제외 데이터:**
- 성적, 출석 → 학습과 직접 관련 없음 (학사 관리는 ask.py 영역)
- 학교 행사, 장학금 → 학습 무관

#### 2-3. NotebookLM 가이드 프롬프트 생성

NotebookLM에 소스와 함께 업로드할 **가이드 문서**를 자동 생성한다. 이 가이드는 NotebookLM이 각 소스를 어떻게 이해하고 활용해야 하는지, 그리고 학습 결과를 어떤 형태로 정리해야 나중에 export하기 편한지를 안내한다.

**가이드 구조:**
```markdown
# {과목명} 학습 가이드 — {날짜}

## 소스 설명
이 노트북에는 다음 소스가 포함되어 있습니다:
- **전사본** ({날짜}.txt): 해당 수업의 교수님 강의 전사 기록. 타임스탬프 포함.
  대괄호 안의 시간([HH:MM:SS])은 강의 시점을 나타냅니다.
- **수업자료** (PDF/PPT 파일들): 해당 수업에서 사용된 강의 교안.
  교수님이 전사본에서 "이 슬라이드", "여기 보시면" 등으로 언급하는 것이 이 자료입니다.
- **학습 컨텍스트** (학습컨텍스트.md): 강의계획서, 현재 과제, 최근 공지를 정리한 문서.
  이번 수업이 전체 커리큘럼에서 어디에 위치하는지, 어떤 과제가 관련되는지 파악하는 데 사용하세요.

## 소스 간 관계
- 전사본에서 교수님이 특정 페이지/슬라이드를 언급하면 → 수업자료 PDF에서 해당 내용을 찾아 연결해주세요.
- 전사본에서 과제/시험/마감을 언급하면 → 학습 컨텍스트의 과제 목록과 교차 확인해주세요.
- 강의계획서의 주차별 토픽과 전사본의 실제 수업 내용을 비교하면 진도 파악이 가능합니다.

## 학습 활용 가이드

### 강의 내용 정리 요청 시
아래 구조로 정리해주세요 (나중에 노트로 export합니다):
- **주제**: 이번 수업의 핵심 주제 1줄
- **핵심 개념**: 새로 등장한 개념/정의/정리 (정확한 정의 포함)
- **교수 강조 포인트**: "시험에 나온다", "중요하다" 등 교수님이 강조한 부분
- **예제/직관**: 교수님이 든 예시, 비유, 직관적 설명
- **수업자료 참조**: 전사본의 설명이 수업자료 몇 페이지/슬라이드와 대응하는지
- **과제 연관**: 현재 과제와 이번 수업 내용의 연결점

### 시험 대비 요청 시
- 핵심 암기 사항 (정의, 공식, 조건)
- 이해 확인 질문 (개념을 이해했는지 점검)
- 예상 문제 (교수 강조 + 수업자료 기반)
- 자주 나오는 함정/혼동 포인트

### 결과 Export 안내
학습 완료 후, 아래 형식으로 정리해달라고 요청하면 Obsidian 노트로 변환하기 편합니다:
- 강의노트: 해당 수업의 핵심 내용 구조화
- 학습노트: 내가 이해한 것/모르는 것/시험대비 정리
각 노트는 마크다운 형식으로, 제목에 `# {과목명} — {날짜}` 포함.
```

> **이 가이드는 과목/날짜별로 자동 생성된다.** 과목별 커스터마이징이 필요하면 `config.yaml`의 과목별 설정에서 추가 지시를 넣을 수 있다.

#### 2-4. 출력 구조

```
output/notebooklm/{과목명}_{날짜}/
├── 전사본_{날짜}.txt            ← SRT 정제본
├── 학습컨텍스트.md              ← 강의계획서 + 과제 + 공지 통합
├── NotebookLM_가이드.md         ← 소스 설명 + 활용 프롬프트 + export 안내
└── README.txt                   ← 업로드 안내 (이 파일들 + PDF 경로)
```

**README.txt 예시:**
```
=== NotebookLM 업로드 안내 ===

아래 파일을 NotebookLM 노트북에 업로드하세요:

1. 전사본_2026-03-10.txt (이 폴더)
2. 학습컨텍스트.md (이 폴더)
3. NotebookLM_가이드.md (이 폴더)
4. 수업자료 PDF:
   → C:\...\school_sync\output\downloads\자료구조\

수업자료 폴더가 자동으로 열립니다.
```

### 완료 시 자동 폴더 열기

Phase 2 완료 시 두 폴더를 자동으로 탐색기에서 연다:

1. **수업자료 폴더**: `school_sync/output/downloads/{과목}/` — PDF/PPT 원본
2. **NotebookLM 패키지 폴더**: `output/notebooklm/{과목}_{날짜}/` — 정제본 + 가이드

사용자가 두 폴더의 파일을 바로 NotebookLM에 드래그 앤 드롭할 수 있도록 하기 위함.

```python
# 구현 방식 (Windows)
import subprocess
subprocess.Popen(["explorer", str(notebooklm_output_path)])
subprocess.Popen(["explorer", str(materials_path)])
```

### 확장 가능 지점: 데이터 가공 파이프라인

> Phase 2의 데이터 가공 단계는 **플러그인 방식으로 확장 가능**하도록 설계한다.
>
> 현재는 SRT 정제 + 학습컨텍스트 통합만 수행하지만, NotebookLM 사용 경험이 쌓이면서 "NotebookLM이 잘 못하는 부분"이 드러날 때 추가 가공 단계를 삽입할 수 있다.
>
> **예상되는 확장:**
> - **PDF↔전사본 매칭**: 전사본의 시간대별 키워드와 PDF 페이지별 텍스트를 사전 매칭하여 `[35:20] → 교안 p.12` 같은 메타데이터를 전사본에 주입. NotebookLM이 소스 간 연결을 잘 못하면 이 단계를 추가.
> - **토픽 분할**: 전사본을 토픽 단위로 분할하여 각 토픽에 관련 PDF 페이지를 태깅. 긴 전사본에서 NotebookLM의 검색 정확도가 떨어지면 유효.
> - **용어 사전 주입**: 해당 과목의 전문 용어 목록을 가이드에 추가. 다글로가 잘못 전사한 용어를 NotebookLM이 문맥상 교정할 수 있도록.
> - **이전 강의 요약 주입**: 같은 과목의 이전 NotebookLM 학습 결과 요약을 새 패키지에 포함. 누적 학습 맥락 제공.
>
> 이 확장들은 **필요성이 확인된 후** 구현한다. NotebookLM에 맡겨보고, 부족한 부분만 보완하는 전략.

---

## Phase 3: NotebookLM 학습

프로그램이 관여하지 않는 구간. 사용자가 직접 수행한다.

### 워크플로우

1. NotebookLM에서 과목별 노트북 생성 (또는 기존 노트북에 소스 추가)
2. Phase 2 산출물 + PDF 업로드
3. **NotebookLM_가이드.md를 반드시 소스로 포함** — 이 가이드가 NotebookLM의 동작을 안내

### 학습 활동 예시

**강의 내용 이해:**
- "이번 전사본에서 교수님이 새로 가르친 핵심 개념을 정리해줘"
- "교안 12페이지의 수식에 대해 교수님이 구두로 설명한 보충 사례가 뭐야?"
- "전사본에서 교수님이 '중요하다', '시험에 나온다'고 말한 부분만 모아줘"

**교차 참조:**
- "전사본에서 교수님이 '이 슬라이드 보시면'이라고 말한 부분이 교안 몇 페이지야?"
- "이번 과제가 오늘 수업 내용 중 어떤 부분과 연관돼?"

**시험 대비:**
- "이번 수업 내용으로 예상 문제 5개 만들어줘"
- "이번 학기 지금까지 배운 내용으로 시험 범위 요약해줘"

### NotebookLM → Export 방법

학습 완료 후 결과를 가져오는 방법. Phase 4로 넘기기 위한 준비.

**방법 A — 정리 요청 후 복사:**
NotebookLM에 "강의노트 형식으로 정리해줘" 또는 "학습노트 형식으로 정리해줘" 요청 → 결과를 복사 → 마크다운 파일로 저장.

**방법 B — Study Guide 등 기능 활용:**
NotebookLM의 Study Guide, FAQ, Timeline 등 자동 생성 기능 결과를 복사.

**방법 C — 대화 내용 선별 복사:**
학습 중 유용했던 Q&A를 선별하여 복사.

> 어떤 방법이든, 결과를 `input/from_notebooklm/{과목명}/` 폴더에 마크다운 파일로 저장하면 Phase 4에서 처리된다.

---

## Phase 4: NotebookLM → Obsidian 노트 생성

**lesson-assist가 수행하는 두 번째 자동화 구간.**

> 이 Phase의 구체적 동작은 실제 사용하면서 다듬는다.
> 아래는 초기 설계이며, NotebookLM에서 실제로 어떤 형태의 결과물이 나오는지 확인한 후 조정.

### 입력: 드롭 폴더

```
input/from_notebooklm/{과목명}/
├── 2026-03-10_강의노트.md     ← NotebookLM에서 복사한 강의 내용 정리
└── 2026-03-10_학습노트.md     ← NotebookLM에서 복사한 학습/시험대비 정리
```

**파일명 규칙:** `YYYY-MM-DD_노트타입.md`
- 노트타입: `강의노트` 또는 `학습노트`
- 과목명은 폴더명으로 결정

**파일 내용:** NotebookLM에서 복사한 원문 그대로. 특별한 포맷 없이 자유 형식.

### 처리

1. **파일 감지**: 드롭 폴더에서 미처리 파일 탐색
2. **메타데이터 파싱**: 파일명에서 과목명/날짜/타입 추출
3. **주차 매칭**: 강의계획서(school_sync syllabus)에서 해당 날짜의 주차/토픽 조회
4. **포맷팅**: Obsidian 템플릿에 맞춰 구조화
   - YAML frontmatter (date, course, week, topic, tags, source)
   - 위키링크 (`[[]]`) 적용
   - 섹션 구조 정리
5. **저장**: The Record 경로에 생성
6. **데일리 연동**: 해당 날짜의 데일리 노트에 공부 기록 추가

### 노트 타입별 출력

#### 강의노트

매 수업마다 생성. 해당 수업의 핵심 내용 정리.

**경로:** `The Record/3_Areas/Lectures/{과목명}/{YYYY-MM-DD}_{과목명}.md`

**템플릿:**
```markdown
---
date: YYYY-MM-DD
course: {과목명}
week: {주차}
topic: {주차별 토픽}
source: NotebookLM
tags: [lecture, {과목명}]
---

# YYYY-MM-DD {과목명}

> **{주차}주차 — {토픽}**

## 강의 내용

{NotebookLM에서 가져온 강의 정리 내용}

## 교수 강조 포인트

{NotebookLM에서 가져온 강조 사항 — 본문에 포함된 경우 자동 추출, 없으면 생략}
```

#### 학습노트

필요할 때 생성. 이해도 정리, 시험 대비.

**경로:** `The Record/3_Areas/Lectures/{과목명}/{YYYY-MM-DD}_{과목명}_학습.md`

**템플릿:**
```markdown
---
date: YYYY-MM-DD
course: {과목명}
type: study
source: NotebookLM
tags: [study, {과목명}]
---

# {과목명} 학습 정리 — YYYY-MM-DD

{NotebookLM에서 가져온 학습 정리 내용}
```

### 데일리 노트 연동

강의노트 생성 시 해당 날짜의 데일리 노트 `## 공부 기록` 섹션에 링크 추가:

```markdown
## 공부 기록
- 📖 [[YYYY-MM-DD_자료구조|자료구조 {주차}주차]] — {토픽}
```

기존 v1의 `daily_linker.py` 로직을 재활용한다.

---

## lesson-assist 모듈 계획

### 제거 모듈 (v1 → v2에서 불필요)

| 모듈 | 이유 |
|------|------|
| `transcribe.py` | 다글로 대체 |
| `_transcribe_worker.py` | 다글로 대체 |
| `review.py` | faster-whisper 저신뢰 교정 — 다글로에서 불필요 |
| `preprocess.py` | ffmpeg 오디오 전처리 — 다글로가 자체 처리 |
| `summarize.py` | GPT-4o 요약 — NotebookLM 대체 |
| `prompts.py` | GPT-4o 프롬프트 — NotebookLM 대체 |
| `actions.py` | 액션 추출 — school_sync가 과제/마감 관리 |
| `exam_sheet.py` | 시험 대비 — NotebookLM Study Guide 대체 |
| `anchors.py` | Visual Anchors — NotebookLM이 소스 교차 참조 |
| `rag/` (전체) | ChromaDB RAG — NotebookLM 대체 |
| `eclass.py` | eclass 데이터 연동 — school_sync에서 이미 처리 |
| `material_loader.py` | PPT/PDF→RAG — NotebookLM에 직접 업로드 |

### 변경 모듈

| 모듈 | 변경 내용 |
|------|-----------|
| `subtitle.py` → `srt_parser.py` | SRT 파싱/정제 (다글로 SRT 입력) |
| `segment.py` | SRT 세그먼트 병합 로직으로 변경 |
| `obsidian_writer.py` | 소스 변경: GPT 요약 → NotebookLM export. 새 템플릿 |
| `daily_linker.py` | 로직 유지, 데이터 소스만 변경 |
| `config.py` | 새 설정 구조 (school_sync 경로, 다글로 폴더 등) |
| `session.py` | 세션 상태 관리 변경 |
| `pipeline.py` | 전면 재작성 — pack/note 두 가지 파이프라인 |

### 신규 모듈

| 모듈 | 역할 |
|------|------|
| `packer.py` | Phase 2 오케스트레이션 — SRT 정제, 컨텍스트 생성, 가이드 생성, 폴더 열기 |
| `context_builder.py` | school_sync 데이터 → 학습 컨텍스트 마크다운 생성 |
| `guide_generator.py` | NotebookLM 가이드 프롬프트 생성 |
| `importer.py` | Phase 4 — 드롭 폴더에서 NotebookLM 결과 임포트 + 메타데이터 파싱 |
| `formatter.py` | NotebookLM 원문 → Obsidian 템플릿 포맷팅 |

### v2 프로젝트 구조

```
lesson-assist/
├── docs/
│   ├── DESIGN.md                  # v1 설계 (아카이브)
│   ├── PIPELINE_V2.md             # v2 설계 (이 문서)
│   └── brainstorming.md
├── src/
│   └── lesson_assist/
│       ├── __init__.py
│       ├── __main__.py            # CLI 진입점 (pack/note 서브커맨드)
│       ├── config.py              # 설정 (school_sync 경로, 입출력 폴더)
│       ├── pipeline.py            # 파이프라인 오케스트레이션
│       ├── srt_parser.py          # 다글로 SRT 파싱 + 정제
│       ├── packer.py              # Phase 2: NotebookLM 패키징
│       ├── context_builder.py     # school_sync 데이터 → 학습 컨텍스트
│       ├── guide_generator.py     # NotebookLM 가이드 프롬프트 생성
│       ├── importer.py            # Phase 4: NLM 결과 임포트
│       ├── formatter.py           # Obsidian 템플릿 포맷팅
│       ├── obsidian_writer.py     # Obsidian 파일 생성 (v1에서 변경)
│       └── daily_linker.py        # 데일리 노트 연동 (v1에서 유지)
├── input/                         # 입력 폴더 (git-ignored)
│   ├── daglo/                     # 다글로 export 파일
│   │   └── {과목명}/
│   │       ├── YYYY-MM-DD.srt
│   │       └── YYYY-MM-DD.txt
│   └── from_notebooklm/          # NotebookLM 학습 결과
│       └── {과목명}/
│           ├── YYYY-MM-DD_강의노트.md
│           └── YYYY-MM-DD_학습노트.md
├── output/                        # 출력 폴더 (git-ignored)
│   └── notebooklm/               # NotebookLM 업로드 패키지
│       └── {과목명}_{날짜}/
│           ├── 전사본_{날짜}.txt
│           ├── 학습컨텍스트.md
│           ├── NotebookLM_가이드.md
│           └── README.txt
├── config.yaml
├── requirements.txt
└── README.md
```

---

## CLI 설계

### 서브커맨드 구조

```bash
# Phase 2: NotebookLM 패키징
python -m lesson_assist pack --course "자료구조" --date 2026-03-10
python -m lesson_assist pack --course "자료구조"    # 최신 미처리 SRT 자동 감지
python -m lesson_assist pack --all                   # 모든 과목의 미처리 SRT

# Phase 4: Obsidian 노트 생성
python -m lesson_assist note --course "자료구조" --date 2026-03-10
python -m lesson_assist note --all                   # 드롭 폴더의 모든 미처리 파일
```

### 주요 옵션

| 옵션 | 적용 | 설명 |
|------|------|------|
| `--course` | pack, note | 과목명 |
| `--date` | pack, note | 날짜 (YYYY-MM-DD, 기본: 자동 감지) |
| `--all` | pack, note | 미처리 파일 전부 처리 |
| `--no-open` | pack | 완료 시 폴더 자동 열기 비활성화 |
| `--vault` | note | Obsidian vault 경로 (기본: config) |
| `--no-daily` | note | 데일리 노트 연동 비활성화 |
| `-v` | 전체 | 상세 로그 |

---

## 설정 파일

### config.yaml 구조

```yaml
# school_sync 연동
school_sync:
  root: "C:\\path\\to\\school_sync"
  output_dir: "output"          # school_sync 내 output 경로
  downloads_dir: "output/downloads"

# 다글로 입력
daglo:
  input_dir: "input/daglo"      # 다글로 export 저장 위치

# NotebookLM 패키징
notebooklm:
  output_dir: "output/notebooklm"
  auto_open: true               # pack 완료 시 폴더 자동 열기
  guide_extras: {}              # 과목별 추가 가이드 지시 (선택)

# NotebookLM 결과 입력
from_notebooklm:
  input_dir: "input/from_notebooklm"

# Obsidian
obsidian:
  vault_path: "G:\\CS_Study\\The Record"
  lecture_dir: "3_Areas/Lectures"
  daily_dir: "1_Daily"

# 과목 설정 (선택)
courses:
  자료구조:
    guide_extra: ""             # NotebookLM 가이드에 추가할 과목별 지시
  머신러닝:
    guide_extra: "수식은 LaTeX 표기로 정리해주세요."
```

---

## 미래 확장

### 단기 (사용 경험 축적 후)

- **Phase 2 가공 파이프라인 확장**: NotebookLM이 소스 간 연결을 잘 못하는 경우가 발견되면 PDF↔전사본 매칭, 토픽 분할 등 추가
- **Phase 4 포맷 안정화**: 실제 NotebookLM 결과물의 패턴이 파악되면 자동 섹션 분류, 구조화 로직 강화
- **가이드 프롬프트 튜닝**: 과목별/상황별 가이드 프롬프트 분기

### 중기

- **이전 학습 결과 누적 참조**: 같은 과목의 이전 NotebookLM 세션 결과를 새 패키지에 요약 포함 → 누적 학습 맥락
- **학습 진도 추적**: Phase 4의 노트 생성 이력을 기반으로 "어떤 과목 몇 주차까지 정리 완료"를 ask.py에서 조회 가능하도록

### 장기 (The_Agent 연동)

- **MCP 서버 전환**: pack/note를 MCP tool로 래핑. The_Agent가 "이번 주 자료구조 패키지 만들어줘"로 호출
- **NotebookLM API 대응**: NotebookLM에 API가 생기면 Phase 3도 자동화

---

## 전체 워크플로우 요약

```
매 수업 단위 반복:

1. [수업 전] school_sync 실행 (자동)
   $ python main.py --download
   → PDF/PPT 다운로드 + 정규화 데이터 갱신

2. [수업 중] 녹음 → 다글로 업로드/전사

3. [수업 후] 다글로 SRT/TXT export → input/daglo/{과목}/ 에 저장

4. [수업 후] lesson-assist pack (자동, ~수초)
   $ python -m lesson_assist pack --course "자료구조"
   → NotebookLM 업로드 셋 생성
   → 수업자료 폴더 + 패키지 폴더 자동 열림

5. [학습] NotebookLM 업로드 + 학습 (수동)
   → 가이드 프롬프트가 NotebookLM 동작 안내
   → 학습 완료 후 결과를 input/from_notebooklm/{과목}/ 에 저장

6. [학습 후] lesson-assist note (자동, ~수초)
   $ python -m lesson_assist note --all
   → Obsidian 강의노트 + 학습노트 생성
   → 데일리 노트 자동 연동
```
