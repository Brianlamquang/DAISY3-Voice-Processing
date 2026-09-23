"""VieNeu context-based synthesis and chapter audio assembly for Task 2."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence

try:
    from pydub import AudioSegment
except ImportError:
    AudioSegment = None

try:
    from vieneu import Vieneu
except ImportError:
    Vieneu = None

from .normalize import clean_source_text, normalize_for_tts, prepare_tts_text


@dataclass(frozen=True)
class TTSSettings:
    voice: str
    backend: str
    max_sentences_per_chunk: int
    max_chars_per_chunk: int
    context_chunk_join_pause_ms: int
    paragraph_pause_ms: int
    section_pause_ms: int
    bitrate: str
    retries: int = 4
    default_frame_rate: int = 24000


@dataclass(frozen=True)
class Paragraph:
    p_id: str
    segments: List[Dict[str, Any]]


@dataclass(frozen=True)
class ContextChunk:
    p_id: str
    chunk_index: int
    segments: List[Dict[str, Any]]
    source_text: str
    tts_text: str


@dataclass(frozen=True)
class TimelineUnit:
    kind: str  # speech | section_break
    p_id: str
    chunk_index: int
    segments: List[Dict[str, Any]]
    source_text: str
    tts_text: str


def ensure_runtime_dependencies() -> None:
    missing: List[str] = []
    if Vieneu is None:
        missing.append("vieneu")
    if AudioSegment is None:
        missing.append("pydub")
    if missing:
        raise RuntimeError(
            f"Missing Python dependencies: {', '.join(missing)}. Install with: "
            "python -m pip install -r src/tts/requirements.txt"
        )
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError(
            "FFmpeg/ffprobe were not found in PATH. Run 'ffmpeg -version' and "
            "'ffprobe -version' before Task 2."
        )


def resolve_voice(tts: Any, requested_voice: str) -> str:
    voices = tts.list_preset_voices()
    ids = [str(voice_id) for _label, voice_id in voices]

    if requested_voice in ids:
        return requested_voice

    for label, voice_id in voices:
        if requested_voice.lower() in str(label).lower():
            return str(voice_id)

    available = ", ".join(f"{label} ({voice_id})" for label, voice_id in voices)
    raise RuntimeError(
        f"VieNeu preset voice {requested_voice!r} was not found. Available: {available}"
    )


def group_segments_by_paragraph(segments: Sequence[Dict[str, Any]]) -> List[Paragraph]:
    """Group only consecutive segments with the same Task-1 ``p_id``."""
    paragraphs: List[Paragraph] = []
    current_p_id: str | None = None
    current_segments: List[Dict[str, Any]] = []

    for segment in segments:
        p_id = str(segment["p_id"])
        if current_p_id is None:
            current_p_id = p_id
        if p_id != current_p_id:
            paragraphs.append(Paragraph(current_p_id, current_segments))
            current_p_id = p_id
            current_segments = []
        current_segments.append(segment)

    if current_segments:
        paragraphs.append(Paragraph(current_p_id or "", current_segments))

    return paragraphs


def _make_context_chunk(
    p_id: str,
    chunk_index: int,
    segments: List[Dict[str, Any]],
) -> ContextChunk:
    source_text = " ".join(clean_source_text(seg["text"]) for seg in segments)
    tts_parts = [prepare_tts_text(seg["text"]) for seg in segments]
    if any(not part for part in tts_parts):
        bad_ids = [
            str(seg["sent_id"])
            for seg, part in zip(segments, tts_parts)
            if not part
        ]
        raise ValueError(f"Empty tts_text inside speech chunk: {bad_ids}")

    return ContextChunk(
        p_id=p_id,
        chunk_index=chunk_index,
        segments=list(segments),
        source_text=source_text,
        tts_text=" ".join(tts_parts),
    )


def build_context_chunks(
    paragraph: Paragraph,
    settings: TTSSettings,
) -> List[TimelineUnit]:
    """Build speech chunks and section-break units without crossing paragraphs."""
    units: List[TimelineUnit] = []
    current: List[Dict[str, Any]] = []
    current_chars = 0
    speech_chunk_index = 0

    def flush() -> None:
        nonlocal current, current_chars, speech_chunk_index
        if not current:
            return
        speech_chunk_index += 1
        chunk = _make_context_chunk(paragraph.p_id, speech_chunk_index, current)
        units.append(
            TimelineUnit(
                kind="speech",
                p_id=chunk.p_id,
                chunk_index=chunk.chunk_index,
                segments=chunk.segments,
                source_text=chunk.source_text,
                tts_text=chunk.tts_text,
            )
        )
        current = []
        current_chars = 0

    for segment in paragraph.segments:
        normalized = normalize_for_tts(segment["text"])
        if normalized.is_section_break:
            flush()
            units.append(
                TimelineUnit(
                    kind="section_break",
                    p_id=paragraph.p_id,
                    chunk_index=0,
                    segments=[segment],
                    source_text=segment["text"],
                    tts_text="",
                )
            )
            continue

        sentence = clean_source_text(segment["text"])
        added_chars = len(sentence) + (1 if current else 0)
        too_many_sentences = len(current) >= settings.max_sentences_per_chunk
        too_many_chars = bool(current) and (
            current_chars + added_chars > settings.max_chars_per_chunk
        )

        if too_many_sentences or too_many_chars:
            flush()

        if current:
            current_chars += 1
        current.append(segment)
        current_chars += len(sentence)

    flush()
    return units


def build_timeline_units(
    segments: Sequence[Dict[str, Any]],
    settings: TTSSettings,
) -> List[TimelineUnit]:
    units: List[TimelineUnit] = []
    for paragraph in group_segments_by_paragraph(segments):
        units.extend(build_context_chunks(paragraph, settings))
    return units


def _make_silence(reference_audio: Any | None, duration_ms: int, frame_rate: int) -> Any:
    silence = AudioSegment.silent(
        duration=max(0, int(duration_ms)),
        frame_rate=(reference_audio.frame_rate if reference_audio is not None else frame_rate),
    )
    if reference_audio is not None:
        silence = silence.set_channels(reference_audio.channels).set_sample_width(
            reference_audio.sample_width
        )
    else:
        silence = silence.set_channels(1)
    return silence


def _chapter_audio_name(chapter_idx: int) -> str:
    return "Gioi_Thieu.mp3" if chapter_idx == 0 else f"Chuong_{chapter_idx:02d}.mp3"


def _structural_pause_after(
    units: Sequence[TimelineUnit],
    index: int,
    settings: TTSSettings,
) -> int:
    current = units[index]
    if current.kind == "section_break" or index + 1 >= len(units):
        return 0

    next_unit = units[index + 1]
    if next_unit.kind == "section_break":
        return 0
    if current.p_id == next_unit.p_id:
        return settings.context_chunk_join_pause_ms
    return settings.paragraph_pause_ms


def _sentence_metadata(segment: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_for_tts(segment["text"])
    return {
        "sent_id": segment["sent_id"],
        "smil_sid": segment["smil_sid"],
        "p_id": segment["p_id"],
        "seq_id": segment["seq_id"],
        "source_text": segment["text"],
        "tts_text": normalized.tts_text,
    }


class VieNeuSynthesizer:
    """One VieNeu instance reused across chapters to avoid repeated model loading."""

    def __init__(self, settings: TTSSettings) -> None:
        ensure_runtime_dependencies()
        self.settings = settings
        self.tts = Vieneu(backend=settings.backend)
        self.voice = resolve_voice(self.tts, settings.voice)

    def _infer_chunk(self, text: str, wav_path: Path) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, self.settings.retries + 1):
            try:
                audio_np = self.tts.infer(text, voice=self.voice)
                self.tts.save(audio_np, wav_path)
                if not wav_path.exists() or wav_path.stat().st_size <= 0:
                    raise RuntimeError("VieNeu returned an empty WAV file")
                return AudioSegment.from_file(wav_path, format="wav")
            except Exception as exc:
                last_error = exc
                wav_path.unlink(missing_ok=True)
                if attempt >= self.settings.retries:
                    break
        raise RuntimeError(
            f"VieNeu failed after {self.settings.retries} attempts: {last_error}"
        ) from last_error

    def synthesize_chapter(
        self,
        handoff: Dict[str, Any],
        chapter_output_dir: Path,
    ) -> Dict[str, Any]:
        chapter_output_dir.mkdir(parents=True, exist_ok=True)
        segments: List[Dict[str, Any]] = handoff["segments"]
        units = build_timeline_units(segments, self.settings)

        chapter_idx = int(handoff["chapter_idx"])
        audio_name = _chapter_audio_name(chapter_idx)
        final_audio_path = chapter_output_dir / audio_name

        timeline_ms = 0
        chapter_audio = AudioSegment.empty()
        output_chunks: List[Dict[str, Any]] = []
        p_chunk_counts: Dict[str, int] = {}

        with tempfile.TemporaryDirectory(prefix="task2_vieneu_") as temp_dir_name:
            temp_dir = Path(temp_dir_name)

            for index, unit in enumerate(units):
                start_ms = timeline_ms

                if unit.kind == "section_break":
                    section_audio = _make_silence(
                        None,
                        self.settings.section_pause_ms,
                        self.settings.default_frame_rate,
                    )
                    chapter_audio += section_audio
                    timeline_ms += len(section_audio)
                    output_chunks.append(
                        {
                            "kind": "section_break",
                            "chunk_id": f"{unit.p_id}_section_break_{index + 1:02d}",
                            "p_id": unit.p_id,
                            "start": round(start_ms / 1000.0, 3),
                            "speech_end": round(start_ms / 1000.0, 3),
                            "end": round(timeline_ms / 1000.0, 3),
                            "pause_after_ms": self.settings.section_pause_ms,
                            "sentences": [_sentence_metadata(seg) for seg in unit.segments],
                        }
                    )
                    continue

                p_chunk_counts[unit.p_id] = p_chunk_counts.get(unit.p_id, 0) + 1
                chunk_no = p_chunk_counts[unit.p_id]
                temp_wav = temp_dir / f"{unit.p_id}_chunk_{chunk_no:02d}.wav"
                speech_audio = self._infer_chunk(unit.tts_text, temp_wav)

                speech_end_ms = start_ms + len(speech_audio)
                pause_ms = _structural_pause_after(units, index, self.settings)
                combined = speech_audio + _make_silence(
                    speech_audio,
                    pause_ms,
                    self.settings.default_frame_rate,
                )
                chapter_audio += combined
                timeline_ms += len(combined)

                output_chunks.append(
                    {
                        "kind": "speech",
                        "chunk_id": f"{unit.p_id}_chunk_{chunk_no:02d}",
                        "p_id": unit.p_id,
                        "start": round(start_ms / 1000.0, 3),
                        "speech_end": round(speech_end_ms / 1000.0, 3),
                        "end": round(timeline_ms / 1000.0, 3),
                        "pause_after_ms": int(pause_ms),
                        "source_text": unit.source_text,
                        "tts_text": unit.tts_text,
                        "sentences": [_sentence_metadata(seg) for seg in unit.segments],
                    }
                )

        temp_final = final_audio_path.with_suffix(".tmp.mp3")
        try:
            chapter_audio.export(temp_final, format="mp3", bitrate=self.settings.bitrate)
            if not temp_final.exists() or temp_final.stat().st_size <= 0:
                raise RuntimeError("Final chapter MP3 export produced an empty file")
            os.replace(temp_final, final_audio_path)
        finally:
            temp_final.unlink(missing_ok=True)

        decoded_final = AudioSegment.from_file(final_audio_path, format="mp3")

        return {
            "metadata": handoff["metadata"],
            "chapter_idx": handoff["chapter_idx"],
            "chapter_title": handoff["chapter_title"],
            "total_paragraphs": handoff["total_paragraphs"],
            "total_sentences": handoff["total_sentences"],
            "audio_file": audio_name,
            "audio_duration": round(len(decoded_final) / 1000.0, 3),
            "tts": {
                "engine": "vieneu",
                "voice": self.settings.voice,
                "resolved_voice": self.voice,
                "backend": self.settings.backend,
                "max_sentences_per_context_chunk": self.settings.max_sentences_per_chunk,
                "max_chars_per_context_chunk": self.settings.max_chars_per_chunk,
                "context_chunk_join_pause_ms": self.settings.context_chunk_join_pause_ms,
                "paragraph_pause_ms": self.settings.paragraph_pause_ms,
                "section_pause_ms": self.settings.section_pause_ms,
                "internal_punctuation": "native",
                "bitrate": self.settings.bitrate,
            },
            "chunks": output_chunks,
        }
