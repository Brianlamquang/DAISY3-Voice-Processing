"""Automated integrity validation for VieNeu Task 2 outputs."""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import (
    TASK1_OUTPUT_DIR,
    TASK2_OUTPUT_DIR,
    TOTAL_CHAPTERS,
    TTS_MAX_CHARS_PER_CONTEXT_CHUNK,
    TTS_MAX_SENTENCES_PER_CONTEXT_CHUNK,
    TTS_PARAGRAPH_PAUSE_MS,
    TTS_SECTION_PAUSE_MS,
)
from src.tts.normalize import is_section_break, normalize_for_tts

try:
    from pydub import AudioSegment
except ImportError:
    AudioSegment = None


REQUIRED_TOP_LEVEL = {
    "metadata",
    "chapter_idx",
    "chapter_title",
    "total_paragraphs",
    "total_sentences",
    "segments",
}
REQUIRED_SEGMENT_FIELDS = {"sent_id", "smil_sid", "p_id", "seq_id", "text"}


DTBOOK_NAMESPACE = "http://www.daisy.org/z3986/2005/dtbook/"
DTBOOK_NS = {"dt": DTBOOK_NAMESPACE}


def load_dtbook_headings(dtbook_path: Path) -> List[Dict[str, Any]]:
    """Read Task-1 id_1..id_3 heading metadata from DTBook in read-only mode."""
    root = ET.parse(dtbook_path).getroot()
    specs = (
        ("book_title", "id_1", ".//dt:doctitle"),
        ("author", "id_2", ".//dt:docauthor"),
        ("chapter_title", "id_3", ".//dt:h1"),
    )
    headings: List[Dict[str, Any]] = []

    for role, sent_id, container_xpath in specs:
        container = root.find(container_xpath, DTBOOK_NS)
        if container is None:
            raise ValueError(f"DTBook missing container for {sent_id}: {container_xpath}")

        sent = container.find(f"./dt:sent[@id='{sent_id}']", DTBOOK_NS)
        if sent is None:
            raise ValueError(f"DTBook missing required heading sentence {sent_id}")

        source_text = " ".join("".join(sent.itertext()).split())
        smilref = str(sent.get("smilref", ""))
        smil_sid = smilref.rsplit("#", 1)[-1] if "#" in smilref else ""
        if not source_text or not smil_sid:
            raise ValueError(f"DTBook heading {sent_id} has invalid text/smilref")

        headings.append(
            {
                "kind": "heading",
                "role": role,
                "sent_id": sent_id,
                "smil_sid": smil_sid,
                "container_id": str(container.get("id", "")),
                "source_text": source_text,
                "tts_text": normalize_for_tts(source_text).tts_text,
            }
        )

    return headings


def validate_task1_heading_consistency(
    source: Dict[str, Any], expected_headings: List[Dict[str, Any]]
) -> List[str]:
    errors: List[str] = []
    expected_text = (
        " ".join(str(source.get("metadata", {}).get("dc:Title", "")).split()),
        " ".join(str(source.get("metadata", {}).get("dc:Creator", "")).split()),
        " ".join(str(source.get("chapter_title", "")).split()),
    )
    actual_text = tuple(str(item.get("source_text", "")) for item in expected_headings)
    if actual_text != expected_text:
        errors.append(
            "Task-1 DTBook id_1..id_3 text differs from segments.json metadata/chapter_title"
        )
    return errors


def chapter_folder_name(chapter_idx: int) -> str:
    return (
        "Trong_Gia_Dinh-Gioi_Thieu"
        if chapter_idx == 0
        else f"Trong_Gia_Dinh-Chuong_{chapter_idx:02d}"
    )


def load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_task1_handoff(source: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    missing = REQUIRED_TOP_LEVEL - set(source)
    if missing:
        errors.append(f"Task-1 JSON missing keys: {sorted(missing)}")
        return errors

    segments = source.get("segments", [])
    if len(segments) != source.get("total_sentences"):
        errors.append(
            f"total_sentences={source.get('total_sentences')} but len(segments)={len(segments)}"
        )

    unique_paragraphs = {s.get("p_id") for s in segments if s.get("p_id") is not None}
    if len(unique_paragraphs) != source.get("total_paragraphs"):
        errors.append(
            f"total_paragraphs={source.get('total_paragraphs')} but unique p_id={len(unique_paragraphs)}"
        )

    for i, segment in enumerate(segments):
        missing_segment = REQUIRED_SEGMENT_FIELDS - set(segment)
        if missing_segment:
            errors.append(f"segment[{i}] missing fields: {sorted(missing_segment)}")
        if not str(segment.get("text", "")).strip():
            errors.append(f"segment[{i}] {segment.get('sent_id')} has empty text")

    for key in ("sent_id", "smil_sid"):
        values = [s.get(key) for s in segments]
        if len(values) != len(set(values)):
            errors.append(f"Duplicate {key} detected within chapter")

    return errors


def _decode_audio_duration(path: Path) -> Tuple[float | None, str | None]:
    if AudioSegment is None:
        return None, "Missing pydub; install src/tts/requirements.txt"
    try:
        audio = AudioSegment.from_file(path, format="mp3")
        return len(audio) / 1000.0, None
    except Exception as exc:
        return None, f"Cannot decode MP3: {exc}"


def _flatten_output_sentences(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    flattened: List[Dict[str, Any]] = []
    for chunk in chunks:
        sentences = chunk.get("sentences", [])
        if isinstance(sentences, list):
            flattened.extend(sentences)
    return flattened


def validate_chapter(chapter_idx: int, task1_dir: Path, task2_dir: Path) -> Dict[str, Any]:
    folder = chapter_folder_name(chapter_idx)
    source_path = task1_dir / folder / "segments.json"
    dtbook_path = task1_dir / folder / "dtbook.xml"
    timestamp_path = task2_dir / folder / "timestamps.json"
    errors: List[str] = []

    if not source_path.exists():
        return {"chapter_idx": chapter_idx, "valid": False, "errors": [f"Missing {source_path}"]}
    if not dtbook_path.exists():
        return {"chapter_idx": chapter_idx, "valid": False, "errors": [f"Missing {dtbook_path}"]}

    source = load_json(source_path)
    errors.extend(validate_task1_handoff(source))
    try:
        expected_headings = load_dtbook_headings(dtbook_path)
    except Exception as exc:
        expected_headings = []
        errors.append(f"Invalid Task-1 DTBook headings: {exc}")
    if expected_headings:
        errors.extend(validate_task1_heading_consistency(source, expected_headings))

    if not timestamp_path.exists():
        errors.append(f"Missing {timestamp_path}")
        return {
            "chapter_idx": chapter_idx,
            "title": source.get("chapter_title", ""),
            "sentences": source.get("total_sentences", 0),
            "valid": False,
            "errors": errors,
        }

    output = load_json(timestamp_path)
    for key in ("chapter_idx", "chapter_title", "total_paragraphs", "total_sentences"):
        if output.get(key) != source.get(key):
            errors.append(f"{key} mismatch: task1={source.get(key)!r}, task2={output.get(key)!r}")

    if output.get("metadata") != source.get("metadata"):
        errors.append("metadata changed between Task 1 and Task 2")

    headings = output.get("headings")
    if not isinstance(headings, list) or len(headings) != 3:
        errors.append("timestamps.json must contain exactly three headings for id_1, id_2, id_3")
        headings = []

    previous_end = 0.0
    if headings and expected_headings:
        heading_fields = ("kind", "role", "sent_id", "smil_sid", "container_id", "source_text")
        for i, (expected_heading, output_heading) in enumerate(zip(expected_headings, headings)):
            for field in heading_fields:
                if output_heading.get(field) != expected_heading.get(field):
                    errors.append(f"heading[{i}] {field} differs from Task-1 DTBook")

            expected_tts = normalize_for_tts(expected_heading["source_text"]).tts_text
            if str(output_heading.get("tts_text", "")) != expected_tts:
                errors.append(f"heading[{i}] tts_text does not match normalization rules")

            try:
                start = float(output_heading["start"])
                speech_end = float(output_heading["speech_end"])
                end = float(output_heading["end"])
                pause_after_ms = int(output_heading["pause_after_ms"])
            except (KeyError, TypeError, ValueError) as exc:
                errors.append(f"heading[{i}] invalid timestamp fields: {exc}")
                continue

            if start < -0.001:
                errors.append(f"heading[{i}] start < 0")
            if speech_end <= start:
                errors.append(f"heading[{i}] speech_end <= start")
            if end < speech_end:
                errors.append(f"heading[{i}] end < speech_end")
            if abs(start - previous_end) > 0.025:
                errors.append(
                    f"heading[{i}] timeline gap/overlap: start={start:.3f}, previous_end={previous_end:.3f}"
                )
            if pause_after_ms != TTS_PARAGRAPH_PAUSE_MS:
                errors.append(
                    f"heading[{i}] pause_after_ms must be {TTS_PARAGRAPH_PAUSE_MS} ms"
                )
            if abs((end - speech_end) - (pause_after_ms / 1000.0)) > 0.025:
                errors.append(f"heading[{i}] end-speech_end does not match pause_after_ms")

            previous_end = end

    chunks = output.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        errors.append("timestamps.json missing non-empty chunks[]")
        chunks = []

    source_segments = source.get("segments", [])
    output_sentences = _flatten_output_sentences(chunks)
    if len(output_sentences) != len(source_segments):
        errors.append(
            f"Sentence coverage mismatch: task1={len(source_segments)}, task2={len(output_sentences)}"
        )

    identity_fields = ("sent_id", "smil_sid", "p_id", "seq_id")
    for i, (src, out) in enumerate(zip(source_segments, output_sentences)):
        for field in identity_fields:
            if out.get(field) != src.get(field):
                errors.append(f"sentence[{i}] {field} changed from Task 1")
        if out.get("source_text") != src.get("text"):
            errors.append(f"sentence[{i}] source_text changed from Task 1")

        expected = normalize_for_tts(src.get("text", ""))
        if str(out.get("tts_text", "")) != expected.tts_text:
            errors.append(f"sentence[{i}] tts_text does not match normalization rules")

    seen_ids: List[str] = []
    for i, chunk in enumerate(chunks):
        kind = chunk.get("kind")
        sentences = chunk.get("sentences", [])
        if not sentences:
            errors.append(f"chunk[{i}] has no sentence mapping")
            continue

        p_ids = {str(s.get("p_id")) for s in sentences}
        if len(p_ids) != 1 or str(chunk.get("p_id")) not in p_ids:
            errors.append(f"chunk[{i}] crosses/does not match paragraph p_id")

        seen_ids.extend(str(s.get("sent_id")) for s in sentences)

        try:
            start = float(chunk["start"])
            speech_end = float(chunk["speech_end"])
            end = float(chunk["end"])
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"chunk[{i}] invalid timestamp fields: {exc}")
            continue

        if start < -0.001:
            errors.append(f"chunk[{i}] start < 0")
        if speech_end < start:
            errors.append(f"chunk[{i}] speech_end < start")
        if end < speech_end:
            errors.append(f"chunk[{i}] end < speech_end")
        if end <= start:
            errors.append(f"chunk[{i}] end <= start")
        if abs(start - previous_end) > 0.025:
            errors.append(
                f"chunk[{i}] timeline gap/overlap: start={start:.3f}, previous_end={previous_end:.3f}"
            )

        if kind == "speech":
            if len(sentences) > TTS_MAX_SENTENCES_PER_CONTEXT_CHUNK:
                errors.append(f"chunk[{i}] exceeds max sentence count")
            tts_text = str(chunk.get("tts_text", "")).strip()
            if not tts_text:
                errors.append(f"chunk[{i}] speech has empty tts_text")
            source_text = str(chunk.get("source_text", "")).strip()
            if len(source_text) > TTS_MAX_CHARS_PER_CONTEXT_CHUNK and len(sentences) > 1:
                errors.append(f"chunk[{i}] exceeds max source char count")
            if any(is_section_break(str(s.get("source_text", ""))) for s in sentences):
                errors.append(f"chunk[{i}] speech contains section-break marker")

        elif kind == "section_break":
            if len(sentences) != 1:
                errors.append(f"chunk[{i}] section_break must map exactly one Task-1 segment")
            marker = str(sentences[0].get("source_text", ""))
            if not is_section_break(marker):
                errors.append(f"chunk[{i}] section_break marker is not approved")
            expected_duration = TTS_SECTION_PAUSE_MS / 1000.0
            if abs((end - start) - expected_duration) > 0.025:
                errors.append(f"chunk[{i}] section_break duration is not {TTS_SECTION_PAUSE_MS} ms")
            if abs(speech_end - start) > 0.025:
                errors.append(f"chunk[{i}] section_break must not contain speech")
        else:
            errors.append(f"chunk[{i}] invalid kind={kind!r}")

        previous_end = end

    source_ids = [str(s.get("sent_id")) for s in source_segments]
    if seen_ids != source_ids:
        errors.append("Task-2 sentence ID order/coverage differs from Task 1")

    audio_file = output.get("audio_file")
    audio_path = task2_dir / folder / str(audio_file) if audio_file else None
    decoded_duration = None
    if not audio_file:
        errors.append("audio_file is missing in timestamps.json")
    elif not audio_path.exists() or audio_path.stat().st_size <= 0:
        errors.append(f"Missing or empty MP3: {audio_path}")
    else:
        decoded_duration, decode_error = _decode_audio_duration(audio_path)
        if decode_error:
            errors.append(decode_error)
        elif decoded_duration is not None:
            try:
                declared_duration = float(output.get("audio_duration", -1))
            except (TypeError, ValueError):
                declared_duration = -1
            if abs(decoded_duration - declared_duration) > 0.25:
                errors.append(
                    f"audio_duration mismatch: JSON={declared_duration:.3f}s decoded={decoded_duration:.3f}s"
                )
            if (chunks or headings) and abs(decoded_duration - previous_end) > 0.25:
                errors.append(
                    f"final timestamp mismatch: end={previous_end:.3f}s decoded={decoded_duration:.3f}s"
                )

    return {
        "chapter_idx": chapter_idx,
        "title": source.get("chapter_title", ""),
        "paragraphs": source.get("total_paragraphs", 0),
        "sentences": source.get("total_sentences", 0),
        "audio_duration": decoded_duration,
        "valid": not errors,
        "errors": errors,
    }


def resolve_targets(args: argparse.Namespace) -> List[int]:
    if args.pilot:
        return [0, 1]
    if args.all:
        return list(range(TOTAL_CHAPTERS))
    if not 0 <= args.chapter < TOTAL_CHAPTERS:
        raise SystemExit(f"--chapter must be between 0 and {TOTAL_CHAPTERS - 1}")
    return [args.chapter]


def run_validation(targets: Iterable[int], task1_dir: Path, task2_dir: Path) -> bool:
    results = []
    print("=" * 78)
    print("  TASK 2 VALIDATION - 'TRONG GIA ĐÌNH'")
    print("=" * 78)

    for idx in targets:
        result = validate_chapter(idx, task1_dir, task2_dir)
        results.append(result)
        status = "PASSED" if result["valid"] else "FAILED"
        print(
            f"[{status}] Ch {idx:02d} | {result.get('paragraphs', 0)} paras | "
            f"{result.get('sentences', 0)} sents"
        )
        if not result["valid"]:
            for error in result["errors"][:10]:
                print(f"    - {error}")
            if len(result["errors"]) > 10:
                print(f"    - ... {len(result['errors']) - 10} more errors")

    passed = sum(1 for r in results if r["valid"])
    total_sents = sum(int(r.get("sentences", 0)) for r in results)
    total_paras = sum(int(r.get("paragraphs", 0)) for r in results)
    all_valid = passed == len(results)

    print("-" * 78)
    print(
        f"TOTAL: {len(results)} chapters | {total_paras} paragraphs | "
        f"{total_sents} sentences | {passed}/{len(results)} PASSED"
    )
    print(f"ALL FILES VALID: {'YES' if all_valid else 'NO'}")
    print("=" * 78)
    return all_valid


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Task 2 MP3 + context timestamp handoff")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pilot", action="store_true", help="Validate Introduction + Chapter 1")
    group.add_argument("--all", action="store_true", help="Validate all 23 chapters")
    group.add_argument("--chapter", type=int, help="Validate one chapter index (0-22)")
    args = parser.parse_args()

    targets = resolve_targets(args)
    ok = run_validation(targets, Path(TASK1_OUTPUT_DIR), Path(TASK2_OUTPUT_DIR))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
