"""TTS-only text normalization for Task 2.

Task 1 is the source of truth. This module never edits Task-1 files or IDs; it
only creates a spoken ``tts_text`` representation for VieNeu.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


_DOUBLE_QUOTE_RE = re.compile(r'[“”„‟«»"]')
_INLINE_FOOTNOTE_RE = re.compile(r"(?<=[\wÀ-ỹĐđ])\s*\(\d+\)")
_LEADING_FOOTNOTE_BLOCK_RE = re.compile(
    r"^\s*(?:(?:\(\d+\))\s*[,;:]?\s*)+"
)
_SECTION_BREAK_OOO_RE = re.compile(r"^oOo$", re.IGNORECASE)
_SECTION_BREAK_STARS_RE = re.compile(r"^\*\s*\*\s*\*$")


@dataclass(frozen=True)
class NormalizedText:
    source_text: str
    tts_text: str
    is_section_break: bool = False


def clean_source_text(text: str) -> str:
    """Normalize Unicode/whitespace for processing without mutating Task 1."""
    normalized = unicodedata.normalize("NFC", text or "")
    return re.sub(r"\s+", " ", normalized).strip()


def is_section_break(text: str) -> bool:
    """Return True only for the approved standalone scene-break markers."""
    stripped = clean_source_text(text)
    return bool(
        stripped
        and (
            _SECTION_BREAK_OOO_RE.fullmatch(stripped)
            or _SECTION_BREAK_STARS_RE.fullmatch(stripped)
        )
    )


def normalize_vv_for_tts(text: str) -> str:
    """TTS-only normalization for ``v.v.`` / ``v.v...`` forms."""
    text = re.sub(
        r"(?i)\bv\s*\.\s*v\s*\.(?:\s*\.)+",
        "vân vân…",
        text,
    )
    text = re.sub(
        r"(?i)\bv\s*\.\s*v\s*\.",
        "vân vân.",
        text,
    )
    text = re.sub(
        r"(?i)\bv\s*\.\s*v\b",
        "vân vân",
        text,
    )
    return text


def normalize_all_caps_phrases_for_tts(text: str) -> str:
    """Normalize multi-word ALL-CAPS phrases while preserving single acronyms."""
    upper_word = (
        r"[A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠƯẠ-Ỵ]"
        r"[A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠƯẠ-Ỵ-]*"
    )
    pattern = re.compile(rf"\b({upper_word}(?:\s+{upper_word})+)\b")

    def repl(match: re.Match[str]) -> str:
        phrase = match.group(1).lower()
        return phrase[:1].upper() + phrase[1:] if phrase else phrase

    return pattern.sub(repl, text)


def strip_footnote_markers_for_tts(text: str) -> str:
    """Remove footnote reference labels only from spoken text.

    Handles both inline references such as ``Rôbinxơn(1)`` and leading blocks
    such as ``(1), (2) Rôbinxơn...`` without touching ordinary numbers.
    """
    text = _LEADING_FOOTNOTE_BLOCK_RE.sub("", text)
    text = _INLINE_FOOTNOTE_RE.sub("", text)
    return text


def prepare_tts_text(text: str) -> str:
    """Create the exact text sent to VieNeu while preserving source externally."""
    spoken = clean_source_text(text)
    spoken = strip_footnote_markers_for_tts(spoken)
    spoken = normalize_vv_for_tts(spoken)
    spoken = normalize_all_caps_phrases_for_tts(spoken)
    spoken = _DOUBLE_QUOTE_RE.sub("", spoken)
    spoken = re.sub(r"\s+", " ", spoken).strip()
    spoken = re.sub(r"\s+([,.;:!?…])", r"\1", spoken)
    return spoken


def normalize_for_tts(text: str) -> NormalizedText:
    """Return source + spoken form for one Task-1 segment."""
    source = unicodedata.normalize("NFC", text or "")
    if is_section_break(source):
        return NormalizedText(source_text=source, tts_text="", is_section_break=True)

    return NormalizedText(
        source_text=source,
        tts_text=prepare_tts_text(source),
        is_section_break=False,
    )
