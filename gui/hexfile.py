"""Intel HEX / raw binary loader for the MX25S1633F programmer."""
import zlib


class HexError(Exception):
    pass


def parse_intel_hex(text):
    """Return (start_address, bytes). Gaps between records are filled with 0xFF."""
    base = 0
    chunks = {}
    eof = False
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line[0] != ":":
            raise HexError("line %d: missing ':'" % n)
        try:
            b = bytes.fromhex(line[1:])
        except ValueError:
            raise HexError("line %d: bad hex digits" % n)
        if len(b) < 5 or len(b) != b[0] + 5:
            raise HexError("line %d: bad length" % n)
        if sum(b) & 0xFF:
            raise HexError("line %d: checksum error" % n)
        cnt, addr, typ = b[0], (b[1] << 8) | b[2], b[3]
        data = b[4:4 + cnt]
        if typ == 0:
            a = base + addr
            for i, v in enumerate(data):
                chunks[a + i] = v
        elif typ == 1:
            eof = True
            break
        elif typ == 2:
            base = ((data[0] << 8) | data[1]) << 4
        elif typ == 4:
            base = ((data[0] << 8) | data[1]) << 16
        # types 3 and 5 (start address) are ignored
    if not eof:
        raise HexError("missing end-of-file record")
    if not chunks:
        raise HexError("no data records")
    lo, hi = min(chunks), max(chunks)
    out = bytearray(b"\xff" * (hi - lo + 1))
    for a, v in chunks.items():
        out[a - lo] = v
    return lo, bytes(out)


def load_file(path):
    """Load .hex/.ihx (Intel HEX) or anything else as raw binary. Returns (start, data)."""
    with open(path, "rb") as f:
        raw = f.read()
    if path.lower().endswith((".hex", ".ihx")):
        return parse_intel_hex(raw.decode("ascii", "replace"))
    return 0, raw


def crc32(data):
    return zlib.crc32(data) & 0xFFFFFFFF
