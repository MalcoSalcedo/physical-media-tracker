import numpy as np


def rms(samples: np.ndarray) -> float:
    """Root-mean-square energy of an audio chunk."""
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))


class GapDetector:
    """Detects the brief silence between tracks from a stream of audio chunks.

    Feed consecutive chunks via `process_chunk`. It fires a gap event
    (returns True) once a continuous span of silence at least
    `min_gap_seconds` long has been observed, and won't fire again until
    real audio resumes and then goes silent again - so one gap produces
    exactly one event, not one per chunk.
    """

    def __init__(
        self,
        sample_rate: int,
        silence_threshold: float = 200.0,
        min_gap_seconds: float = 1.5,
    ):
        self.sample_rate = sample_rate
        self.silence_threshold = silence_threshold
        self.min_gap_samples = int(min_gap_seconds * sample_rate)
        self._silent_samples = 0
        self._gap_fired = False

    def process_chunk(self, samples: np.ndarray) -> bool:
        """Feed in the next chunk of audio. Returns True on a new gap event."""
        if rms(samples) < self.silence_threshold:
            self._silent_samples += len(samples)
            if self._silent_samples >= self.min_gap_samples and not self._gap_fired:
                self._gap_fired = True
                return True
        else:
            self._silent_samples = 0
            self._gap_fired = False
        return False
