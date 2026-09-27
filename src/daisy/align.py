"""Sentence times inside a Task 2 speech window.

Headings, scene breaks, and one-sentence chunks already have exact edges.
A multi-sentence chunk is one VieNeu utterance, so alignment searches only
inside ``[start, speech_end]`` and the trailing structural pause stays on
the last sentence. CTC is the acoustic fit. A bad span falls back to
character weights of ``tts_text`` inside that same window.
"""

from __future__ import annotations

import array
import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any, Dict, List, Sequence

from src.config import TASK3_ALIGN_MODEL


def sec_to_ms(value: float) -> int:
    return int(round(float(value) * 1000))


def require_ffmpeg() -> None:
    missing = [name for name in ("ffmpeg", "ffprobe") if shutil.which(name) is None]
    if missing:
        raise RuntimeError(f"Required on PATH: {', '.join(missing)}")


def probe_duration_ms(path: Path) -> int:
    require_ffmpeg()
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"ffprobe failed for {path}")
    return sec_to_ms(float(result.stdout.strip()))


def proportional_spans(weights: Sequence[int], start_ms: int, end_ms: int) -> List[tuple[int, int]]:
    """Split ``[start_ms, end_ms]`` into strictly increasing spans."""
    if end_ms <= start_ms:
        raise ValueError("empty alignment window")
    if not weights:
        raise ValueError("no sentences to place")
    total = sum(weights)
    if total <= 0:
        raise ValueError("alignment weights must be positive")

    edges = [start_ms]
    consumed = 0
    for weight in weights[:-1]:
        consumed += weight
        edge = start_ms + (end_ms - start_ms) * consumed // total
        if edge <= edges[-1]:
            edge = edges[-1] + 1
        if edge >= end_ms:
            edge = end_ms - 1
        edges.append(edge)
    edges.append(end_ms)
    for index in range(len(edges) - 2, 0, -1):
        if edges[index] >= edges[index + 1]:
            edges[index] = edges[index + 1] - 1
    if any(edges[index] >= edges[index + 1] for index in range(len(edges) - 1)):
        raise ValueError(
            f"window {end_ms - start_ms} ms is too short for {len(weights)} sentences"
        )
    return list(zip(edges[:-1], edges[1:]))


def _weights(sentences: Sequence[Dict[str, Any]]) -> List[int]:
    return [max(len(str(sentence.get("tts_text", "")).strip()), 1) for sentence in sentences]


class SentenceAligner:
    """CTC forced aligner with a per-chunk proportional fallback."""

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = os.environ.get("TASK3_ALIGN_MODEL", model_name or TASK3_ALIGN_MODEL)
        self.engine = "unloaded"
        self.error: str | None = None
        self.chunk_error: str | None = None
        self._ready = False
        self._attempted = False
        self._torch: Any = None
        self._processor: Any = None
        self._model: Any = None
        self._blank_id = 0

    def ensure(self) -> bool:
        if self._attempted:
            return self._ready
        self._attempted = True
        try:
            os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
            os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
            import torch
            from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
            from transformers.utils import logging as hf_logging

            hf_logging.set_verbosity_error()
        except ImportError as exc:
            self.engine = "proportional"
            self.error = f"CTC dependencies are not installed ({exc.__class__.__name__}: {exc})"
            return False
        try:
            torch.set_num_threads(min(4, os.cpu_count() or 1))
            processor = Wav2Vec2Processor.from_pretrained(self.model_name)
            model = Wav2Vec2ForCTC.from_pretrained(self.model_name)
            model.eval()
            blank = processor.tokenizer.pad_token_id
            self._torch = torch
            self._processor = processor
            self._model = model
            self._blank_id = 0 if blank is None else int(blank)
            self._ready = True
            self.engine = "ctc"
            self.error = None
            return True
        except Exception as exc:
            self.engine = "proportional"
            self.error = f"CTC model load failed: {exc}"
            return False

    def align_speech(
        self,
        audio_path: Path,
        start_s: float,
        speech_end_s: float,
        sentences: Sequence[Dict[str, Any]],
    ) -> tuple[List[tuple[int, int]], str]:
        """Return absolute spans covering ``[start, speech_end]`` and the method name."""
        start_ms = sec_to_ms(start_s)
        speech_ms = sec_to_ms(speech_end_s)
        if len(sentences) == 1:
            if speech_ms <= start_ms:
                raise ValueError(f"{sentences[0].get('sent_id')} has an empty speech window")
            return [(start_ms, speech_ms)], "exact"
        if self.ensure():
            try:
                spans = self._ctc_spans(audio_path, start_s, speech_end_s, sentences)
            except Exception as exc:
                spans = None
                if self.chunk_error is None:
                    self.chunk_error = f"{exc.__class__.__name__}: {exc}"
            if spans is not None:
                return spans, "aligned"
        return proportional_spans(_weights(sentences), start_ms, speech_ms), "proportional"

    def _token_ids(self, text: str) -> List[int]:
        tokenizer = self._processor.tokenizer
        encoded = tokenizer(text, add_special_tokens=False)
        raw_ids = encoded["input_ids"] if isinstance(encoded, dict) else encoded.input_ids
        skip = {self._blank_id}
        for attr in ("bos_token_id", "eos_token_id", "cls_token_id", "sep_token_id"):
            value = getattr(tokenizer, attr, None)
            if value is not None:
                skip.add(int(value))
        return [int(token_id) for token_id in raw_ids if int(token_id) not in skip]

    def _ctc_spans(
        self,
        audio_path: Path,
        start_s: float,
        speech_end_s: float,
        sentences: Sequence[Dict[str, Any]],
    ) -> List[tuple[int, int]] | None:
        groups = [self._token_ids(str(sentence.get("tts_text", ""))) for sentence in sentences]
        if any(not group for group in groups):
            return None
        tokens: List[int] = [token for group in groups for token in group]
        with tempfile.TemporaryDirectory(prefix="task3_align_") as temp_name:
            wav_path = Path(temp_name) / "slice.wav"
            _extract_wav(audio_path, start_s, speech_end_s, wav_path)
            waveform, sample_rate = self._load_waveform(wav_path)
        if waveform.numel() == 0 or sample_rate <= 0:
            return None

        inputs = self._processor(
            waveform.squeeze(0).numpy(),
            sampling_rate=sample_rate,
            return_tensors="pt",
            padding=False,
        )
        with self._torch.inference_mode():
            logits = self._model(inputs.input_values).logits
        emissions = self._torch.log_softmax(logits, dim=-1)
        targets = self._torch.tensor([tokens], dtype=self._torch.int32)
        from torchaudio.functional import forced_align, merge_tokens

        alignments, scores = forced_align(emissions, targets, blank=self._blank_id)
        spans = merge_tokens(alignments[0], scores[0].exp(), blank=self._blank_id)
        if len(spans) != len(tokens):
            return None

        frame_count = int(emissions.shape[1])
        if frame_count <= 0:
            return None
        start_ms = sec_to_ms(start_s)
        speech_ms = sec_to_ms(speech_end_s)
        window = speech_ms - start_ms
        if window <= 0:
            return None

        cursor = 0
        speech_starts: List[int] = []
        for group in groups:
            group_spans = spans[cursor : cursor + len(group)]
            cursor += len(group)
            frame = int(group_spans[0].start)
            speech_starts.append(start_ms + window * frame // frame_count)
        edges = [start_ms, *speech_starts[1:], speech_ms]
        for index in range(1, len(edges)):
            if edges[index] <= edges[index - 1]:
                edges[index] = edges[index - 1] + 1
        if edges[-1] != speech_ms or any(
            edges[index] >= edges[index + 1] for index in range(len(edges) - 1)
        ):
            return None
        return list(zip(edges[:-1], edges[1:]))

    def _load_waveform(self, wav_path: Path) -> tuple[Any, int]:
        # ffmpeg writes 16-bit PCM. Avoid torchaudio.load, which now requires torchcodec.
        with wave.open(str(wav_path), "rb") as handle:
            sample_rate = handle.getframerate()
            channels = handle.getnchannels()
            if handle.getsampwidth() != 2:
                raise RuntimeError(f"{wav_path.name} is not 16-bit PCM")
            frames = handle.readframes(handle.getnframes())
        samples = array.array("h")
        samples.frombytes(frames)
        waveform = self._torch.tensor(samples, dtype=self._torch.float32).div_(32768.0)
        if channels > 1:
            waveform = waveform.reshape(-1, channels).mean(dim=1)
        if sample_rate != 16000:
            raise RuntimeError(f"expected 16 kHz audio, got {sample_rate}")
        return waveform.unsqueeze(0), sample_rate


def _extract_wav(audio_path: Path, start_s: float, end_s: float, wav_path: Path) -> None:
    require_ffmpeg()
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(audio_path),
            "-ss",
            f"{start_s:.3f}",
            "-to",
            f"{end_s:.3f}",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(wav_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not wav_path.exists() or wav_path.stat().st_size <= 0:
        raise RuntimeError(result.stderr.strip() or f"ffmpeg could not slice {audio_path}")
