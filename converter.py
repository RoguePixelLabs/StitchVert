from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from pyembroidery import (
    COLOR_BREAK, COLOR_CHANGE, COMMAND_MASK, END, JUMP, NEEDLE_AT, NEEDLE_SET,
    SEQUIN_EJECT, SEW_TO, STITCH, TRIM, EmbPattern, EmbThread,
    decode_embroidery_command, encode_thread_change,
)

import legacy_formats

FORMATS = {
    item["extension"]: item
    for item in EmbPattern.supported_formats()
    if item["category"] == "embroidery"
}
for extension, description in legacy_formats.DESCRIPTIONS.items():
    FORMATS[extension] = {"description": description}
for extension, reader in legacy_formats.READERS.items():
    FORMATS[extension]["reader"] = reader
for extension, writer in legacy_formats.WRITERS.items():
    FORMATS[extension]["writer"] = writer

INPUTS = sorted(ext for ext, item in FORMATS.items() if item.get("reader"))
OUTPUTS = sorted(ext for ext, item in FORMATS.items() if item.get("writer"))
RGB_FORMATS = {"pes", "vp3", "xxx", "tbf", "gcode", "vip"}
PALETTE_FORMATS = {"pec", "jef", "hus", "sew"}
SEWING = {STITCH, SEW_TO, NEEDLE_AT, SEQUIN_EJECT}
CHANGES = {COLOR_CHANGE, COLOR_BREAK, NEEDLE_SET}
FALLBACK_COLORS = (
    "#315ec6", "#e25442", "#008778", "#8a50b4", "#bc6900",
    "#ca3974", "#48783d", "#41788d",
)


def is_pale(color):
    red, green, blue = bytes.fromhex(color[1:])
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue > 193


@dataclass
class Design:
    pattern: EmbPattern
    runs: list
    sections: list
    used_threads: list
    estimated: set
    bounds: tuple
    count: int


def load_design(path):
    extension = path.suffix.lower().lstrip(".")
    if extension not in INPUTS:
        raise ValueError(f"Unsupported input format: {path.suffix or '(no extension)'}")
    pattern = EmbPattern.read_embroidery(FORMATS[extension]['reader'], str(path))
    if pattern is None:
        raise ValueError("The file could not be decoded.")

    runs = []
    sections = []
    section_stitches = 0
    used_threads = []
    used = set()
    estimated = set()
    index = 0
    next_index = 0
    active = False
    run = None
    previous = (0, 0)
    anchored = True
    left = top = float("inf")
    right = bottom = float("-inf")
    count = 0
    for stitch in pattern.stitches:
        x, y, data = stitch
        command, thread, needle, _ = decode_embroidery_command(data)
        point = (x, y)
        if command == END:
            break
        if command in CHANGES:
            if section_stitches:
                sections.append((index, section_stitches))
                section_stitches = 0
            index = next_index if thread is None else thread
            if extension == "tbf" and needle:
                index = needle - 1
                stitch[2] = encode_thread_change(NEEDLE_SET, index, needle)
            if thread is None:
                next_index += 1
            active = True
            run = None
            anchored = False
        elif command in SEWING:
            if not active:
                index = next_index
                next_index += 1
                active = True
            while len(pattern.threadlist) <= index:
                slot = len(pattern.threadlist)
                pattern.add_thread(EmbThread(FALLBACK_COLORS[slot % len(FALLBACK_COLORS)]))
                estimated.add(slot)
            if index not in used:
                used.add(index)
                used_threads.append(index)
            start = previous if anchored else point
            if run is None:
                run = [start]
                runs.append((index, run))
            run.append(point)
            left = min(left, start[0], x)
            top = min(top, start[1], y)
            right = max(right, start[0], x)
            bottom = max(bottom, start[1], y)
            anchored = True
            count += 1
            section_stitches += 1
        elif command in {JUMP, TRIM}:
            run = None
            anchored = False
        previous = point
    if not count:
        raise ValueError("The file contains no readable stitches.")
    if section_stitches:
        sections.append((index, section_stitches))
    return Design(pattern, runs, sections, used_threads, estimated, (left, top, right, bottom), count)


def export_design(design, destination):
    extension = destination.suffix.lower().lstrip(".")
    if extension not in OUTPUTS:
        raise ValueError(f"Unsupported output format: {destination.suffix}")
    pattern = design.pattern.copy()
    pattern.stitches = [stitch[:] for stitch in pattern.stitches]
    pattern.threadlist = deepcopy(pattern.threadlist)
    settings = {"pes": {"version": 6}, "jef": {"trims": True}}.get(extension, {})
    if extension in {"dst", "tbf", "dsb", "dsz", "tap", "t01"}:
        # These headers use fixed-width ASCII fields.
        name = str(pattern.get_metadata("name", destination.stem))
        pattern.metadata("name", name.encode("ascii", "replace").decode()[:16])
    if extension == "tbf":
        if len(pattern.threadlist) > 254:
            raise ValueError("This design exceeds the TBF thread table capacity.")
        # Number needles by the thread table, including repeated thread uses.
        next_index = 0
        active = False
        changes = 0
        for stitch in pattern.stitches:
            command, thread, _, order = decode_embroidery_command(stitch[2])
            if command in CHANGES:
                index = next_index if thread is None else thread
                stitch[2] = encode_thread_change(NEEDLE_SET, index, index + 1, order)
                if thread is None:
                    next_index += 1
                changes += 1
                active = True
            elif command in SEWING and not active:
                next_index = 1
                active = True
                changes += 1
        if changes > 256:
            raise ValueError("This design exceeds the TBF thread-order capacity.")
        settings = {"needle_count": 254}

    if extension in {"dsb", "dsz"}:
        settings = {"needle_count": 15 if extension == "dsb" else 12}

    # Write to a sibling first so a failed encoder cannot replace a good file.
    temporary = None
    try:
        with NamedTemporaryFile(dir=destination.parent, suffix=destination.suffix, delete=False) as handle:
            temporary = Path(handle.name)
        EmbPattern.write_embroidery(FORMATS[extension]['writer'], pattern, str(temporary), settings)
        if temporary.stat().st_size == 0:
            raise ValueError("The encoder produced an empty file.")
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
