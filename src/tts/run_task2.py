"""Task 2 runner: Task-1 segments.json -> VieNeu -> MP3 + timestamps.json."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import (
    TASK1_OUTPUT_DIR,
    TASK2_OUTPUT_DIR,
    TOTAL_CHAPTERS,
    TTS_AUDIO_BITRATE,
    TTS_BACKEND,
    TTS_CONTEXT_CHUNK_JOIN_PAUSE_MS,
    TTS_MAX_CHARS_PER_CONTEXT_CHUNK,
    TTS_MAX_SENTENCES_PER_CONTEXT_CHUNK,
    TTS_PARAGRAPH_PAUSE_MS,
    TTS_RETRIES,
    TTS_SECTION_PAUSE_MS,
    TTS_VOICE,
)
from src.tts.synthesize import TTSSettings, VieNeuSynthesizer
from src.tts.validate_task2 import chapter_folder_name, validate_task1_handoff, validate_chapter


def load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json_atomic(data: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_targets(args: argparse.Namespace) -> List[int]:
    if args.pilot:
        return [0, 1]
    if args.all:
        return list(range(TOTAL_CHAPTERS))
    if not 0 <= args.chapter < TOTAL_CHAPTERS:
        raise SystemExit(f"--chapter must be between 0 and {TOTAL_CHAPTERS - 1}")
    return [args.chapter]


def build_settings() -> TTSSettings:
    return TTSSettings(
        voice=TTS_VOICE,
        backend=TTS_BACKEND,
        max_sentences_per_chunk=TTS_MAX_SENTENCES_PER_CONTEXT_CHUNK,
        max_chars_per_chunk=TTS_MAX_CHARS_PER_CONTEXT_CHUNK,
        context_chunk_join_pause_ms=TTS_CONTEXT_CHUNK_JOIN_PAUSE_MS,
        paragraph_pause_ms=TTS_PARAGRAPH_PAUSE_MS,
        section_pause_ms=TTS_SECTION_PAUSE_MS,
        bitrate=TTS_AUDIO_BITRATE,
        retries=TTS_RETRIES,
    )


def process_chapter(
    chapter_idx: int,
    synthesizer: VieNeuSynthesizer,
) -> Dict[str, Any]:
    folder = chapter_folder_name(chapter_idx)
    source_path = Path(TASK1_OUTPUT_DIR) / folder / "segments.json"
    output_dir = Path(TASK2_OUTPUT_DIR) / folder
    timestamp_path = output_dir / "timestamps.json"

    if not source_path.exists():
        raise FileNotFoundError(f"Task-1 input not found: {source_path}")

    before_hash = sha256_file(source_path)
    handoff = load_json(source_path)
    errors = validate_task1_handoff(handoff)
    if errors:
        joined = "\n  - ".join(errors)
        raise ValueError(f"Invalid Task-1 handoff {source_path}:\n  - {joined}")

    generated = synthesizer.synthesize_chapter(handoff, output_dir)
    save_json_atomic(generated, timestamp_path)

    after_hash = sha256_file(source_path)
    if before_hash != after_hash:
        raise RuntimeError(
            f"TASK 1 SAFETY FAILURE: {source_path} changed while Task 2 was running"
        )

    validation = validate_chapter(
        chapter_idx,
        Path(TASK1_OUTPUT_DIR),
        Path(TASK2_OUTPUT_DIR),
    )
    if not validation["valid"]:
        joined = "\n  - ".join(validation["errors"])
        raise RuntimeError(f"Post-generation validation failed:\n  - {joined}")

    audio_path = output_dir / generated["audio_file"]
    return {
        "chapter_idx": chapter_idx,
        "chapter_title": handoff["chapter_title"],
        "paragraphs": handoff["total_paragraphs"],
        "sentences": handoff["total_sentences"],
        "audio_path": str(audio_path),
        "size_mb": audio_path.stat().st_size / (1024 * 1024),
        "duration": generated["audio_duration"],
        "valid": True,
    }


def run_pipeline(targets: Iterable[int], settings: TTSSettings) -> bool:
    targets = list(targets)
    print("=" * 78)
    print("  TASK 2: VIENEU TTS & AUDIO PIPELINE - 'TRONG GIA ĐÌNH'")
    print(
        f"  Voice: {settings.voice} | Backend: {settings.backend} | "
        f"Context: <= {settings.max_sentences_per_chunk} sents / "
        f"{settings.max_chars_per_chunk} chars"
    )
    print("  Task 1: READ ONLY")
    print("=" * 78)

    synthesizer = VieNeuSynthesizer(settings)
    results: List[Dict[str, Any]] = []

    for idx in targets:
        try:
            print(f"[*] Chapter {idx:02d}: synthesizing...", flush=True)
            result = process_chapter(idx, synthesizer)
            results.append(result)
            print(
                f"[OK] Chapter {idx:02d} ({result['sentences']} sents, "
                f"{result['duration'] / 60:.1f} min, {result['size_mb']:.1f} MB)"
            )
        except Exception as exc:
            print(f"[FAILED] Chapter {idx:02d}: {exc}")
            results.append({"chapter_idx": idx, "valid": False, "error": str(exc)})

    passed = sum(1 for r in results if r.get("valid"))
    total_sents = sum(int(r.get("sentences", 0)) for r in results)
    print("-" * 78)
    print(f"SUMMARY: {passed}/{len(results)} chapters PASSED | {total_sents} sentences")
    print(f"Output: {TASK2_OUTPUT_DIR}")
    print("=" * 78)
    return passed == len(results)


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Task 2: Task-1 segments.json -> VieNeu chapter MP3 + context timestamps"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pilot", action="store_true", help="Run Introduction + Chapter 1")
    group.add_argument("--all", action="store_true", help="Run all 23 chapters")
    group.add_argument("--chapter", type=int, help="Run one chapter index (0-22)")
    return parser


def main() -> None:
    args = make_parser().parse_args()
    targets = resolve_targets(args)
    settings = build_settings()
    ok = run_pipeline(targets, settings)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
