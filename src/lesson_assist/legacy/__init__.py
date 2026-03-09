"""lesson-assist v1 레거시 모듈.

다글로/NotebookLM 사용이 어려울 때 fallback으로 활용:
  - python -m lesson_assist legacy process --audio ... --course ...
  - python -m lesson_assist legacy exam --course ...

또는 개별 모듈 import:
  from lesson_assist.legacy.transcribe import transcribe
  from lesson_assist.legacy.summarize import summarize
"""
