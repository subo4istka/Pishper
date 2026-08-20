"""Continuous recording with Voice Activity Detection (VAD).

Keeps the mic open, detects speech segments by RMS energy,
and fires a callback with encoded MP3 when a speech segment ends.
"""

import queue
import threading
from collections import deque

import numpy as np
import sounddevice as sd
import lameenc


class ContinuousRecorder:
    """Continuously records, detects speech, and yields MP3 chunks."""

    SAMPLE_RATE = 16_000
    CHANNELS = 1
    DTYPE = "int16"
    CHUNK_SAMPLES = 1600       # 100ms per callback chunk (at 16kHz)

    # VAD thresholds
    SPEECH_RMS = 150           # RMS above this = speech
    MIN_SPEECH_MS = 300        # ignore speech segments shorter than this
    MAX_SPEECH_MS = 60_000     # force-flush after this much continuous speech
    PRE_ROLL_CHUNKS = 4        # 400ms of audio kept before speech starts
                               # (quiet onset of the first word isn't clipped)

    def __init__(self, on_speech_chunk: callable, silence_timeout_ms: int = 2000, bitrate: int = 32) -> None:
        """
        Args:
            on_speech_chunk: called with (mp3_bytes: bytes) in a bg thread
                             when a speech segment ends.
            silence_timeout_ms: ms of silence to end a speech segment.
        """
        self._on_speech = on_speech_chunk
        self._bitrate = bitrate
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()
        self._active = False

        # VAD state
        self._in_speech = False
        self._speech_frames: list[np.ndarray] = []
        self._silence_chunks = 0  # how many consecutive silent chunks
        self._speech_chunks = 0   # how many consecutive speech chunks
        self._pre_roll: deque[np.ndarray] = deque(maxlen=self.PRE_ROLL_CHUNKS)
        self._level = 0.0         # last chunk loudness, 0..1 (for UI)

        # Single encoder worker: keeps the audio callback fast and
        # guarantees segments are encoded/delivered in spoken order.
        self._encode_queue: queue.Queue = queue.Queue()
        threading.Thread(target=self._encode_loop, daemon=True).start()

        # Pre-compute chunk counts
        ms_per_chunk = self.CHUNK_SAMPLES / self.SAMPLE_RATE * 1000  # 100ms
        self._silence_limit = int(silence_timeout_ms / ms_per_chunk)
        self._min_speech_count = int(
            self.MIN_SPEECH_MS / (self.CHUNK_SAMPLES / self.SAMPLE_RATE * 1000)
        )
        self._max_speech_count = int(
            self.MAX_SPEECH_MS / (self.CHUNK_SAMPLES / self.SAMPLE_RATE * 1000)
        )

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def in_speech(self) -> bool:
        return self._in_speech

    @property
    def level(self) -> float:
        """Loudness of the last audio chunk, normalized to 0..1."""
        return self._level

    def start(self) -> None:
        with self._lock:
            if self._active:
                return
            self._active = True
            self._in_speech = False
            self._speech_frames.clear()
            self._silence_chunks = 0
            self._speech_chunks = 0
            self._total_frames = 0
            self._pre_roll.clear()
            self._level = 0.0
            self._stream = sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=self.CHANNELS,
                dtype=self.DTYPE,
                blocksize=self.CHUNK_SAMPLES,
                callback=self._audio_cb,
            )
            self._stream.start()

    def stop(self) -> None:
        with self._lock:
            self._active = False
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None
            # Flush any remaining speech
            if self._in_speech and self._speech_frames:
                self._flush_speech()
            self._speech_frames.clear()

    def _audio_cb(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if not self._active:
            return

        rms = np.sqrt(np.mean(indata.astype(np.float32) ** 2))
        self._level = float(min(1.0, (rms / 4000.0) ** 0.5))
        is_loud = rms > self.SPEECH_RMS

        if is_loud:
            self._silence_chunks = 0
            self._speech_chunks += 1
            self._total_frames += 1
            if not self._in_speech:
                self._in_speech = True
                # Prepend pre-roll so the quiet onset of the phrase isn't lost
                self._speech_frames.extend(self._pre_roll)
                self._pre_roll.clear()
            self._speech_frames.append(indata.copy())
            # Force-flush if speaking too long without pause
            if self._total_frames >= self._max_speech_count:
                self._flush_speech()
                self._in_speech = False
                self._speech_chunks = 0
                self._total_frames = 0
        else:
            if self._in_speech:
                self._silence_chunks += 1
                self._speech_frames.append(indata.copy())
                if self._silence_chunks >= self._silence_limit:
                    if self._speech_chunks >= self._min_speech_count:
                        self._flush_speech()
                    else:
                        self._speech_frames.clear()
                    self._in_speech = False
                    self._speech_chunks = 0
                    self._silence_chunks = 0
                    self._total_frames = 0
            else:
                # Idle: keep a rolling window for the next speech onset
                self._pre_roll.append(indata.copy())

    def _flush_speech(self) -> None:
        """Queue accumulated speech frames for encoding (in order)."""
        if not self._speech_frames:
            return
        audio = np.concatenate(self._speech_frames, axis=0)
        self._speech_frames.clear()
        self._encode_queue.put(audio)

    def _encode_loop(self) -> None:
        """Worker thread: encodes queued segments sequentially."""
        while True:
            audio = self._encode_queue.get()
            try:
                pcm = audio.tobytes()
                enc = lameenc.Encoder()
                enc.set_bit_rate(self._bitrate)
                enc.set_in_sample_rate(self.SAMPLE_RATE)
                enc.set_channels(self.CHANNELS)
                enc.set_quality(7)
                mp3 = enc.encode(pcm)
                mp3 += enc.flush()
                if mp3:
                    self._on_speech(bytes(mp3))
            except Exception:
                pass  # never kill the worker on a bad segment
