"""Write one self-contained DAISY 3 package for a chapter."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from xml.sax.saxutils import escape

from src.daisy.clips import ChapterSync, Clip


SMIL_DOCTYPE = (
    '<!DOCTYPE smil PUBLIC "-//NISO//DTD dtbsmil 2005-2//EN" '
    '"http://www.daisy.org/z3986/2005/dtbsmil-2005-2.dtd">'
)
OPF_DOCTYPE = (
    '<!DOCTYPE package PUBLIC "-//NISO//DTD dtb 2005-1//EN" '
    '"http://www.daisy.org/z3986/2005/dtb-2005-1.dtd">'
)
NCX_DOCTYPE = (
    '<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" '
    '"http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">'
)
RES_DOCTYPE = (
    '<!DOCTYPE resources PUBLIC "-//NISO//DTD resource 2005-1//EN" '
    '"http://www.daisy.org/z3986/2005/resource-2005-1.dtd">'
)


def format_npt(milliseconds: int) -> str:
    return f"{milliseconds / 1000:.3f}s"


def format_daisy_time(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def _xml(text: str) -> str:
    return escape(text, {'"': "&quot;", "'": "&apos;"})


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    os.replace(temporary, path)


def _link_or_copy(source: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        destination.unlink()
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def _groups(clips: list[Clip]) -> list[tuple[str, list[Clip]]]:
    groups: list[tuple[str, list[Clip]]] = []
    for clip in clips:
        if groups and groups[-1][0] == clip.container_id:
            groups[-1][1].append(clip)
        else:
            groups.append((clip.container_id, [clip]))
    return groups


def render_smil(sync: ChapterSync) -> str:
    language = _xml(str(sync.metadata.get("dc:Language", "vi-VN")))
    uid = _xml(str(sync.metadata["dtb:uid"]))
    generator = _xml(str(sync.metadata.get("dtb:generator", "DAISY 3 Pipeline")))
    total = format_daisy_time(sync.audio_duration_ms)
    duration = format_npt(sync.audio_duration_ms)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        SMIL_DOCTYPE,
        f'<smil xmlns="http://www.w3.org/2001/SMIL20/" xml:lang="{language}">',
        "  <head>",
        f'    <meta name="dtb:uid" content="{uid}"/>',
        f'    <meta name="dtb:totalElapsedTime" content="{total}"/>',
        f'    <meta name="dtb:generator" content="{generator}"/>',
        "    <layout>",
        '      <region id="text" top="0%" left="0%" right="0%" bottom="0%"/>',
        "    </layout>",
        "  </head>",
        "  <body>",
        f'    <seq id="mseq" dur="{duration}">',
    ]
    for container_id, clips in _groups(sync.clips):
        lines.append(f'      <seq id="{_xml(container_id)}">')
        for clip in clips:
            lines.extend(
                [
                    f'        <par id="{_xml(clip.smil_sid)}" endsync="last">',
                    f'          <text src="dtbook.xml#{_xml(clip.sent_id)}" region="text"/>',
                    (
                        f'          <audio src="{_xml(sync.audio_file)}" '
                        f'clipBegin="{format_npt(clip.clip_begin_ms)}" '
                        f'clipEnd="{format_npt(clip.clip_end_ms)}"/>'
                    ),
                    "        </par>",
                ]
            )
        lines.append("      </seq>")
    lines.extend(["    </seq>", "  </body>", "</smil>", ""])
    return "\n".join(lines)


def render_opf(sync: ChapterSync) -> str:
    metadata = sync.metadata
    uid = str(metadata["dtb:uid"])
    fields = [
        ("dc:Title", sync.package_title),
        ("dc:Creator", str(metadata.get("dc:Creator", ""))),
        ("dc:Subject", str(metadata.get("dc:Subject", ""))),
        ("dc:Description", str(metadata.get("dc:Description", ""))),
        ("dc:Publisher", str(metadata.get("dc:Publisher", ""))),
        ("dc:Date", str(metadata.get("dc:Date", ""))),
        ("dc:Language", str(metadata.get("dc:Language", "vi-VN"))),
        ("dc:Source", uid),
        ("dc:Format", str(metadata.get("dc:Format", "ANSI/NISO Z39.86-2005"))),
    ]
    dc_lines = []
    for name, value in fields:
        if not value:
            continue
        if name == "dc:Source":
            dc_lines.append(f'      <dc:Identifier id="uid">{_xml(uid)}</dc:Identifier>')
        dc_lines.append(f"      <{name}>{_xml(value)}</{name}>")
    extras = []
    for name in ("dtb:generator", "dc:Translator"):
        value = str(metadata.get(name, ""))
        if value:
            extras.append(f'      <meta name="{name}" content="{_xml(value)}"/>')
    note = str(metadata.get("note", ""))
    if note:
        extras.append(f'      <meta name="note" content="{_xml(note)}"/>')
    total = format_daisy_time(sync.audio_duration_ms)
    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            OPF_DOCTYPE,
            '<package xmlns="http://openebook.org/namespaces/oeb-package/1.0/" unique-identifier="uid" version="2005-1">',
            "  <metadata>",
            '    <dc-metadata xmlns:dc="http://purl.org/dc/elements/1.1/">',
            *dc_lines,
            "    </dc-metadata>",
            "    <x-metadata>",
            '      <meta name="dtb:multimediaType" content="audioFullText"/>',
            '      <meta name="dtb:multimediaContent" content="text,audio"/>',
            f'      <meta name="dtb:totalTime" content="{total}"/>',
            f'      <meta name="dtb:uid" content="{_xml(uid)}"/>',
            *extras,
            "    </x-metadata>",
            "  </metadata>",
            "  <manifest>",
            '    <item id="ncx" href="navigation.ncx" media-type="application/x-dtbncx+xml"/>',
            '    <item id="dtbook" href="dtbook.xml" media-type="application/x-dtbook+xml"/>',
            '    <item id="smil" href="mo0.smil" media-type="application/smil"/>',
            f'    <item id="audio" href="{_xml(sync.audio_file)}" media-type="audio/mpeg"/>',
            '    <item id="resource" href="resources.res" media-type="application/x-dtbresource+xml"/>',
            "  </manifest>",
            "  <spine>",
            '    <itemref idref="smil"/>',
            "  </spine>",
            "</package>",
            "",
        ]
    )


def render_ncx(sync: ChapterSync) -> str:
    uid = _xml(str(sync.metadata["dtb:uid"]))
    language = _xml(str(sync.metadata.get("dc:Language", "vi-VN")))
    generator = _xml(str(sync.metadata.get("dtb:generator", "DAISY 3 Pipeline")))
    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            NCX_DOCTYPE,
            f'<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" xml:lang="{language}">',
            "  <head>",
            f'    <meta name="dtb:uid" content="{uid}"/>',
            '    <meta name="dtb:depth" content="2"/>',
            '    <meta name="dtb:totalPageCount" content="0"/>',
            '    <meta name="dtb:maxPageNumber" content="0"/>',
            f'    <meta name="dtb:generator" content="{generator}"/>',
            "  </head>",
            f"  <docTitle><text>{_xml(sync.package_title)}</text></docTitle>",
            f"  <docAuthor><text>{_xml(sync.author)}</text></docAuthor>",
            "  <navMap>",
            '    <navPoint id="nav_book" playOrder="1">',
            f"      <navLabel><text>{_xml(sync.book_title)}</text></navLabel>",
            '      <content src="mo0.smil#sforsmil-1"/>',
            '      <navPoint id="nav_chapter" playOrder="2">',
            f"        <navLabel><text>{_xml(sync.chapter_title)}</text></navLabel>",
            '        <content src="mo0.smil#sfaux-heading"/>',
            "      </navPoint>",
            "    </navPoint>",
            "  </navMap>",
            "</ncx>",
            "",
        ]
    )


def render_resources() -> str:
    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            RES_DOCTYPE,
            '<resources xmlns="http://www.daisy.org/z3986/2005/resource/" version="2005-1">',
            "</resources>",
            "",
        ]
    )


def render_alignment(sync: ChapterSync) -> Dict[str, object]:
    return {
        "chapter_idx": sync.chapter_idx,
        "chapter_title": sync.chapter_title,
        "audio_file": sync.audio_file,
        "audio_duration": round(sync.audio_duration_ms / 1000, 3),
        "aligner": {
            "engine": sync.aligner_engine,
            "model": sync.aligner_model,
            "error": sync.aligner_error,
        },
        "counts": sync.counts,
        "clips": [
            {
                "sent_id": clip.sent_id,
                "smil_sid": clip.smil_sid,
                "container_id": clip.container_id,
                "clip_begin": round(clip.clip_begin_ms / 1000, 3),
                "clip_end": round(clip.clip_end_ms / 1000, 3),
                "method": clip.method,
                "source_text": clip.source_text,
            }
            for clip in sync.clips
        ],
    }


def write_package(sync: ChapterSync, task1_dir: Path, task2_dir: Path, output_dir: Path) -> None:
    from src.daisy.clips import chapter_folder_name

    folder_name = chapter_folder_name(sync.chapter_idx)
    destination = output_dir / folder_name
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(task1_dir / folder_name / "dtbook.xml", destination / "dtbook.xml")
    _link_or_copy(task2_dir / folder_name / sync.audio_file, destination / sync.audio_file)
    _write(destination / "mo0.smil", render_smil(sync))
    _write(destination / "book.opf", render_opf(sync))
    _write(destination / "navigation.ncx", render_ncx(sync))
    _write(destination / "resources.res", render_resources())
    _write(
        destination / "alignment.json",
        json.dumps(render_alignment(sync), ensure_ascii=False, indent=2) + "\n",
    )
