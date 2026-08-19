import numpy as np
import pytest

from app.gap_detector import GapDetector, rms

SAMPLE_RATE = 1000  # small, synthetic - keeps test arrays tiny
LOUD = np.full(100, 1000, dtype=np.int16)
SILENT = np.zeros(100, dtype=np.int16)


def test_rms_of_silence_is_zero():
    assert rms(np.zeros(100, dtype=np.int16)) == 0.0


def test_rms_of_empty_array_is_zero():
    assert rms(np.array([], dtype=np.int16)) == 0.0


def test_rms_of_constant_signal_equals_its_amplitude():
    assert rms(np.full(100, 500, dtype=np.int16)) == pytest.approx(500.0)


def test_never_fires_on_continuous_loud_audio():
    detector = GapDetector(SAMPLE_RATE, silence_threshold=200, min_gap_seconds=0.5)
    fired = [detector.process_chunk(LOUD) for _ in range(20)]
    assert not any(fired)


def test_fires_once_after_sustained_silence():
    detector = GapDetector(SAMPLE_RATE, silence_threshold=200, min_gap_seconds=0.5)
    # 0.5s of silence at 1000Hz = 500 samples = 5 chunks of 100
    fired = [detector.process_chunk(SILENT) for _ in range(5)]
    assert fired.count(True) == 1
    assert fired[-1] is True


def test_does_not_fire_again_while_silence_continues():
    detector = GapDetector(SAMPLE_RATE, silence_threshold=200, min_gap_seconds=0.5)
    fired = [detector.process_chunk(SILENT) for _ in range(20)]
    assert fired.count(True) == 1


def test_brief_dip_shorter_than_min_gap_does_not_fire():
    detector = GapDetector(SAMPLE_RATE, silence_threshold=200, min_gap_seconds=0.5)
    fired = []
    fired += [detector.process_chunk(SILENT) for _ in range(2)]  # 0.2s, too short
    fired += [detector.process_chunk(LOUD) for _ in range(3)]  # audio resumes
    assert not any(fired)


def test_fires_again_on_a_second_independent_gap():
    detector = GapDetector(SAMPLE_RATE, silence_threshold=200, min_gap_seconds=0.5)
    first_gap = [detector.process_chunk(SILENT) for _ in range(5)]
    assert first_gap.count(True) == 1

    resume = [detector.process_chunk(LOUD) for _ in range(3)]
    assert not any(resume)

    second_gap = [detector.process_chunk(SILENT) for _ in range(5)]
    assert second_gap.count(True) == 1


def test_catches_a_gap_split_across_chunk_boundaries():
    # Regression test for a real bug found live (2026-08-18, see DEVLOG):
    # a genuine CD-player skip's silence measured ~1.55s, but it landed
    # across two separately-recorded chunks in a way that kept *each*
    # chunk's own whole-chunk RMS average above the silence threshold -
    # loud audio surrounding a partial silence dilutes the average enough
    # that the chunk never reads as silent, even though real,
    # long-enough-to-matter silence is present. Neither chunk here is
    # purely loud or purely silent, unlike every other test in this file.
    detector = GapDetector(SAMPLE_RATE, silence_threshold=200, min_gap_seconds=1.2)
    loud = np.full(100, 1000, dtype=np.int16)
    silent = np.zeros(100, dtype=np.int16)

    chunk_a = np.concatenate([np.tile(loud, 13), np.tile(silent, 7)])  # 1.3s loud, 0.7s silent
    chunk_b = np.concatenate([np.tile(silent, 6), np.tile(loud, 14)])  # 0.6s silent, 1.4s loud

    assert detector.process_chunk(chunk_a) is False
    assert detector.process_chunk(chunk_b) is True
