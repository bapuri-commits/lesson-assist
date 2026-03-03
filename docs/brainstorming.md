[CURSOR PROMPT] 로컬 Whisper 전사 + GPT 요약 + Obsidian 노트 생성 + Visual Anchors(판서/슬라이드 연결) 파이프라인 구현

너는 Windows 환경에서 동작하는 “수업 녹음 자동 정리 파이프라인”을 구현한다.
사용자 PC 사양: Ryzen 9 3900X + RTX 3080 Ti (GPU 사용 가능).
수업은 100% 한국어, 교수님 단독 발화가 대부분이므로 화자 구분은 기본적으로 필요 없다.
요약/정리는 OpenAI API(LLM)로 수행한다.
지식 베이스는 Notion이 아니라 Obsidian(로컬 vault)이다.

[최종 목표]
1) 사용자가 수업 녹음 파일(m4a/mp3/wav)을 지정 폴더에 넣는다.
2) 로컬에서 whisper.cpp 또는 faster-whisper로 한국어 전사를 수행한다. (GPU 가속 사용)
3) 전사 결과가 너무 길면 자동으로 “N분 단위(기본 25~30분)”로 분할 전사/요약한다.
4) OpenAI API로:
   - Part별 1차 요약(구조화)
   - 전체 통합 요약(중복 제거 + 흐름 재정렬)
   - 시험 대비 A4 1장 압축(암기/이해/문제풀이)
5) 결과를 Obsidian vault 내 마크다운 파일로 생성한다.
   - Frontmatter 포함: date, course, source_audio, duration, model, tags
   - 섹션: Raw Transcript(옵션), Part Summaries, Final Summary, Exam Sheet, Visual Anchors, TODO/Questions
6) 모든 작업을 단일 CLI 명령으로 실행 가능하게 만든다.
   - 예: python pipeline.py --audio "C:\...\lecture.m4a" --course "자료구조" --vault "D:\Obsidian\Vault"
   - 또는 폴더 감시 모드: python watch.py --inbox ".../inbox" --vault ".../vault"

[핵심 확장 요구사항: Visual Anchors(판서/슬라이드/시각정보 연결)]
수업은 교수님이 필기/판서/슬라이드로 설명하는 경우가 많아, 음성만으로 맥락이 끊기는 구간이 존재한다.
따라서 “텍스트 전사 ↔ 시각 정보”를 연결하는 기능을 반드시 포함한다.

A) 타임스탬프 기반 앵커(Anchor)
- 전사 결과를 plain text 뿐 아니라 SRT 또는 VTT 형태로도 저장한다(타임스탬프 포함).
- Obsidian 노트에 "## Visual Anchors" 섹션을 항상 생성한다.
- 사용자는 수업 중/후에 특정 시점(mm:ss)만 메모해도 되고, 해당 시점에 촬영한 이미지가 있으면 연결할 수 있다.
- 파이프라인은 자동으로 “시각정보 의존 구간 후보”를 탐지하여 앵커 초안을 만들어준다.

B) 시각 의존 구간 후보 자동 탐지(Heuristic)
- 전사 텍스트에서 다음 류의 표현이 나오면 시각 의존 후보로 판단하고, 해당 문장 주변(예: ±20~40초) 타임 범위를 앵커 후보로 생성한다.
  키워드 예: "칠판", "판서", "보면", "그림", "표", "수식", "식", "여기", "이거", "이렇게", "저기", "슬라이드", "다이어그램", "그래프"
- 후보는 "Visual Anchors" 섹션에 체크리스트로 생성한다.
  예:
  - [ ] [35:20] (후보) “여기 칠판에 쓴 식…” — (사진/수식/설명 추가)
  - [ ] [41:05] (후보) “표로 정리하면…” — (표 캡처 추가)

C) 이미지(촬영) 연결 기능(선택적이지만 지원)
- 사용자가 판서/슬라이드 사진을 찍어 Obsidian vault 또는 inbox 폴더에 넣을 수 있다.
- 구현은 최소한 다음 두 가지 모드를 제공한다:
  (1) 수동 연결: 사용자가 Visual Anchors 섹션에 이미지 파일명을 직접 적거나 드래그&드롭 후 링크를 넣는다.
  (2) 반자동 연결(가능하면): 파일명 규칙을 지원한다.
      - 예: "2026-03-03_자료구조_35m20s.jpg" 또는 "DS_35-20.jpg"
      - 스크립트가 파일명에서 시간 정보를 파싱해 해당 앵커에 자동 첨부(링크 추가)한다.
- 이미지 링크는 Obsidian 마크다운 규칙을 따른다.
  예: ![[DS_35-20.jpg]]

D) (옵션) 앵커 주변 텍스트 자동 스니펫 삽입
- Visual Anchors에 각 앵커별로 해당 시간대 주변의 전사 텍스트 일부(예: 30~60초 구간)를 자동으로 붙여서 “어떤 설명 중이었는지” 맥락을 제공한다.
- 스니펫은 너무 길지 않게 제한하고, 필요하면 “더보기 링크(파일 위치/타임)”를 제공한다.

[중요 제약]
- 외부 SaaS(Otter/Notion)를 쓰지 않는다.
- 화자 구분/회의 기능은 기본적으로 필요 없다(옵션으로만).
- 한국어 정확도를 최우선으로 하며, 전사 품질이 낮으면 자동으로 large/medium 모델 전환 옵션을 제공한다.
- 요약은 프롬프트 템플릿을 코드로 고정하여 항상 동일한 포맷으로 출력한다.
- API 키는 환경변수로 받는다(OPENAI_API_KEY).
- 긴 파일 처리(메모리/시간) 안정성 확보: 분할 처리 + 재시도 + 중간 산출물 저장 + resume 가능.

[구현 방식 제안]
A안: faster-whisper (Python, GPU, 속도 빠름, 설치 쉬움)  ← 기본
B안: whisper.cpp 호출 (exe/cli) + 결과 파싱          ← 옵션
- timestamps 생성(SRT/VTT)은 반드시 지원한다.

[디렉토리/파일 설계]
- project/
  - pipeline.py (단일 실행 진입점)
  - transcribe.py (전사 모듈: txt + srt/vtt)
  - segmenter.py (오디오/전사 분할 로직)
  - summarize.py (API 요약 모듈)
  - anchors.py (Visual Anchors 후보 추출 + 이미지 연결)
  - obsidian_writer.py (md 생성 모듈)
  - prompts.py (고정 프롬프트 템플릿)
  - watch.py (폴더 감시 모드: audio + images)
  - requirements.txt
  - README.md
  - data/
    - transcripts/
    - summaries/
    - anchors/
    - logs/

[전사 요구사항]
- language="ko"
- VAD(무음 구간)로 대략 분할 가능하면 활용
- 기본 분할: 25~30분 단위(오디오 길이 기반)
- 결과 포맷:
  - lecture_raw.txt
  - lecture.srt 또는 lecture.vtt (timestamps)
  - parts/part_01.txt, part_02.txt ...
  - parts/part_01.srt/vtt ...
- timestamps 기반으로 “mm:ss → 텍스트 스니펫”을 추출하는 유틸 함수 제공

[요약 프롬프트 1차(Part별)]
- 오늘의 주제 1줄
- 목차(섹션 5~10개)
- 핵심 개념/정의(정확히)
- 정리/규칙/조건(있으면 엄밀히)
- 예제/직관
- 교수 강조 포인트(“시험/중요/기억/자주” 신호)
- 헷갈리는 포인트/오해 방지
- 과제/읽을거리/다음 예고(언급된 것만)
- (추가) "시각자료 의존 구간"이 의심되는 표현이 나오면 따로 모아서 bullet로 출력(앵커 후보 생성에 도움)

[통합 요약 프롬프트(Part1~N 합치기)]
- 전체 목차 재구성
- 중복 제거
- 흐름/의존관계 반영(선행개념 -> 후행개념)
- 정의/정리/예제를 재배치하여 “학습용 문서”로 완성
- (추가) Visual Anchors 후보(시간/표현/필요 보완 요소) 요약 섹션 생성

[시험 대비 A4 1장 프롬프트]
- 암기할 것 / 이해할 것 / 문제풀이 포인트
- 자주 나오는 함정 3개
- 5분 초압축 10줄

[Obsidian 마크다운 템플릿]
- YAML frontmatter:
  date: YYYY-MM-DD
  course: ...
  source_audio: filename
  duration_min: ...
  transcribe_engine: faster-whisper|whisper.cpp
  transcribe_model: ...
  summarize_model: ...
  tags: [lecture, ...]
- 본문 섹션:
  # 요약
  ## 최종 요약
  ## 시험 대비(A4)
  ## Part별 요약
  # Visual Anchors (판서/슬라이드 보완)
  ## 후보(자동 생성)
  ## 확정(수동/반자동 연결)
  # 원문(선택)
  # 질문/할일

[Visual Anchors 출력 예시(마크다운)]
## 후보(자동 생성)
- [ ] [35:20] (후보) “여기 칠판에 쓴 식…”  
  - 주변 텍스트(스니펫): "...(자동 삽입)..."  
  - 첨부 이미지: (없음)
- [ ] [41:05] (후보) “표로 정리하면…”  
  - 주변 텍스트(스니펫): "...(자동 삽입)..."  
  - 첨부 이미지: (없음)

## 확정(수동/반자동 연결)
- [x] [35:20] (판서) 행렬 곱 예시 2x2  
  - ![[DS_35-20.jpg]]
  - 추가 메모: (사용자 입력)

[안정성/UX]
- 진행 로그 출력
- 중간 산출물 저장 후 실패 시 재개(resume) 가능
- 파일명이 겹치면 날짜+해시로 충돌 방지
- 실행 예시/설치 가이드 포함
- watch 모드에서:
  - audio inbox에 새 파일 → 전사/요약/md 생성
  - images inbox에 새 파일 → 파일명 시간 파싱 후 해당 노트의 Visual Anchors에 자동 첨부 시도(가능한 범위에서)

[Deliverables]
1) 동작하는 코드
2) requirements.txt
3) README.md (설치/사용법/예시)
4) 샘플 실행 커맨드
5) (선택) watch 모드로 폴더 자동 처리(audio + images)
6) (선택) 이미지 파일명 규칙 문서화 + 자동 연결 예시

이제 위 요구사항을 만족하는 구현을 시작하라.
먼저 아키텍처와 파일별 책임을 제시하고, 그 다음 실제 코드를 작성하라.