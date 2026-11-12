"""Additional machine codecs built on the bundled pyembroidery encoder."""

from io import BytesIO
from struct import Struct, pack
from types import SimpleNamespace

from pyembroidery import (
    COLOR_CHANGE, COMMAND_MASK, END, JUMP, NEEDLE_SET, STITCH, STOP, TRIM,
    DstWriter, DszReader, EmbThread, TapReader, decode_embroidery_command,
    encode_thread_change, expand,
)
from pyembroidery.EmbThreadHus import get_thread_set as hus_palette
from pyembroidery.EmbThreadSew import get_thread_set as sew_palette

# VIP color mask and field layout documented by Embroidermodder/libembroidery.
VIP_MASK = bytes.fromhex(
    "2E82E46F38A9DCC67BB628ACFDAA8A4E762EF0E4251B8A684E92B9B495F03EEF"
    "F74024183931BBE153A81FB13A07FBCBE60081500E40E12C73500D91D60A5DD6"
    "8BB862AE4700535AB780AA28F75D705E2C0B98E3A0986047899B82FB40C9B400"
    "0E686A1E0985C05381D19889AFE8854FE3698903A12E8FCFED919F581ED6843C"
    "0927BDF4C390C0511B2B63BCB93D404D626FE08CF55D08FD3D5036D7C9C943E4"
    "2DCB95B6F40DEAC2FD663F5EBD69062A0319472BDF38EA4F804995B2D6F99A75"
    "F4D89B1DB0A469DBA921796FD8DE33FE9F04E59A6B9B7383627CB96676F25BC9"
    "5EFC74AA6CF1CD93CEE98053033B974B3976C2C156CB70FD3B3E5257815D568D"
    "5190D476D7D516026DF24DE10E964FA13AA0605964041AE467B6ED3F7420551F"
    "FB23929153C865AB9D51D673DE01B180B7C0D6801C2E3C8363EEBC3325E20E7A"
    "67DE3F7114499C92930D269A0EDAED6FA4890C1BF0A1DFE19E3C0478E4AB6DFF"
    "9CAFCAC788179CE5B7336DDCED8F6C181D7106B1C5E2CF137781C5B70A140A6B"
    "4026A088D1626AB35012B99BB5839B37"
)
VIP_MAGIC = 0x0190FC5D
HUS_MAGIC = 0x00C8AF5B
COMPRESSED_HEADER = Struct("<IIIhhhhIII8xH")
MAX_COMPRESSED_COMMANDS = 1_000_000


def write_tape(pattern, stream, settings):
    dst = BytesIO()
    DstWriter.write(pattern, dst, settings)
    stream.write(dst.getbuffer()[DstWriter.DSTHEADERSIZE:])


def read_dsz(stream, pattern, settings):
    DszReader.read(stream, pattern, settings)
    for stitch in pattern.stitches:
        command, thread, needle, order = decode_embroidery_command(stitch[2])
        if command == NEEDLE_SET and needle is not None:
            stitch[2] = encode_thread_change(command, thread, needle + 1, order)


def read_vip(stream, pattern, settings):
    data = stream.read()
    if len(data) < 46:
        raise ValueError("Truncated VIP header.")
    magic, count, colors, _, _, _, _, commands, xs, ys, _ = COMPRESSED_HEADER.unpack_from(data)
    if magic != VIP_MAGIC or not 0 < count <= MAX_COMPRESSED_COMMANDS:
        raise ValueError("Invalid VIP signature or command count.")
    if 4 * colors > len(VIP_MASK) or not 46 + 4 * colors <= commands < xs < ys < len(data):
        raise ValueError("Invalid VIP color table or stitch offsets.")
    table = data[46:46 + 4 * colors]
    previous = 0
    decoded = bytearray()
    for byte, mask in zip(table, VIP_MASK):
        decoded.append(byte ^ mask ^ previous)
        previous = byte
    for offset in range(0, len(decoded), 4):
        pattern.add_thread(EmbThread(int.from_bytes(decoded[offset:offset + 3], "big")))

    attributes, x_values, y_values = (
        expand(data[start:stop], count - 1)
        for start, stop in ((commands, xs), (xs, ys), (ys, len(data)))
    )
    if min(len(attributes), len(x_values), len(y_values)) < count:
        raise ValueError("Truncated VIP stitch data.")
    for command, x, y in zip(attributes[:count], x_values[:count], y_values[:count]):
        dx = x if x < 128 else x - 256
        dy = -(y if y < 128 else y - 256)
        if command == 0x90:
            break
        if command == 0x80:
            pattern.stitch(dx, dy)
        elif command == 0x81:
            pattern.move(dx, dy)
        elif command == 0x84:
            pattern.color_change(dx, dy)
        elif command == 0x88:
            if dx or dy:
                pattern.move(dx, dy)
            pattern.trim()
        else:
            raise ValueError(f"Unsupported VIP stitch command 0x{command:02X}.")
    pattern.end()


def literal_blocks(data):
    # The HUS/VIP decoder accepts literal Huffman blocks of up to 65535 bytes.
    # 02 A0 01 FE describes the fixed tree with one eight-bit code per byte.
    result = bytearray()
    for offset in range(0, len(data), 65535):
        block = data[offset:offset + 65535]
        result.extend(len(block).to_bytes(2, "big"))
        result.extend(bytes.fromhex("02 A0 01 FE"))
        result.extend(block)
    return result


def write_compressed(pattern, stream, settings, vip=False):
    colors = len(pattern.threadlist)
    if not 1 <= colors <= 24:
        raise ValueError("HUS and VIP exports support up to 24 thread sections.")
    commands, xs, ys = bytearray(), bytearray(), bytearray()
    codes = {STITCH: 0x80, JUMP: 0x81, COLOR_CHANGE: 0x84, END: 0x90}
    codes[TRIM] = 0x81 if vip else 0x88
    previous_x = previous_y = 0
    for x, y, data in pattern.stitches:
        x, y = round(x), round(y)
        command = data & COMMAND_MASK
        if command == STOP:
            raise ValueError("This format cannot preserve a standalone stop.")
        if command not in codes:
            continue
        dx, dy = x - previous_x, previous_y - y
        if not (-127 <= dx <= 127 and -127 <= dy <= 127):
            raise ValueError("A stitch or jump exceeds the HUS/VIP movement limit.")
        commands.append(codes[command])
        xs.append(dx & 0xff)
        ys.append(dy & 0xff)
        previous_x, previous_y = x, y
    if len(commands) > MAX_COMPRESSED_COMMANDS:
        raise ValueError("This design exceeds the supported command count.")
    streams = [literal_blocks(data) for data in (commands, xs, ys)]
    if vip:
        table = bytearray(pack("<I", colors * 4))
        previous = 0
        rgb = b"".join((thread.color & 0xffffff).to_bytes(3, "big") + b"\x01" for thread in pattern.threadlist)
        for byte, mask in zip(rgb, VIP_MASK):
            previous ^= byte ^ mask
            table.append(previous)
        table.extend(pack("<I", 1) * (colors + 1))
        table.extend(bytes(6))
    else:
        palette = hus_palette()
        table = b"".join(pack("<H", thread.find_nearest_color_index(palette))
                         for thread in pattern.threadlist)
    start = COMPRESSED_HEADER.size + len(table)
    left, top, right, bottom = map(round, pattern.bounds())
    stream.write(COMPRESSED_HEADER.pack(
        VIP_MAGIC if vip else HUS_MAGIC, len(commands), colors, right, 1 - top, left,
        1 - bottom, start, start + len(streams[0]), start + len(streams[0]) + len(streams[1]), 0,
    ))
    stream.write(table)
    stream.writelines(streams)


def write_sew(pattern, stream, settings):
    palette = sew_palette()
    colors = [thread.find_nearest_color_index(palette) for thread in pattern.threadlist]
    header = pack("<H", len(colors)) + b"".join(pack("<H", color) for color in colors)
    if len(header) > 0x1D78:
        raise ValueError("The SEW thread table is too large.")
    stream.write(header.ljust(0x1D78, b" "))
    previous_x = previous_y = 0
    for x, y, data in pattern.stitches:
        x, y = round(x), round(y)
        command = data & COMMAND_MASK
        delta = bytes(((x - previous_x) & 0xff, (previous_y - y) & 0xff))
        if command == STITCH:
            stream.write(delta)
        elif command == JUMP:
            stream.write(b"\x80\x02" + delta)
        elif command == COLOR_CHANGE:
            stream.write(b"\x80\x01\x00\x00")
        elif command == STOP:
            raise ValueError("SEW export cannot preserve a standalone stop.")
        elif command == END:
            stream.write(b"\x80\x00\x00\x00")
            break
        else:
            continue
        previous_x, previous_y = x, y


def write_needle_tape(pattern, stream, settings, dsb):
    # These formats use the same 512-byte text header as DST.
    header = BytesIO()
    header_pattern = pattern.copy()
    header_pattern.stitches = [
        (x, y, COLOR_CHANGE if (data & COMMAND_MASK) == NEEDLE_SET else data)
        for x, y, data in pattern.stitches
    ]
    DstWriter.write(header_pattern, header, settings)
    stream.write(header.getbuffer()[:DstWriter.DSTHEADERSIZE])
    previous_x = previous_y = 0
    for x, y, data in pattern.stitches:
        x, y = round(x), round(y)
        command, _, needle, _ = decode_embroidery_command(data)
        if command in (STITCH, JUMP):
            dx, dy = x - previous_x, previous_y - y
            x_sign, y_sign = (0x20, 0x40) if dsb else (0x40, 0x20)
            control = int(command == JUMP)
            control |= x_sign if dx < 0 else 0
            control |= y_sign if dy < 0 else 0
        else:
            dx = dy = 0
            if command == NEEDLE_SET:
                limit = 15 if dsb else 12
                if not 1 <= needle <= limit:
                    raise ValueError(f"This format supports needle numbers 1 through {limit}.")
                control = 0xE8 + needle if dsb else 0x83 + 2 * (needle - 1)
            elif command == TRIM:
                control = 0xE7 if dsb else 0x9B
            elif command == STOP:
                control = 0xE8 if dsb else 0x82
            elif command == END:
                control = 0xF8 if dsb else 0x10
            else:
                continue
        stream.write(bytes((control, abs(dy), abs(dx)) if dsb else (abs(dy), abs(dx), control)))
        previous_x, previous_y = x, y
        if command == END:
            break


def writer(write, distance=127, thread_change=COLOR_CHANGE, trim=True):
    return SimpleNamespace(write=write, MAX_STITCH_DISTANCE=distance, MAX_JUMP_DISTANCE=distance,
                           ROUND=True, EXPLICIT_TRIM=trim, THREAD_CHANGE_COMMAND=thread_change)


def write_vip(pattern, stream, settings):
    write_compressed(pattern, stream, settings, vip=True)


def write_dsb(pattern, stream, settings):
    write_needle_tape(pattern, stream, settings, dsb=True)


def write_dsz(pattern, stream, settings):
    write_needle_tape(pattern, stream, settings, dsb=False)


READERS = {
    "dsz": SimpleNamespace(read=read_dsz),
    "t01": TapReader,
    "vip": SimpleNamespace(read=read_vip),
}
WRITERS = {
    "dsb": writer(write_dsb, 121, NEEDLE_SET),
    "dsz": writer(write_dsz, 121, NEEDLE_SET),
    "hus": writer(write_compressed),
    "sew": writer(write_sew, trim=False),
    "t01": writer(write_tape, 121),
    "tap": writer(write_tape, 121),
    "vip": writer(write_vip),
}
DESCRIPTIONS = {"t01": "T01 embroidery stitch file", "vip": "Viking / Pfaff VIP"}
