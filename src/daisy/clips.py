"""Build contiguous sentence clips from a DTBook and Task 2 timestamps."""

from __future__ import annotations

import json
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Sequence

from src.daisy.align import SentenceAligner, probe_duration_ms, sec_to_ms


DTBOOK_NS = {"dt": "http://www.daisy.org/z3986/2005/dtbook/"}
DURATION_TOLERANCE_MS = 250


@dataclass
class Clip:
    sent_id: str
    smil_sid: str
    container_id: str
    clip_begin_ms: int
    clip_end_ms: int
    method: str
    source_text: str


@dataclass
class ChapterSync:
    chapter_idx: int
    chapter_title: str
    book_title: str
    author: str
    package_title: str
    metadata: Dict[str, Any]
    audio_file: str
    audio_duration_ms: int
    clips: List[Clip]
    aligner_engine: str
    aligner_model: str
    aligner_error: str | None
    counts: Dict[str, int] = field(default_factory=dict)


def chapter_folder_name(chapter_idx: int) -> str:
    if chapter_idx == 0:
        return "Trong_Gia_Dinh-Gioi_Thieu"
    return f"Trong_Gia_Dinh-Chuong_{chapter_idx:02d}"


def norm_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text or "").split())


def _fragment(smilref: str, owner: str) -> str:
    if "#" not in smilref:
        raise ValueError(f"{owner} is missing a SMIL fragment in {smilref!r}")
    fragment = smilref.split("#", 1)[1].strip()
    if not fragment:
        raise ValueError(f"{owner} has an empty SMIL fragment")
    return fragment


def _load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _dtbook_rows(dtbook_path: Path) -> tuple[str, List[Dict[str, Any]]]:
    """Return the chapter package title and document-order sentence rows."""
    root = ET.parse(dtbook_path).getroot()
    package_title = ""
    for meta in root.findall("./dt:head/dt:meta", DTBOOK_NS):
        if meta.get("name") == "dc:Title" and meta.get("content"):
            package_title = meta.get("content", "")
            break

    rows: List[Dict[str, Any]] = []
    containers = [
        root.find(".//dt:doctitle", DTBOOK_NS),
        root.find(".//dt:docauthor", DTBOOK_NS),
        root.find(".//dt:h1", DTBOOK_NS),
        *root.findall(".//dt:p", DTBOOK_NS),
    ]
    for container in containers:
        if container is None:
            raise ValueError(f"{dtbook_path.name} is missing doctitle, docauthor, h1, or a paragraph")
        smil_container_id = _fragment(str(container.get("smilref", "")), f"<{container.tag}>")
        xml_container_id = str(container.get("id", ""))
        sentences = container.findall("./dt:sent", DTBOOK_NS)
        if not sentences:
            raise ValueError(f"SMIL container {smil_container_id} has no sentences")
        for sent in sentences:
            sent_id = str(sent.get("id", ""))
            rows.append(
                {
                    "sent_id": sent_id,
                    "smil_sid": _fragment(str(sent.get("smilref", "")), sent_id or smil_container_id),
                    "smil_container_id": smil_container_id,
                    "xml_container_id": xml_container_id,
                    "source_text": norm_text("".join(sent.itertext())),
                }
            )
    if not package_title:
        raise ValueError(f"{dtbook_path.name} is missing dc:Title")
    return package_title, rows


def _timestamp_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    headings = payload.get("headings")
    chunks = payload.get("chunks")
    if not isinstance(headings, list) or len(headings) != 3:
        raise ValueError("timestamps.json must contain exactly three headings")
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("timestamps.json must contain body chunks")

    rows: List[Dict[str, Any]] = []
    previous_end = 0.0
    for heading in headings:
        start = float(heading["start"])
        end = float(heading["end"])
        speech_end = float(heading["speech_end"])
        if abs(start - previous_end) > 0.025 or speech_end <= start or end < speech_end:
            raise ValueError(f"heading {heading.get('sent_id')} breaks the timeline")
        rows.append(
            {
                "kind": "heading",
                "sent_id": str(heading["sent_id"]),
                "smil_sid": str(heading["smil_sid"]),
                "xml_container_id": str(heading["container_id"]),
                "source_text": norm_text(str(heading["source_text"])),
                "tts_text": str(heading.get("tts_text", "")),
                "start": start,
                "speech_end": speech_end,
                "end": end,
            }
        )
        previous_end = end

    for chunk in chunks:
        start = float(chunk["start"])
        end = float(chunk["end"])
        speech_end = float(chunk["speech_end"])
        sentences = chunk.get("sentences")
        if abs(start - previous_end) > 0.025 or end < speech_end or not isinstance(sentences, list):
            raise ValueError(f"chunk {chunk.get('chunk_id')} breaks the timeline")
        if not sentences:
            raise ValueError(f"chunk {chunk.get('chunk_id')} has no sentences")
        for sentence in sentences:
            rows.append(
                {
                    "kind": str(chunk.get("kind", "")),
                    "sent_id": str(sentence["sent_id"]),
                    "smil_sid": str(sentence["smil_sid"]),
                    "smil_container_id": str(sentence["seq_id"]),
                    "xml_container_id": str(sentence["p_id"]),
                    "source_text": norm_text(str(sentence["source_text"])),
                    "tts_text": str(sentence.get("tts_text", "")),
                    "start": start,
                    "speech_end": speech_end,
                    "end": end,
                    "chunk_id": str(chunk.get("chunk_id", "")),
                }
            )
        previous_end = end
    return rows


def _check_segments(segments_path: Path, body_rows: Sequence[Dict[str, Any]]) -> None:
    payload = _load_json(segments_path)
    segments = payload.get("segments")
    if not isinstance(segments, list):
        raise ValueError("segments.json has no segments list")
    if len(segments) != len(body_rows):
        raise ValueError(
            f"body sentence count differs: dtbook={len(body_rows)} segments={len(segments)}"
        )
    for index, (segment, row) in enumerate(zip(segments, body_rows)):
        if str(segment.get("sent_id")) != row["sent_id"] or str(segment.get("smil_sid")) != row["smil_sid"]:
            raise ValueError(f"body sentence {index} id differs between DTBook and segments.json")
        if norm_text(str(segment.get("text", ""))) != row["source_text"]:
            raise ValueError(f"{row['sent_id']} text differs between DTBook and segments.json")
        if str(segment.get("seq_id")) != row["smil_container_id"]:
            raise ValueError(f"{row['sent_id']} seq_id does not match the paragraph smilref")
        if str(segment.get("p_id")) != row["xml_container_id"]:
            raise ValueError(f"{row['sent_id']} p_id does not match the DTBook paragraph")


def _group_units(rows: Sequence[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    groups: List[List[Dict[str, Any]]] = []
    for row in rows:
        key = (row["kind"], row["start"], row["end"], row.get("chunk_id", row["sent_id"]))
        if groups and (
            groups[-1][0]["kind"],
            groups[-1][0]["start"],
            groups[-1][0]["end"],
            groups[-1][0].get("chunk_id", groups[-1][0]["sent_id"]),
        ) == key and row["kind"] != "heading":
            groups[-1].append(row)
            continue
        groups.append([row])
    return groups


def build_sync(
    chapter_idx: int,
    task1_dir: Path,
    task2_dir: Path,
    aligner: SentenceAligner,
) -> ChapterSync:
    folder = chapter_folder_name(chapter_idx)
    source_dir = task1_dir / folder
    audio_dir = task2_dir / folder
    dtbook_path = source_dir / "dtbook.xml"
    segments_path = source_dir / "segments.json"
    timestamp_path = audio_dir / "timestamps.json"
    for path in (dtbook_path, segments_path, timestamp_path):
        if not path.exists():
            raise FileNotFoundError(path)

    package_title, dtbook_rows = _dtbook_rows(dtbook_path)
    if len(dtbook_rows) < 4:
        raise ValueError("DTBook does not contain heading sentences plus body text")
    _check_segments(segments_path, dtbook_rows[3:])

    timestamps = _load_json(timestamp_path)
    timed_rows = _timestamp_rows(timestamps)
    if len(timed_rows) != len(dtbook_rows):
        raise ValueError(
            f"sentence coverage differs: dtbook={len(dtbook_rows)} timestamps={len(timed_rows)}"
        )
    identity_keys = ("sent_id", "smil_sid", "xml_container_id", "source_text")
    for dtbook_row, timed_row in zip(dtbook_rows, timed_rows):
        for key in identity_keys:
            if dtbook_row[key] != timed_row[key]:
                raise ValueError(f"{dtbook_row['sent_id']} {key} differs between DTBook and timestamps")
        if timed_row["kind"] != "heading" and dtbook_row["smil_container_id"] != timed_row["smil_container_id"]:
            raise ValueError(f"{dtbook_row['sent_id']} seq_id does not match the DTBook smilref")
        timed_row["smil_container_id"] = dtbook_row["smil_container_id"]

    audio_file = str(timestamps.get("audio_file", ""))
    audio_path = audio_dir / audio_file
    if not audio_file or not audio_path.exists() or audio_path.stat().st_size <= 0:
        raise FileNotFoundError(f"missing chapter audio: {audio_path}")
    timeline_end_ms = sec_to_ms(float(timed_rows[-1]["end"]))
    audio_duration_ms = probe_duration_ms(audio_path)
    if abs(audio_duration_ms - timeline_end_ms) > DURATION_TOLERANCE_MS:
        raise ValueError(
            f"audio duration {audio_duration_ms} ms differs from timeline {timeline_end_ms} ms"
        )

    clips: List[Clip] = []
    for group in _group_units(timed_rows):
        kind = group[0]["kind"]
        start_ms = sec_to_ms(group[0]["start"])
        speech_ms = sec_to_ms(group[0]["speech_end"])
        end_ms = sec_to_ms(group[0]["end"])
        if kind == "heading":
            spans, method = [(start_ms, end_ms)], "exact"
        elif kind == "section_break":
            if len(group) != 1:
                raise ValueError(f"{group[0].get('chunk_id')} section break maps multiple sentences")
            spans, method = [(start_ms, end_ms)], "silence"
        else:
            if kind != "speech":
                raise ValueError(f"unknown chunk kind {kind!r}")
            spans, method = aligner.align_speech(
                audio_path,
                group[0]["start"],
                group[0]["speech_end"],
                group,
            )
            # The measured pause after the utterance stays on the last sentence
            # so playback does not jump over the silence Task 2 mixed in.
            spans[-1] = (spans[-1][0], end_ms)
        if len(spans) != len(group) or spans[0][0] != start_ms or spans[-1][1] != end_ms:
            raise ValueError(f"clip placement failed for {group[0]['sent_id']}")
        for row, (begin_ms, finish_ms) in zip(group, spans):
            if finish_ms <= begin_ms:
                raise ValueError(f"{row['sent_id']} received an empty clip")
            if kind == "speech" and begin_ms > speech_ms:
                raise ValueError(f"{row['sent_id']} starts after the spoken window")
            clips.append(
                Clip(
                    sent_id=row["sent_id"],
                    smil_sid=row["smil_sid"],
                    container_id=row["smil_container_id"],
                    clip_begin_ms=begin_ms,
                    clip_end_ms=finish_ms,
                    method=method,
                    source_text=row["source_text"],
                )
            )

    if clips[-1].clip_end_ms != audio_duration_ms:
        if clips[-1].clip_begin_ms >= audio_duration_ms:
            raise ValueError("decoded audio ends before the last sentence starts")
        clips[-1].clip_end_ms = audio_duration_ms
    if clips[0].clip_begin_ms != 0:
        raise ValueError("timeline does not start at 0")
    for index in range(len(clips) - 1):
        if clips[index].clip_end_ms != clips[index + 1].clip_begin_ms:
            raise ValueError(
                f"gap between {clips[index].sent_id} and {clips[index + 1].sent_id}"
            )

    counts: Dict[str, int] = {}
    for clip in clips:
        counts[clip.method] = counts.get(clip.method, 0) + 1
    aligner_error = aligner.error
    if counts.get("aligned", 0) == 0 and aligner.chunk_error:
        aligner_error = aligner.chunk_error
    return ChapterSync(
        chapter_idx=chapter_idx,
        chapter_title=str(timestamps["chapter_title"]),
        book_title=dtbook_rows[0]["source_text"],
        author=dtbook_rows[1]["source_text"],
        package_title=package_title,
        metadata=dict(timestamps["metadata"]),
        audio_file=audio_file,
        audio_duration_ms=audio_duration_ms,
        clips=clips,
        aligner_engine=aligner.engine,
        aligner_model=aligner.model_name,
        aligner_error=aligner_error,
        counts=counts,
    )
