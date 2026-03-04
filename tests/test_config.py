"""config 모듈 테스트."""
import os
import shutil
import tempfile
from pathlib import Path

import yaml

from lesson_assist.config import (
    AnchorsConfig,
    AppConfig,
    EclassConfig,
    RAGConfig,
    load_config,
)


def _make_temp_dir():
    d = Path(tempfile.mkdtemp(prefix="la_test_"))
    return d


class TestLoadConfig:
    def test_defaults(self):
        cfg = load_config("/nonexistent/config.yaml")
        assert cfg.transcribe.model == "large-v3"
        assert cfg.transcribe.device == "cuda"
        assert cfg.segment.part_minutes == 25
        assert cfg.rag.enabled is True
        assert cfg.eclass.enabled is False

    def test_load_from_yaml(self):
        td = _make_temp_dir()
        try:
            config_data = {
                "vault_path": "test_vault",
                "output_dir": "test_out",
                "transcribe": {"model": "small", "device": "cpu"},
                "rag": {"enabled": False, "top_k": 3},
                "eclass": {"enabled": True, "data_dir": "/some/path"},
            }
            config_file = td / "config.yaml"
            config_file.write_text(yaml.dump(config_data), encoding="utf-8")

            cfg = load_config(str(config_file))
            assert cfg.vault_path == "test_vault"
            assert cfg.transcribe.model == "small"
            assert cfg.transcribe.device == "cpu"
            assert cfg.rag.enabled is False
            assert cfg.rag.top_k == 3
            assert cfg.eclass.enabled is True
            assert cfg.eclass.data_dir == "/some/path"
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_anchors_defaults(self):
        cfg = AnchorsConfig()
        assert "칠판" in cfg.keywords
        assert "슬라이드" in cfg.keywords
        assert cfg.context_seconds == 30.0

    def test_unknown_keys_ignored(self):
        td = _make_temp_dir()
        try:
            config_data = {
                "transcribe": {"model": "small", "unknown_key": "value"},
            }
            config_file = td / "config.yaml"
            config_file.write_text(yaml.dump(config_data), encoding="utf-8")

            cfg = load_config(str(config_file))
            assert cfg.transcribe.model == "small"
        finally:
            shutil.rmtree(td, ignore_errors=True)
