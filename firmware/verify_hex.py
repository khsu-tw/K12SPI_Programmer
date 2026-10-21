"""Compare a built HEX with a device read-back (MPLAB IPE -GF). Exit 1 on any mismatch.

Checks every program-memory byte and every configuration byte present in the built HEX.
Usage: verify_hex.py built.hex readback.hex
"""
import sys


def load(path):
    mem, base = {}, 0
    with open(path) as f:
        for ln in f:
            ln = ln.strip()
            if not ln.startswith(":"):
                continue
            b = bytes.fromhex(ln[1:])
            n, addr, typ = b[0], (b[1] << 8) | b[2], b[3]
            data = b[4:4 + n]
            if typ == 0:
                for i, v in enumerate(data):
                    mem[base + addr + i] = v
            elif typ == 4:
                base = ((data[0] << 8) | data[1]) << 16
            elif typ == 2:
                base = ((data[0] << 8) | data[1]) << 4
    return mem


def main():
    want, got = load(sys.argv[1]), load(sys.argv[2])
    bad = [a for a in sorted(want) if got.get(a, 0xFF) != want[a]]
    print("verify: %d bytes checked, %d mismatches" % (len(want), len(bad)))
    for a in bad[:10]:
        print("  0x%06X  want %02X  device %02X" % (a, want[a], got.get(a, 0xFF)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
