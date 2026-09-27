"""Validate a Task 3 DAISY package against its Task 1 and Task 2 inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterable, List

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import TASK1_OUTPUT_DIR, TASK2_OUTPUT_DIR, TASK3_OUTPUT_DIR, TOTAL_CHAPTERS
from src.daisy.align import probe_duration_ms, sec_to_ms
from src.daisy.clips import chapter_folder_name, norm_text


REQUIRED_FILES = (
    "dtbook.xml",
    "mo0.smil",
    "book.opf",
    "navigation.ncx",
    "resources.res",
    "alignment.json",
)
DTBOOK_NS = {"dt": "http://www.daisy.org/z3986/2005/dtbook/"}


def resolve_targets(args: argparse.Namespace) -> List[int]:
    if args.pilot:
        return [0, 1]
    if args.all:
        return list(range(TOTAL_CHAPTERS))
    if not 0 <= args.chapter < TOTAL_CHAPTERS:
        raise SystemExit(f"--chapter must be between 0 and {TOTAL_CHAPTERS - 1}")
    return [args.chapter]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_npt(value: str) -> int:
    text = value.strip()
    if text.startswith("npt="):
        text = text[4:]
    if text.endswith("s") and ":" not in text:
        return sec_to_ms(float(text[:-1]))
    raise ValueError(f"unsupported clock value {value!r}")


def _load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _meta_content(root: ET.Element, name: str) -> str:
    for element in root.iter():
        if _local(element.tag) == "meta" and element.get("name") == name:
            return element.get("content", "")
    return ""


def validate_chapter(chapter_idx: int, task1_dir: Path, task2_dir: Path, task3_dir: Path) -> Dict[str, Any]:
    folder = chapter_folder_name(chapter_idx)
    package = task3_dir / folder
    errors: List[str] = []
    if not package.exists():
        return {"chapter_idx": chapter_idx, "valid": False, "errors": [f"missing {package}"]}

    for name in REQUIRED_FILES:
        if not (package / name).exists():
            errors.append(f"missing {name}")
    if errors:
        return {"chapter_idx": chapter_idx, "valid": False, "errors": errors, "clips": 0}

    source_dtbook = task1_dir / folder / "dtbook.xml"
    source_timestamps = task2_dir / folder / "timestamps.json"
    if _sha256(package / "dtbook.xml") != _sha256(source_dtbook):
        errors.append("packaged dtbook.xml differs from Task 1")

    timestamps = _load_json(source_timestamps)
    audio_name = str(timestamps["audio_file"])
    packaged_audio = package / audio_name
    source_audio = task2_dir / folder / audio_name
    if not packaged_audio.exists():
        errors.append(f"missing packaged audio {audio_name}")
    elif _sha256(packaged_audio) != _sha256(source_audio):
        errors.append("packaged audio differs from Task 2")

    dtbook = ET.parse(package / "dtbook.xml").getroot()
    smil = ET.parse(package / "mo0.smil").getroot()
    opf = ET.parse(package / "book.opf").getroot()
    ncx = ET.parse(package / "navigation.ncx").getroot()
    ET.parse(package / "resources.res")
    alignment = _load_json(package / "alignment.json")

    smil_ids: Dict[str, ET.Element] = {}
    for element in smil.iter():
        element_id = element.get("id")
        if not element_id:
            continue
        if element_id in smil_ids:
            errors.append(f"duplicate SMIL id {element_id}")
        smil_ids[element_id] = element

    dtbook_refs = []
    for element in dtbook.iter():
        smilref = element.get("smilref")
        if not smilref:
            continue
        fragment = smilref.split("#", 1)[-1]
        dtbook_refs.append((fragment, element))
        if fragment not in smil_ids:
            errors.append(f"dtbook smilref {smilref} has no SMIL element")

    sent_pars: Dict[str, ET.Element] = {}
    audio_clips: List[tuple[str, int, int]] = []
    for element in smil.iter():
        if _local(element.tag) != "par":
            continue
        par_id = element.get("id", "")
        text = next((child for child in element if _local(child.tag) == "text"), None)
        audio = next((child for child in element if _local(child.tag) == "audio"), None)
        if text is None or audio is None:
            errors.append(f"{par_id} is missing text or audio")
            continue
        src = text.get("src", "")
        if not src.startswith("dtbook.xml#"):
            errors.append(f"{par_id} text src {src!r} is not a dtbook fragment")
            continue
        sent_id = src.split("#", 1)[1]
        sent_pars[sent_id] = element
        if audio.get("src") != audio_name:
            errors.append(f"{par_id} audio src is {audio.get('src')!r}")
        try:
            begin = _parse_npt(audio.get("clipBegin", ""))
            end = _parse_npt(audio.get("clipEnd", ""))
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if end <= begin:
            errors.append(f"{par_id} clipBegin is not before clipEnd")
        audio_clips.append((sent_id, begin, end))

    dtbook_sent_ids = [
        element.get("id", "")
        for element in dtbook.iter()
        if _local(element.tag) == "sent"
    ]
    if [sent_id for sent_id, _, _ in audio_clips] != dtbook_sent_ids:
        errors.append("SMIL sentence order differs from DTBook")
    for sent_id in dtbook_sent_ids:
        if sent_id not in sent_pars:
            errors.append(f"{sent_id} has no SMIL par")

    for index in range(len(audio_clips) - 1):
        if audio_clips[index][2] != audio_clips[index + 1][1]:
            errors.append(
                f"SMIL gap between {audio_clips[index][0]} and {audio_clips[index + 1][0]}"
            )
    if audio_clips and audio_clips[0][1] != 0:
        errors.append("first SMIL clip does not start at 0")

    try:
        probed_ms = probe_duration_ms(packaged_audio) if packaged_audio.exists() else -1
    except Exception as exc:
        probed_ms = -1
        errors.append(f"ffprobe failed: {exc}")
    if audio_clips and probed_ms >= 0 and abs(audio_clips[-1][2] - probed_ms) > 20:
        errors.append(
            f"last clipEnd {audio_clips[-1][2]} ms differs from audio {probed_ms} ms"
        )

    alignment_clips = alignment.get("clips")
    if not isinstance(alignment_clips, list) or len(alignment_clips) != len(audio_clips):
        errors.append("alignment.json clip count differs from SMIL")
        alignment_clips = []
    for smil_clip, saved in zip(audio_clips, alignment_clips):
        saved_begin = sec_to_ms(float(saved["clip_begin"]))
        saved_end = sec_to_ms(float(saved["clip_end"]))
        if (saved["sent_id"], saved_begin, saved_end) != smil_clip:
            errors.append(f"{saved.get('sent_id')} alignment.json does not match SMIL")

    errors.extend(_check_timing(timestamps, alignment_clips, probed_ms))
    errors.extend(_check_opf_ncx(opf, ncx, dtbook, smil_ids, audio_name, package))

    return {
        "chapter_idx": chapter_idx,
        "valid": not errors,
        "errors": errors,
        "clips": len(audio_clips),
        "counts": alignment.get("counts", {}),
    }


def _check_timing(
    timestamps: Dict[str, Any],
    alignment_clips: List[Dict[str, Any]],
    probed_ms: int,
) -> List[str]:
    errors: List[str] = []
    by_id = {str(clip.get("sent_id")): clip for clip in alignment_clips}
    units: List[Dict[str, Any]] = []
    for heading in timestamps.get("headings", []):
        units.append({"kind": "heading", "sentences": [heading], **heading})
    for chunk in timestamps.get("chunks", []):
        units.append(chunk)

    flat_ids = [
        str(sentence["sent_id"])
        for unit in units
        for sentence in unit["sentences"]
    ]
    if flat_ids != [str(clip.get("sent_id")) for clip in alignment_clips]:
        errors.append("alignment sentence order differs from timestamps")
        return errors

    for unit_index, unit in enumerate(units):
        sentences = unit["sentences"]
        clips = [by_id[str(sentence["sent_id"])] for sentence in sentences]
        begin = sec_to_ms(float(unit["start"]))
        end = sec_to_ms(float(unit["end"]))
        speech_end = sec_to_ms(float(unit["speech_end"]))
        is_last = unit_index == len(units) - 1
        if sec_to_ms(float(clips[0]["clip_begin"])) != begin:
            errors.append(f"{clips[0]['sent_id']} does not start on its Task 2 boundary")
        actual_end = sec_to_ms(float(clips[-1]["clip_end"]))
        if is_last:
            if probed_ms >= 0 and abs(actual_end - probed_ms) > 20:
                errors.append("last sentence does not end at the audio duration")
            if abs(actual_end - end) > 250:
                errors.append("last sentence drifted from the Task 2 timeline")
        elif actual_end != end:
            errors.append(f"{clips[-1]['sent_id']} does not end on its Task 2 boundary")
        methods = {clip.get("method") for clip in clips}
        kind = unit.get("kind")
        if kind == "heading" and methods != {"exact"}:
            errors.append(f"{clips[0]['sent_id']} heading was re-aligned")
        elif kind == "section_break" and methods != {"silence"}:
            errors.append(f"{clips[0]['sent_id']} section break method is {methods}")
        elif kind == "speech" and len(sentences) == 1 and methods != {"exact"}:
            errors.append(f"{clips[0]['sent_id']} single-sentence chunk was re-aligned")
        elif kind == "speech" and len(sentences) > 1 and methods - {"aligned", "proportional"}:
            errors.append(f"{unit.get('chunk_id')} has an unknown alignment method")
        for clip in clips:
            clip_begin = sec_to_ms(float(clip["clip_begin"]))
            if kind == "speech" and clip_begin > speech_end:
                errors.append(f"{clip['sent_id']} starts after spoken audio")
            if norm_text(str(clip.get("source_text", ""))) != norm_text(
                str(next(sentence["source_text"] for sentence in sentences if sentence["sent_id"] == clip["sent_id"]))
            ):
                errors.append(f"{clip['sent_id']} source text changed")
    return errors


def _check_opf_ncx(
    opf: ET.Element,
    ncx: ET.Element,
    dtbook: ET.Element,
    smil_ids: Dict[str, ET.Element],
    audio_name: str,
    package: Path,
) -> List[str]:
    errors: List[str] = []
    uid = _meta_content(dtbook, "dtb:uid")
    texts = {_local(element.tag): (element.text or "").strip() for element in opf.iter()}
    if texts.get("Identifier") != uid or _meta_content(opf, "dtb:uid") != uid:
        errors.append("OPF uid does not match DTBook dtb:uid")
    if texts.get("Source") != uid:
        errors.append("OPF dc:Source is not the ISBN uid")
    for name in ("Title", "Creator", "Subject", "Description", "Publisher", "Date", "Language"):
        if not texts.get(name):
            errors.append(f"OPF is missing dc:{name}")

    manifest = {}
    spine_ids = []
    for element in opf.iter():
        if _local(element.tag) == "item" and element.get("id"):
            manifest[element.get("id")] = element.get("href", "")
        if _local(element.tag) == "itemref":
            spine_ids.append(element.get("idref", ""))
    if spine_ids != ["smil"]:
        errors.append(f"spine is {spine_ids}, expected ['smil']")
    for href in manifest.values():
        if href and not (package / href).exists():
            errors.append(f"manifest item missing on disk: {href}")
    if manifest.get("audio") != audio_name:
        errors.append("manifest audio href differs from timestamps")

    ncx_uid = _meta_content(ncx, "dtb:uid")
    if ncx_uid != uid:
        errors.append("NCX uid does not match DTBook")
    points = [element for element in ncx.iter() if _local(element.tag) == "navPoint"]
    if len(points) < 2:
        errors.append("NCX needs the book title and the chapter heading")
    for point in points:
        content = next((child for child in point if _local(child.tag) == "content"), None)
        src = content.get("src", "") if content is not None else ""
        fragment = src.split("#", 1)[-1]
        if not src.startswith("mo0.smil#") or fragment not in smil_ids:
            errors.append(f"NCX content {src!r} does not resolve")
    return errors


def run_validation(targets: Iterable[int]) -> bool:
    task1_dir = Path(TASK1_OUTPUT_DIR)
    task2_dir = Path(TASK2_OUTPUT_DIR)
    task3_dir = Path(TASK3_OUTPUT_DIR)
    print("=" * 78)
    print("  TASK 3 VALIDATION - 'TRONG GIA ĐÌNH'")
    print("=" * 78)
    results = []
    for chapter_idx in targets:
        result = validate_chapter(chapter_idx, task1_dir, task2_dir, task3_dir)
        results.append(result)
        status = "PASSED" if result["valid"] else "FAILED"
        print(f"[{status}] Ch {chapter_idx:02d} | {result.get('clips', 0)} clips | {result.get('counts', {})}")
        if not result["valid"]:
            for error in result["errors"][:10]:
                print(f"    - {error}")
            if len(result["errors"]) > 10:
                print(f"    - ... {len(result['errors']) - 10} more errors")
    passed = sum(1 for result in results if result["valid"])
    print("-" * 78)
    print(f"TOTAL: {passed}/{len(results)} PASSED")
    print("=" * 78)
    return passed == len(results) and bool(results)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Task 3 DAISY packages")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pilot", action="store_true", help="Introduction and Chapter 1")
    group.add_argument("--all", action="store_true", help="All 23 chapters")
    group.add_argument("--chapter", type=int, help="One chapter index (0-22)")
    args = parser.parse_args()
    ok = run_validation(resolve_targets(args))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
