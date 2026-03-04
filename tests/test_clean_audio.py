"""오디오 전처리 테스트."""
from __future__ import annotations

import shutil

import pytest

from lesson_assist.config import CleanAudioConfig
from lesson_assist.preprocess import (
    CleanStats,
    _build_filter_chain,
    _check_afftdn_available,
    _settings_hash,
)


class TestBuildFilterChain:
    """필터 체인 조립 테스트."""

    def test_default_config_produces_filters(self):
        cfg = CleanAudioConfig()
        chain, names = _build_filter_chain(cfg)
        assert "highpass" in chain
        assert "lowpass" in chain
        assert "silenceremove" in chain
        assert "loudnorm" in chain
        assert len(names) >= 4

    def test_all_disabled(self):
        cfg = CleanAudioConfig(
            highpass_freq=0,
            lowpass_freq=0,
            denoise=False,
            remove_silence=False,
            normalize=False,
        )
        chain, names = _build_filter_chain(cfg)
        assert chain == ""
        assert names == []

    def test_only_silence_removal(self):
        cfg = CleanAudioConfig(
            highpass_freq=0,
            lowpass_freq=0,
            denoise=False,
            remove_silence=True,
            silence_threshold_db=-35.0,
            min_silence_duration=3.0,
            normalize=False,
        )
        chain, names = _build_filter_chain(cfg)
        assert "silenceremove" in chain
        assert "-35.0dB" in chain
        assert "stop_duration=3.0" in chain
        assert "highpass" not in chain
        assert len(names) == 1

    def test_custom_frequencies(self):
        cfg = CleanAudioConfig(
            highpass_freq=100,
            lowpass_freq=6000,
            denoise=False,
            remove_silence=False,
            normalize=False,
        )
        chain, names = _build_filter_chain(cfg)
        assert "highpass=f=100" in chain
        assert "lowpass=f=6000" in chain

    def test_normalize_only(self):
        cfg = CleanAudioConfig(
            highpass_freq=0,
            lowpass_freq=0,
            denoise=False,
            remove_silence=False,
            normalize=True,
        )
        chain, names = _build_filter_chain(cfg)
        assert "loudnorm" in chain
        assert len(names) == 1


class TestCleanStats:
    """전처리 통계 테스트."""

    def test_reduction_pct(self):
        stats = CleanStats(
            original_duration=100.0,
            cleaned_duration=80.0,
            removed_seconds=20.0,
            original_size_mb=10.0,
            cleaned_size_mb=8.0,
            filters_applied=["highpass", "silenceremove"],
        )
        assert stats.reduction_pct == pytest.approx(20.0)

    def test_zero_duration(self):
        stats = CleanStats(
            original_duration=0.0,
            cleaned_duration=0.0,
            removed_seconds=0.0,
            original_size_mb=0.0,
            cleaned_size_mb=0.0,
            filters_applied=[],
        )
        assert stats.reduction_pct == 0.0


class TestSettingsHash:
    """캐시 키 해시 테스트."""

    def test_same_config_same_hash(self):
        a = CleanAudioConfig()
        b = CleanAudioConfig()
        assert _settings_hash(a) == _settings_hash(b)

    def test_different_config_different_hash(self):
        a = CleanAudioConfig(highpass_freq=80)
        b = CleanAudioConfig(highpass_freq=100)
        assert _settings_hash(a) != _settings_hash(b)

    def test_hash_length(self):
        h = _settings_hash(CleanAudioConfig())
        assert len(h) == 8

    def test_silence_threshold_affects_hash(self):
        a = CleanAudioConfig(silence_threshold_db=-40.0)
        b = CleanAudioConfig(silence_threshold_db=-35.0)
        assert _settings_hash(a) != _settings_hash(b)


class TestDenoiseSafety:
    """denoise_strength 음수 방어 테스트."""

    def test_negative_strength_produces_positive(self):
        cfg = CleanAudioConfig(
            highpass_freq=0, lowpass_freq=0,
            denoise=True, denoise_strength=-30,
            remove_silence=False, normalize=False,
        )
        chain, names = _build_filter_chain(cfg)
        if "afftdn" in chain:
            assert "nf=--" not in chain
            assert "nf=-30" in chain


class TestAfftdnCheck:
    """afftdn 가용 여부 체크."""

    def test_returns_bool(self):
        result = _check_afftdn_available()
        assert isinstance(result, bool)

    @pytest.mark.skipif(
        not shutil.which("ffmpeg"),
        reason="ffmpeg not installed",
    )
    def test_ffmpeg_present(self):
        result = _check_afftdn_available()
        assert isinstance(result, bool)
