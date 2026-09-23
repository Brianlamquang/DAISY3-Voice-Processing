"""
Central configuration for Task 1: Text & XML Lead
Book: Trong Gia Đình (Hector Malot)
Standard: DAISY 3 (DTBook 2005-3 / NISO Z39.86-2005)
"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
EPUB_PATH = os.path.join(DATA_DIR, "trong_gia_dinh.epub")
OUTPUT_DIR = os.path.join(BASE_DIR, "results", "task1")
TASK1_OUTPUT_DIR = OUTPUT_DIR
TASK2_OUTPUT_DIR = os.path.join(BASE_DIR, "results", "task2")

# Metadata compliant with DAISY 3 & Course Guidelines
METADATA = {
    "dtb:uid": "978-604-69-8175-6",
    "dtb:generator": "DAISY 3 DTBook Python Pipeline (K35)",
    "dc:Title": "Trong Gia Đình",
    "dc:Creator": "Hector Malot",
    "dc:Translator": "Huỳnh Lý & Mai Hương, Huỳnh Phan Thanh Yên",
    "dc:Publisher": "NXB Văn Học",
    "dc:Date": "2017",
    "dc:Identifier": "978-604-69-8175-6",
    "dc:Language": "vi-VN",
    "dc:Subject": "Văn học & Tiểu thuyết",
    "dc:Format": "ANSI/NISO Z39.86-2005",
    "dc:Description": (
        "Cuốn sách kể về cuộc đời cô bé Perrine (Perin), 12 tuổi, mồ côi cha mẹ "
        "và hành trình đầy khó khăn, thử thách với nghị lực phi thường để vươn lên "
        "và được ông nội đón nhận trở lại trong gia đình."
    ),
    "note": "Bản dịch của GS. Huỳnh Lý & Mai Hương, hiệu đính Huỳnh Phan Thanh Yên",
}

# Total chapters in the epub: C0 (Intro) through C22
TOTAL_CHAPTERS = 23

# Task 2: TTS & Audio
TTS_ENGINE = "vieneu"
TTS_VOICE = "Minh Đức"
TTS_BACKEND = "onnx"

# Context chunking
TTS_MAX_SENTENCES_PER_CONTEXT_CHUNK = 12
TTS_MAX_CHARS_PER_CONTEXT_CHUNK = 900

# Structural pauses
# Punctuation inside a context is handled natively by VieNeu.
TTS_CONTEXT_CHUNK_JOIN_PAUSE_MS = 155
TTS_PARAGRAPH_PAUSE_MS = 170
TTS_SECTION_PAUSE_MS = 250

# Audio
TTS_AUDIO_BITRATE = "128k"
TTS_RETRIES = 4