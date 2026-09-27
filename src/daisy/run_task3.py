"""Task 3 runner: DTBook + Task 2 audio -> DAISY 3 package."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, List

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import TASK1_OUTPUT_DIR, TASK2_OUTPUT_DIR, TASK3_OUTPUT_DIR, TOTAL_CHAPTERS
from src.daisy.align import SentenceAligner
from src.daisy.build import write_package
from src.daisy.clips import build_sync


def resolve_targets(args: argparse.Namespace) -> List[int]:
    if args.pilot:
        return [0, 1]
    if args.all:
        return list(range(TOTAL_CHAPTERS))
    if not 0 <= args.chapter < TOTAL_CHAPTERS:
        raise SystemExit(f"--chapter must be between 0 and {TOTAL_CHAPTERS - 1}")
    return [args.chapter]


def run_pipeline(targets: Iterable[int]) -> bool:
    task1_dir = Path(TASK1_OUTPUT_DIR)
    task2_dir = Path(TASK2_OUTPUT_DIR)
    output_dir = Path(TASK3_OUTPUT_DIR)
    aligner = SentenceAligner()
    if aligner.ensure():
        print(f"[ALIGN] CTC {aligner.model_name}")
    else:
        print(f"[ALIGN] proportional ({aligner.error})")

    failed = 0
    for chapter_idx in targets:
        try:
            sync = build_sync(chapter_idx, task1_dir, task2_dir, aligner)
            write_package(sync, task1_dir, task2_dir, output_dir)
        except Exception as exc:
            failed += 1
            print(f"[FAILED] Ch {chapter_idx:02d} | {exc}")
            continue
        counts = sync.counts
        print(
            f"[OK] Ch {chapter_idx:02d} | {len(sync.clips)} clips | "
            f"exact {counts.get('exact', 0)} | aligned {counts.get('aligned', 0)} | "
            f"proportional {counts.get('proportional', 0)} | silence {counts.get('silence', 0)} | "
            f"{sync.audio_duration_ms / 1000:.3f}s"
        )
    print(f"TOTAL: {failed} failed chapter(s)")
    return failed == 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Build DAISY 3 packages from Task 1 and Task 2")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pilot", action="store_true", help="Introduction and Chapter 1")
    group.add_argument("--all", action="store_true", help="All 23 chapters")
    group.add_argument("--chapter", type=int, help="One chapter index (0-22)")
    args = parser.parse_args()
    ok = run_pipeline(resolve_targets(args))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
