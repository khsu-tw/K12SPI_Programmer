"""SPI-NOR identification: JEDEC ID database + JESD216H SFDP parser (pure Python, no GUI/serial imports).

Supported 1.2 V parts (datasheets in DOC/):
  Macronix  MX25S1633F     C2 2B 25   16 Mbit   Vcc 1.14-1.6 V
  GigaDevice GD25UF16E     C8 83 15   16 Mbit   Vcc 1.14-1.26 V
  Winbond   W25Q65NE       EF 65 17   64 Mbit   Vcc 1.14-1.26 V
  Winbond   W25Q32NE       EF 65 16   32 Mbit   Vcc 1.14-1.26 V
The common safe window for all of them is 1.14-1.26 V (VIO_MIN_MV / VIO_MAX_MV in the firmware).
"""
import struct

SFDP_SIGNATURE = b"SFDP"           # 0x50444653 little-endian (JESD216H 6.2.1)
VIO_MIN_MV = 1140
VIO_MAX_MV = 1260

# JEDEC manufacturer ID (JEP106, single byte of the 9Fh reply) -> name. Only the vendors of the supported parts
# are certain; the others are common SPI-NOR vendors and are shown with "(JEP106)" so they read as a lookup.
MANUFACTURERS = {0xC2: "Macronix", 0xC8: "GigaDevice", 0xEF: "Winbond"}
JEP106_EXTRA = {0x20: "Micron/ST", 0x1F: "Adesto/Renesas", 0x9D: "ISSI", 0xBF: "Microchip SST",
                0x01: "Infineon/Cypress", 0x85: "Puya", 0x68: "Boya", 0x0B: "XTX", 0xA1: "Fudan", 0x5E: "Zbit"}

# SFDP parameter table IDs (MSB FFh = JEDEC owned), names per JESD216H clauses 6.4-6.20
SFDP_TABLES = {
    0xFF00: "Basic Flash Parameter", 0xFF81: "Sector Map", 0xFF03: "RPMC", 0xFF84: "4-byte Address Instruction",
    0xFF05: "xSPI Profile 1.0", 0xFF06: "xSPI Profile 2.0", 0xFF87: "SCCR Map", 0xFF09: "SCCR Map xSPI 2.0",
    0xFF88: "SCCR Map Multi-Chip", 0xFF0A: "Octal DDR command sequences", 0xFF0C: "Quad IO with DS",
    0xFF8D: "Quad DDR command sequences", 0xFF8E: "Secure Packet R/W", 0xFF0F: "GRAM",
    0xFF90: "Safety Extensions (Interface CRC)", 0xFF11: "SFDP CRC-32", 0xFF12: "ECC",
}


def table_name(tid):
    if tid in SFDP_TABLES:
        return SFDP_TABLES[tid]
    msb, lsb = tid >> 8, tid & 0xFF
    # JESD216H 6.3.3: an ID LSB with odd parity is a JEP106 manufacturer code (vendor owned table);
    # MSB 01h-7Fh is its JEP106 bank. Legacy devices keep MSB = FFh, e.g. Macronix FFC2h.
    if bin(lsb).count("1") % 2 == 1 or 0x01 <= msb <= 0x7F:
        return "Vendor table (%s)" % vendor_name(lsb)
    return "Unknown table %04Xh" % tid


def vendor_name(mfr):
    if mfr in MANUFACTURERS:
        return MANUFACTURERS[mfr]
    if mfr in JEP106_EXTRA:
        return "%s (JEP106)" % JEP106_EXTRA[mfr]
    return "Unknown (0x%02X)" % mfr

# SR bit layouts (bit number -> name), per datasheet. Used by the Config SR dialog.
SR1_MX = [("SRWD", 7), ("QE", 6), ("BP3", 5), ("BP2", 4), ("BP1", 3), ("BP0", 2)]
SR1_GD = [("SRP0", 7), ("BP4", 6), ("BP3", 5), ("BP2", 4), ("BP1", 3), ("BP0", 2)]
SR1_W = [("SRP", 7), ("SEC", 6), ("TB", 5), ("BP2", 4), ("BP1", 3), ("BP0", 2)]


class FlashInfo:
    """Static per-part data that SFDP does not (or not reliably) carry."""

    def __init__(self, vendor, part, jedec, size, sr_bits, chip_erase_s, sr_mask, voltage, has_sr2,
                 datasheet=True):
        self.vendor, self.part, self.jedec = vendor, part, jedec
        self.datasheet = datasheet       # False = entry inferred from a real part, no matching datasheet
        self.size = size                 # bytes
        self.sr_bits = sr_bits           # writable SR1 bit names for the Config dialog
        self.chip_erase_s = chip_erase_s  # worst-case chip erase from the datasheet (watchdog + progress)
        self.sr_mask = sr_mask           # SR1 bits whose readback must match after WRSR
        self.voltage = voltage           # (min, max) volts from the datasheet
        self.has_sr2 = has_sr2           # SR2 exists: WRSR must rewrite it too (a 1-byte WRSR clears it on GD25UF16E)

    @property
    def name(self):
        return "%s %s" % (self.vendor, self.part)


KNOWN = {
    # tCE 57 s = Ultra Low Power mode maximum (MX25S1633FM2IG2 powers up in ULP; HPM is 38 s)
    (0xC2, 0x2B, 0x25): FlashInfo("Macronix", "MX25S1633F", (0xC2, 0x2B, 0x25), 0x200000, SR1_MX, 57.0, 0xFC, (1.14, 1.6), False),
    (0xC8, 0x83, 0x15): FlashInfo("GigaDevice", "GD25UF16E", (0xC8, 0x83, 0x15), 0x200000, SR1_GD, 50.0, 0xFC, (1.14, 1.26), True),
    (0xEF, 0x65, 0x17): FlashInfo("Winbond", "W25Q65NE", (0xEF, 0x65, 0x17), 0x800000, SR1_W, 140.0, 0xFC, (1.14, 1.26), True),
    # W25Q32NE RevE (DOC/): 9Fh = EF 6516h, 32 Mbit, SR1 SRP/SEC/TB/BP2-0, SR2 via 31h, tCE max 70 s
    # (IoT mode only slows page program / sector / block erase, not chip erase). Verified on a real part.
    (0xEF, 0x65, 0x16): FlashInfo("Winbond", "W25Q32NE", (0xEF, 0x65, 0x16), 0x400000,
                                  SR1_W, 70.0, 0xFC, (1.14, 1.26), True),
}

# W25Q64NE (DOC/W25Q64NE RevB2) is deliberately NOT supported: it answers 9Fh = EF 6517h exactly like the
# W25Q65NE and has the same 64 Mbit SFDP density, so the two cannot be told apart. The user chose to keep the
# W25Q65NE only (2026-10-20). Note a W25Q64NE detected as W25Q65NE would need longer waits than the W25Q65NE
# values: tCE 160 s vs 140 s, tRES1 50 us vs 20 us.


# Extra 9Fh IDs that map to an entry above (none at present).
ALIASES = {}


def supported_lines():
    """One line per supported part, for the GUI's Supported Flash list."""
    return ["%-10s %-11s %02X %02X %02X  %3d Mbit  %.2f-%.2f V" %
            ((i.vendor, i.part) + i.jedec + (i.size * 8 >> 20,) + i.voltage) for i in KNOWN.values()]


class SfdpError(Exception):
    pass


def _dword(b, off):
    return struct.unpack_from("<I", b, off)[0]


def parse_sfdp(raw):
    """Parse the SFDP header + JEDEC Basic Flash Parameter Table (JESD216H 6.2 / 6.4).

    `raw` is the first >=256 bytes of the SFDP space. Returns a dict, raises SfdpError if the
    signature is missing or the basic table is not present/readable.
    """
    if len(raw) < 16 or raw[:4] != SFDP_SIGNATURE:
        raise SfdpError("no SFDP signature (got %s)" % raw[:4].hex())
    minor, major, nph, access = raw[4], raw[5], raw[6], raw[7]
    out = {"major": major, "minor": minor, "nph": nph + 1, "access": access, "tables": []}
    basic = None
    for i in range(nph + 1):
        o = 8 + 8 * i
        if o + 8 > len(raw):
            break
        id_lsb, t_minor, t_major, t_len = raw[o], raw[o + 1], raw[o + 2], raw[o + 3]
        ptp = raw[o + 4] | (raw[o + 5] << 8) | (raw[o + 6] << 16)
        id_msb = raw[o + 7]
        out["tables"].append({"id": (id_msb << 8) | id_lsb, "rev": (t_major, t_minor), "dwords": t_len, "ptp": ptp})
        if id_lsb == 0x00 and id_msb == 0xFF and basic is None:     # JEDEC Basic Flash Parameter Table
            basic = out["tables"][-1]
    if basic is None:
        raise SfdpError("JEDEC Basic Flash Parameter Table not found")
    n, ptp = basic["dwords"], basic["ptp"]
    if n < 2 or ptp + 8 > len(raw):
        raise SfdpError("basic table out of range (ptp=0x%X, %d dwords)" % (ptp, n))

    out["basic"] = basic
    d1 = _dword(raw, ptp)
    addr_mode = (d1 >> 17) & 0x3
    out["addr_bytes"] = {0: "3", 1: "3 or 4", 2: "4"}.get(addr_mode, "reserved")
    out["erase4k_cmd"] = (d1 >> 8) & 0xFF
    out["erase4k_ok"] = ((d1 >> 0) & 0x3) == 0x1
    # DWORD 1 bit 16/20/21/22 = (1S-1S-2S)/(1S-2S-2S)/(1S-4S-4S)/(1S-1S-4S) fast read, bit 19 = DTR
    modes = [name for bit, name in ((16, "1-1-2"), (20, "1-2-2"), (22, "1-1-4"), (21, "1-4-4")) if d1 >> bit & 1]
    out["dtr"] = bool(d1 >> 19 & 1)
    if n >= 5 and ptp + 20 <= len(raw):                 # DWORD 5 bit 0 = (2S-2S-2S), bit 4 = (4S-4S-4S)
        d5 = _dword(raw, ptp + 16)
        modes += [name for bit, name in ((0, "2-2-2"), (4, "4-4-4")) if d5 >> bit & 1]
    out["read_modes"] = modes

    d2 = _dword(raw, ptp + 4)
    out["density_bits"] = (1 << (d2 & 0x7FFFFFFF)) if d2 & 0x80000000 else (d2 & 0x7FFFFFFF) + 1
    out["size"] = out["density_bits"] // 8

    out["erase_types"] = []                         # (size_bytes, opcode); DWORD 8 = types 1/2, DWORD 9 = types 3/4
    slots = {}                                      # erase type number (1..4) -> size, for DWORD 10
    for dw in (8, 9):
        if n >= dw and ptp + 4 * dw <= len(raw):
            d = _dword(raw, ptp + 4 * (dw - 1))
            for k, sh in enumerate((0, 16)):
                nn, op = (d >> sh) & 0xFF, (d >> (sh + 8)) & 0xFF
                if nn:                              # size field is N: erase size = 2^N bytes, 0 = type absent
                    out["erase_types"].append((1 << nn, op))
                    slots[(dw - 8) * 2 + k + 1] = 1 << nn
    # DWORD 10: typical erase time of erase types 1..4 (count at bits 4/11/18/25, 2-bit unit above it)
    # and the typical->maximum multiplier in bits 3:0 (max = 2 * (count + 1) * typical)
    out["erase_typ_ms"] = {}
    if n >= 10 and ptp + 40 <= len(raw):
        d10 = _dword(raw, ptp + 36)
        out["max_mult"] = 2 * ((d10 & 0xF) + 1)
        for t, lo in ((1, 4), (2, 11), (3, 18), (4, 25)):
            if t in slots:
                out["erase_typ_ms"][slots[t]] = ((d10 >> lo & 0x1F) + 1) * (1, 16, 128, 1000)[d10 >> (lo + 5) & 0x3]
    # DWORD 11: chip-erase typical time, page size, page-program typical time
    if n >= 11 and ptp + 44 <= len(raw):
        d11 = _dword(raw, ptp + 40)
        out["page_size"] = 1 << ((d11 >> 4) & 0xF)
        out["chip_erase_typ_s"] = (((d11 >> 24) & 0x1F) + 1) * (0.016, 0.256, 4.0, 64.0)[(d11 >> 29) & 0x3]
        out["page_prog_typ_us"] = (((d11 >> 8) & 0x1F) + 1) * (8, 64)[(d11 >> 13) & 0x1]
    return out


def _mbit(bits):
    return "%d Mbit" % (bits >> 20) if bits >= 1 << 20 else "%d Kbit" % (bits >> 10)


def _ms(ms):
    return "%.0f ms" % ms if ms < 1000 else "%.1f s" % (ms / 1000.0)


def generic_name(jedec, sfdp):
    """Display name for a device that is not in KNOWN, built only from JEDEC ID + SFDP fields."""
    return "%s SPI-NOR %s (ID %02X %02X %02X)" % ((vendor_name(jedec[0]), _mbit(sfdp["density_bits"])) +
                                                   tuple(jedec))


def describe_sfdp(sfdp):
    """Human-readable lines for every SFDP field we decode (JESD216H 6.2 header, 6.3 parameter headers,
    6.4 Basic Flash Parameter Table). Used to show a device that is not in the supported list."""
    lines = ["SFDP header: JESD216 rev %d.%d, %d parameter header(s), access protocol %02Xh" %
             (sfdp["major"], sfdp["minor"], sfdp["nph"], sfdp["access"])]
    for t in sfdp["tables"]:
        lines.append("  table %-34s ID %04Xh  rev %d.%d  %2d DWORDs  @ 0x%06X" %
                     (table_name(t["id"]), t["id"], t["rev"][0], t["rev"][1], t["dwords"], t["ptp"]))
    lines.append("Density: %s (%d KB)" % (_mbit(sfdp["density_bits"]), sfdp["size"] // 1024))
    lines.append("Address: %s-byte" % sfdp["addr_bytes"])
    if "page_size" in sfdp:
        lines.append("Page: %d bytes, typ program %d us" % (sfdp["page_size"], sfdp["page_prog_typ_us"]))
    er = []
    for sz, op in sfdp["erase_types"]:
        t = sfdp["erase_typ_ms"].get(sz)
        er.append("%dK=%02Xh%s" % (sz // 1024, op, " (typ %s)" % _ms(t) if t else ""))
    lines.append("Erase: " + (", ".join(er) or "none listed"))
    if "chip_erase_typ_s" in sfdp:
        mult = sfdp.get("max_mult")
        lines.append("Chip erase: typ %.1f s%s" % (sfdp["chip_erase_typ_s"],
                                                  ", max ~%.0f s" % (sfdp["chip_erase_typ_s"] * mult) if mult else ""))
    lines.append("Fast read: 1-1-1%s%s" % ("".join(", " + m for m in sfdp["read_modes"]),
                                           ", DTR" if sfdp["dtr"] else ""))
    return lines


def identify(jedec, sfdp=None):
    """Combine the 9Fh ID and (optional) parsed SFDP into a descriptor dict for the GUI.

    `blockers` are hard reasons to refuse program/erase; `warnings` are informational.
    The bridge only supports 3-byte addressing and 256-byte pages, and the GUI erase plan needs the 4 KB
    erase (20h), so anything else is refused rather than guessed.
    """
    key = tuple(jedec)
    info = KNOWN.get(ALIASES.get(key, key))
    res = {
        "jedec": key,
        "vendor": vendor_name(key[0]),
        "known": info is not None,
        "info": info,
        "sfdp": sfdp,
        "name": info.name if info else (generic_name(key, sfdp) if sfdp else "Unknown %02X %02X %02X" % key),
        "size": (sfdp or {}).get("size") or (info.size if info else 0),
        "page": (sfdp or {}).get("page_size") or 256,
        "erase_sizes": sorted({sz for sz, op in (sfdp or {}).get("erase_types", [])}),
        "blockers": [],
        "warnings": [],
    }
    res["sfdp_lines"] = describe_sfdp(sfdp) if sfdp else []
    if info is None:
        res["blockers"].append("ID %02X %02X %02X is not in the supported list (%s); shown from SFDP only, "
                               "program/erase disabled" % (key + (", ".join(i.part for i in KNOWN.values()),)))
    if sfdp is None:
        res["blockers"].append("SFDP not readable (JESD216 SFDP is required to identify the device)")
        return res
    if info and not info.datasheet:
        res["warnings"].append("%s: datasheet not in DOC/; capacity from SFDP, SR bits / erase time borrowed "
                               "from a related part" % info.part)
    if info and key in ALIASES:
        res["warnings"].append("ID %02X %02X %02X is not the datasheet value (%02X %02X %02X) but SFDP is checked" %
                               (key + ALIASES[key]))
    if info and sfdp.get("size") != info.size:
        res["blockers"].append("SFDP density %d KB does not match %s (%d KB): wrong ID or bad link" %
                               (sfdp["size"] // 1024, info.name, info.size // 1024))
    if sfdp.get("addr_bytes") == "4":
        res["blockers"].append("device is 4-byte-address only; the bridge uses 3-byte addressing")
    elif sfdp.get("addr_bytes") not in ("3", None):
        res["warnings"].append("device supports %s-byte addressing; using 3-byte (default)" % sfdp["addr_bytes"])
    if res["page"] != 256:
        res["blockers"].append("page size %d bytes (bridge supports 256)" % res["page"])
    if not (sfdp.get("erase4k_ok") and sfdp.get("erase4k_cmd") == 0x20):
        res["blockers"].append("4 KB sector erase (20h) not advertised in SFDP")
    return res
