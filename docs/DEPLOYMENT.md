# lesson-assist — VPS 배포 가이드 (하이브리드 구조)

> ⚠️ **초안 문서** — 각 Stage 진행 시 실제 환경에 맞게 수정될 수 있음.

> 전사(GPU)는 로컬, 요약(API)은 VPS에서 실행하는 분리 구조.
> DevOps 학습 로드맵 Stage 8에서 사용.
>
> **참조**: DevOps 로드맵 전체는 `SyOps/docs/DEVOPS_ROADMAP.md`를 참조하세요.

---

## 아키텍처 개요

```
[로컬 PC (NVIDIA GPU)]              [VPS]
녹음 파일                            
   ↓                                 
전사 (faster-whisper, CUDA)          
   ↓                                 
transcript 생성                      
   ↓ rsync                           
   ──────────────────────→  data/transcripts/
                                     ↓
                            요약 (GPT-4o API)
                                     ↓
                            Obsidian 노트 생성
                                     ↓ rsync
   ←──────────────────────  결과 동기화
```

---

## 사전 요구사항

### 로컬 (전사용)
- NVIDIA GPU + CUDA
- faster-whisper
- ffmpeg

### VPS (요약용)
- Python 3.10+
- OpenAI API 키

---

## 환경변수

| 변수 | 필수 | 설명 |
|------|------|------|
| `OPENAI_API_KEY` | ✅ | GPT-4o 요약용 |

---

## VPS 설치

```bash
cd /opt
git clone https://github.com/사용자/lesson-assist.git
cd lesson-assist

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
# GPU 관련 패키지(faster-whisper)는 VPS에서 제외 가능

cp config.yaml.example config.yaml
# config.yaml 편집: transcribe 비활성화, summarize만 활성화
```

---

## Stage 8 — rsync 동기화 설정

### 로컬 → VPS (전사 결과 업로드)

```bash
# TODO: Stage 9에서 설정
# rsync -avz ./data/transcripts/ vps:/opt/lesson-assist/data/transcripts/
```

### VPS → 로컬 (요약 결과 다운로드)

```bash
# TODO: Stage 9에서 설정
# rsync -avz vps:/opt/lesson-assist/data/summaries/ ./data/summaries/
```

### 자동화 옵션

1. **수동**: 로컬에서 전사 후 직접 rsync 실행
2. **cron**: VPS에서 주기적으로 새 transcript 확인 → 요약 실행
3. **inotifywait**: 파일 변경 감지 시 자동 실행

---

## 요약 전용 실행 모드 (TODO)

현재 lesson-assist는 전사+요약이 하나의 파이프라인. VPS용으로:
- transcript 입력 → 요약만 실행하는 모드 필요
- `--skip-transcribe` 플래그 또는 config에서 분리

---

## 알려진 이슈

- faster-whisper는 CUDA 필수 → VPS에서 전사 불가 (CPU 모드는 실용적이지 않음)
- config.yaml에서 vault_path를 VPS 경로로 변경 필요
- ChromaDB RAG 저장소 경로도 VPS에 맞게 조정 필요
- school_sync 연동 시 eclass 데이터 경로 설정 주의
