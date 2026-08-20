"""Microphone audio recorder using sounddevice."""

import time
import threading
import numpy as np
import sounddevice as sd
import lameenc


class AudioRecorder:
    """Records audio from the default microphone into an MP3 buffer."""

    SAMPLE_RATE = 16_000
    CHANNELS = 1
    DTYPE = "int16"
    MIN_DURATION = 0.3        # seconds — ignore accidental taps
    SILENCE_RMS_THRESHOLD = 200  # int16 RMS below this = silence

    def __init__(self, bitrate: int = 32) -> None:
        self._bitrate = bitrate
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()
        self._recording = False
        self._start_time: float = 0.0
        self._level = 0.0  # last chunk loudness, 0..1 (for UI)

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def level(self) -> float:
        """Loudness of the last audio chunk, normalized to 0..1."""
        return self._level

    # ---- public API ----

    def start(self) -> None:
        """Begin recording from the default input device."""
        with self._lock:
            self._frames.clear()
            self._recording = True
            self._level = 0.0
            self._start_time = time.perf_counter()
            self._stream = sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=self.CHANNELS,
                dtype=self.DTYPE,
                callback=self._audio_callback,
            )
            self._stream.start()

    def stop(self) -> bytes:
        """Stop recording and return MP3 bytes.

        Returns empty bytes if too short or too quiet.
        """
        with self._lock:
            duration = time.perf_counter() - self._start_time
            self._recording = False
            self._level = 0.0
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None

            # Skip too-short recordings (accidental taps)
            if duration < self.MIN_DURATION:
                return b""

            if not self._frames:
                return b""

            audio = np.concatenate(self._frames, axis=0)

            # Skip silence
            rms = np.sqrt(np.mean(audio.astype(np.float32) ** 2))
            if rms < self.SILENCE_RMS_THRESHOLD:
                return b""

            return self._encode_mp3(audio)

    # ---- internals ----

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if status:
            pass  # silently ignore minor xruns
        rms = np.sqrt(np.mean(indata.astype(np.float32) ** 2))
        self._level = float(min(1.0, (rms / 4000.0) ** 0.5))
        self._frames.append(indata.copy())

    def _encode_mp3(self, audio: np.ndarray) -> bytes:
        pcm = audio.tobytes()
        enc = lameenc.Encoder()
        enc.set_bit_rate(self._bitrate)
        enc.set_in_sample_rate(self.SAMPLE_RATE)
        enc.set_channels(self.CHANNELS)
        enc.set_quality(7)  # 7=fast
        mp3 = enc.encode(pcm)
        mp3 += enc.flush()
        # MUST be bytes, not bytearray: httpx treats a bytearray as an
        # iterable and falls back to chunked transfer with ONE CHUNK PER
        # BYTE, which made every upload ~9x slower.
        return bytes(mp3)

