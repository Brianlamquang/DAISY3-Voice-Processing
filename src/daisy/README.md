# Task 3 — Alignment & DAISY package

`results/task1` and `results/task2` stay read-only. Each chapter with audio becomes one DAISY 3 book under `results/task3/`:

```text
results/task3/Trong_Gia_Dinh-Chuong_XX/
├── dtbook.xml
├── Chuong_XX.mp3
├── mo0.smil
├── book.opf
├── navigation.ncx
├── resources.res
└── alignment.json
```

The Introduction uses `Gioi_Thieu.mp3`.

## Timing

Task 2 already measured the coarse timeline. Task 3 does not align the whole chapter again.

* Headings `id_1`–`id_3` and one-sentence chunks keep the Task 2 edges.
* A scene-break marker keeps its 250 ms silence.
* Sentences inside one chunk are CTC-aligned on `tts_text` between `start` and `speech_end`.
* The structural pause after a chunk stays on the last sentence, so the clips cover the file without skipping silence.
* If CTC cannot place a chunk, that chunk is split by `tts_text` length and `alignment.json` records `proportional`.

SMIL ids follow the DTBook `smilref` fragments (`sforsmil-1`, `sfaux-heading`, `seq_N`, `sid_N`). Those fragments are not always the XML element id.

## Run

ffmpeg must be on `PATH`. Use Python 3.12 for the aligner.

```bash
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python -m pip install -r src/daisy/requirements.txt
.venv\Scripts\python src/daisy/run_task3.py --pilot
.venv\Scripts\python src/daisy/validate_task3.py --pilot
```

`--all` processes every chapter index. A chapter without Task 2 audio fails on its own and does not stop the others; the command exits non-zero until all 23 packages validate.
