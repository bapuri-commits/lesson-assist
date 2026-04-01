# lesson-assist

다글로 전사본(SRT)을 inbox에 넣으면 **과목 분류 → NotebookLM 업로드 패키지 자동 생성**되는 CLI 도구.

## 빠른 시작 (로컬)

의존성 2개만 설치하면 바로 사용 가능:

```powershell
cd lesson-assist
pip install pyyaml loguru
pip install -e .
```

> 최초 1회만 실행하면 이후엔 바로 사용 가능.

## 매번 쓰는 명령어

```powershell
cd C:\Users\chois\CS_Study_SY\lesson-assist
python -m lesson_assist run --no-sync
```

**순서:**
1. 다글로에서 `.srt` 파일 다운로드
2. `input\daglo\inbox\` 폴더에 파일 넣기
3. 위 명령어 실행
4. 열리는 `output\notebooklm\{과목}\` 폴더 파일들을 NotebookLM에 업로드

## 전체 명령어

```powershell
# 전체 워크플로우 (inbox 분류 → 패키징)
python -m lesson_assist run --no-sync

# 단계별 실행
python -m lesson_assist inbox                          # inbox 분류만
python -m lesson_assist pack --course "자료구조"       # 특정 과목 패키징
python -m lesson_assist pack --all                     # 모든 과목 패키징

# school_sync 크롤링 포함 (기본값)
python -m lesson_assist run
```

### 주요 옵션

| 옵션 | 설명 |
|------|------|
| `--no-sync` | school_sync 크롤링 건너뛰기 (빠름) |
| `--course` | 특정 과목만 처리 |
| `--date YYYY-MM-DD` | 특정 날짜 지정 |
| `--no-open` | 완료 후 폴더 자동 열기 비활성화 |
| `-v` | 상세 로그 |

## 출력물 (NotebookLM 업로드 대상)

| 파일 | 설명 | 재업로드 |
|------|------|----------|
| `전사본_YYYY-MM-DD.txt` | 강의 전사본 | 새 강의마다 추가 |
| `학습컨텍스트.md` | 강의계획서 + 과제 + 공지 | 새 강의마다 교체 |
| `NotebookLM_가이드.md` | NotebookLM 활용 가이드 | 처음 한 번만 |
| `{노트북명}.md` | ipynb → 마크다운 변환 | 새 ipynb 올라올 때만 |

## 파이프라인 흐름

```
inbox (.srt) → 과목/날짜 자동 감지 → 과목별 폴더 이동
    → 전사본 변환 → school_sync 컨텍스트 로드 → ipynb 변환
    → output/notebooklm/{과목}/ 패키지 생성
```

## v1 레거시 (faster-whisper + GPT-4o)

```powershell
python -m lesson_assist legacy process --audio "lecture.m4a" --course "자료구조"
```
