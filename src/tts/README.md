# Task 2 â€” TTS & Audio Lead

Pipeline:

`results/task1/*/segments.json -> TTS-only normalize -> VieNeu context synthesis -> chapter MP3 + timestamps.json -> validate -> Task 3`

## Configuration

Task 2 uses the shared `src/config.py`.

Production defaults:

```text
Engine              : VieNeu
Voice               : Minh Äá»©c
Backend              : ONNX
Max sentences/chunk : 12
Max chars/chunk     : 900
Chunk join pause    : 155 ms
Paragraph pause     : 170 ms
Scene break         : 250 ms
Bitrate             : 128k
```

Punctuation inside a context chunk is handled natively by VieNeu.

## Install

```bash
python -m pip install -r src/tts/requirements.txt
ffmpeg -version
ffprobe -version
```

## Pilot first

```bash
python src/tts/run_task2.py --pilot
python src/tts/validate_task2.py --pilot
```

Listen to the complete Introduction and Chapter 1 before running more chapters.

Single chapter:

```bash
python src/tts/run_task2.py --chapter 5
python src/tts/validate_task2.py --chapter 5
```

Full run is kept for the final production dataset:

```bash
python src/tts/run_task2.py --all
python src/tts/validate_task2.py --all
```

## Output

```text
results/task2/Trong_Gia_Dinh-Chuong_XX/
â”œâ”€â”€ Chuong_XX.mp3
â””â”€â”€ timestamps.json
```

The Introduction uses `Gioi_Thieu.mp3`.

`timestamps.json` stores context-level timing plus ordered Task-1 sentence mapping (`sent_id`, `smil_sid`, `p_id`, `seq_id`, `source_text`, `tts_text`). Task 3 performs sentence-level forced alignment and creates final `clipBegin` / `clipEnd` values for SMIL.

## Task-1 safety

Task 2 reads Task-1 `segments.json` only. It never writes into `results/task1/`. The runner also verifies the SHA-256 of each source `segments.json` before and after synthesis.

