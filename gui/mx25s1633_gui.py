#!/usr/bin/env python3
"""1.2 V SPI-NOR Flash Programmer GUI  (PIC18F16Q20 Curiosity Nano bridge).

PC --USB CDC (500000 8N1)--> PIC18F16Q20-CNANO --SPI--> TXS0108E --> flash
Flash: MX25S1633F / GD25UF16E / W25Q65NE, identified automatically (JEDEC ID + JESD216H SFDP).
Protocol: docs/PROTOCOL.md
"""
import csv
import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import serial
from serial.tools import list_ports

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flashdb  # noqa: E402
import hexfile  # noqa: E402

APP_NAME = "K1V2SPI Programmer"
VERSION = "5.4.0"
BUILD_DATE = "2026-10-29"           # program update date: change together with VERSION and ChangeHistory.md
MCU_NAME = "Microchip PIC18F16Q20"
AUTHOR = "Keynes Hsu"
AUTHOR_EMAIL = "keynes.hsu@microchip.com"
BAUD = 500000
FLASH_SIZE = 0x200000      # default until Auto Detect has identified the part
SECTOR = 0x1000
PAGE = 0x100
PORT_HINTS = ("curiosity", "pic18f16q20", "microchip", "mchp")

# (label, firmware SPEED value). Larger value = slower bit-banged SPI clock.
SPEEDS = [("Max", 0), ("Fast", 1), ("Normal", 2), ("Slow", 8), ("Slower", 20), ("Slowest", 63)]
# (label, SLEW value): 0 = fastest edges, 1 = slew-rate limited
DRIVES = [("Slow edge", 1), ("Fast edge", 0)]   # slew-limited first: TXS0108E rings with fast edges

STATS_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "MX25S1633F_Programmer")
VERIFY_CHUNK = 0x10000      # verify in 64KB pieces: gives percent progress and locates mismatches
# rough datasheet times (s), used only to weight the progress bar
T_SE, T_BE32, T_BE64, T_PAGE, T_VERIFY_BYTE = 0.24, 1.5, 3.0, 0.0055, 6e-6

SR_BITS = flashdb.SR1_MX            # default layout until a device has been identified
VSENSE_ABSENT_MV = 80               # pull-up moved the reading by more than this: pin is floating


class Cancelled(Exception):
    pass


class BridgeError(Exception):
    pass


class Stats:
    """Persistent program success/fail counters (+ CSV history) stored under %APPDATA%."""

    def __init__(self):
        self.path = os.path.join(STATS_DIR, "stats.json")
        self.hist = os.path.join(STATS_DIR, "program_history.csv")
        self.ok = 0
        self.fail = 0
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            self.ok, self.fail = int(d.get("ok", 0)), int(d.get("fail", 0))
        except (OSError, ValueError):
            pass

    def _save(self):
        try:
            os.makedirs(STATS_DIR, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"ok": self.ok, "fail": self.fail}, f)
        except OSError:
            pass

    def record(self, success, fname="", crc=0, seconds=0.0, note=""):
        if success:
            self.ok += 1
        else:
            self.fail += 1
        self._save()
        try:
            os.makedirs(STATS_DIR, exist_ok=True)
            new = not os.path.exists(self.hist)
            with open(self.hist, "a", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(["time", "result", "file", "crc32", "seconds", "note"])
                w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), "OK" if success else "FAIL", fname,
                            "%08X" % crc, "%.1f" % seconds, note])
        except OSError:
            pass

    def reset(self):
        self.ok = self.fail = 0
        self._save()

    def text(self):
        return "Program count   OK: %d    FAIL: %d    Total: %d" % (self.ok, self.fail, self.ok + self.fail)

    def parts(self):
        """(Pass, Fail, Total) counters for the coloured labels in the GUI."""
        return self.ok, self.fail, self.ok + self.fail


class Bridge:
    """Thin wrapper over the serial protocol."""

    def __init__(self, port):
        self.ser = serial.Serial(port, BAUD, timeout=1.0, write_timeout=2.0)
        self.cancel = threading.Event()
        self.tap = None  # optional callback(bytes) for the raw monitor

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass

    def _check(self):
        if self.cancel.is_set():
            raise Cancelled()

    def flush(self, idle=0.05, limit=3.0):
        """Discard input until the line has been quiet for `idle` seconds (stale replies after Stop)."""
        end = time.time() + limit
        last = time.time()
        while time.time() < end and time.time() - last < idle:
            self.ser.reset_input_buffer()
            if self.ser.read(1):
                last = time.time()
            else:
                time.sleep(0.01)

    def readline(self, timeout=2.0):
        end = time.time() + timeout
        buf = bytearray()
        while time.time() < end:
            self._check()
            c = self.ser.read(1)
            if not c:
                continue
            if c == b"\n":
                s = buf.decode("ascii", "replace").strip()
                if self.tap:
                    self.tap(("<- " + s + "\n").encode())
                return s
            buf += c
        raise BridgeError("timeout (no response)")

    def cmd(self, text, timeout=2.0):
        self._check()
        if self.tap:
            self.tap(("-> " + text + "\n").encode())
        self.ser.write(text.encode("ascii") + b"\n")
        resp = self.readline(timeout)
        if resp.startswith("ERR"):
            raise BridgeError("%s -> %s" % (text, resp))
        return resp

    def read_exact(self, n, timeout=5.0):
        buf = bytearray()
        end = time.time() + timeout
        while len(buf) < n:
            self._check()
            chunk = self.ser.read(n - len(buf))
            if chunk:
                buf += chunk
                end = time.time() + timeout
            elif time.time() > end:
                raise BridgeError("timeout reading data (%d/%d)" % (len(buf), n))
        return bytes(buf)

    # ---- flash operations
    def read_id(self):
        return self.cmd("ID")[3:].strip()

    def read_id_bytes(self):
        return tuple(int(x, 16) for x in self.read_id().split())

    def read_sfdp(self, addr=0, length=256):
        """JESD216 Read SFDP (5Ah); the bridge sends the 3 address bytes and the 8 dummy clocks."""
        self.cmd("SFDP %X %X" % (addr, length))
        return self.read_exact(length)

    def read_vio(self):
        """VSENSE pin (1.2 V rail) in mV vs the on-chip 2.048 V FVR: (plain, with weak pull-up).
        A pin tied to a rail reads the same both ways; a floating pin follows the pull-up."""
        a, b = self.cmd("VIO")[4:].split()
        return int(a, 16), int(b, 16)

    def set_vcheck(self, on):
        self.cmd("VCHK %d" % (1 if on else 0))

    def read_sr(self):
        return int(self.cmd("RDSR")[3:], 16)

    def read_sr2(self):
        return int(self.cmd("RDSR2")[4:], 16)

    def write_sr(self, sr1, sr2=None):
        self.cmd("WRSR %X" % sr1 if sr2 is None else "WRSR %X %X" % (sr1, sr2))

    def read_cr(self):
        return int(self.cmd("RDCR")[3:], 16)

    def read(self, addr, length, progress=None):
        out = bytearray()
        while length:
            n = min(length, 4096)
            self.cmd("READ %X %X" % (addr, n))
            out += self.read_exact(n)
            addr += n
            length -= n
            if progress:
                progress(len(out))
        return bytes(out)

    def crc(self, addr, length):
        # bit-banged SPI + software CRC on the MCU: budget ~150 us/byte, min 10 s
        return int(self.cmd("CRC %X %X" % (addr, length), timeout=10 + length * 150e-6 * 2)[4:], 16)

    def write_page(self, addr, data):
        """Pipelined page program: command + data in one write, no RDY handshake. The MCU answers OK
        once the page program has *started*, so the next page is transferred while the flash works."""
        last = None
        for _ in range(3):
            self._check()
            line = "PW %X %X" % (addr, len(data))
            if self.tap:
                self.tap(("-> " + line + " [+%d bytes]\n" % len(data)).encode())
            self.ser.write(line.encode("ascii") + b"\n" + data)
            r = self.readline(3.0)
            if r.startswith("OK"):
                return
            last = r
            if "ovf" not in r:
                break
            self.flush(0.1)
        raise BridgeError("PW %06X -> %s" % (addr, last))

    def program_page(self, addr, data):
        self.cmd("PP %X %X" % (addr, len(data)))  # replies RDY
        self.ser.write(data)
        end = time.time() + 2
        while True:
            r = self.readline(max(0.1, end - time.time()))
            if r.startswith("ERR"):
                raise BridgeError("PP %06X -> %s" % (addr, r))
            if r.startswith("OK"):
                return


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("%s v%s" % (APP_NAME, VERSION))
        self.minsize(940, 150)
        self.bridge = None
        self.fw_start = 0
        self.fw_data = None
        self.q = queue.Queue()
        self.busy = False
        self.raw_win = None
        self.raw_text = None
        self.flash = None            # flashdb.identify() result once Auto Detect has run
        self.vio = ("unknown", 0)    # (state, mV): state = ok | bad | absent | unknown
        self.custom_file = flashdb.custom_path(STATS_DIR)
        _, custom_errors = flashdb.load_custom(self.custom_file)
        self.bridge_info = None              # (board, firmware version) reported by INFO once connected
        self.about_win = None
        self.sup_win = self.sup_tv = None    # Supported SPI Flash window / its list
        self.sup_sel = None                  # JEDEC iid of the detected part
        self.log_shown = False               # the log is collapsed until its button is clicked
        self.log_new_err = False
        self._build()
        self.refresh_ports()
        self.after(50, self._pump)
        self.after(300, self._auto_connect)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.log("Programmer GUI v%s. Bridge firmware: not connected yet." % VERSION)
        self.log("Ready. Board: PIC18F16Q20 Curiosity Nano (USB CDC, 500000 bps).")
        self.log("HW: TXS0108E VCCA=1.2V (A side -> flash), VCCB=3.3V (B side -> Nano VTG).")
        self.log("Supported SPI flash (auto detected by JEDEC ID + SFDP):")
        for ln in flashdb.supported_lines():
            self.log("  " + ln)
        for e in custom_errors:
            self.log("Custom flash ignored: " + e, "err")

    # ------------------------------------------------------------- layout
    def _build(self):
        bold = ("Segoe UI", 10, "bold")
        top = ttk.Frame(self, padding=(4, 4, 4, 0))
        top.pack(fill="x")
        top.columnconfigure(6, weight=1)
        ttk.Label(top, text="Port:").grid(row=0, column=0, sticky="w")
        self.port_var = tk.StringVar()
        self.port_cb = ttk.Combobox(top, textvariable=self.port_var, width=22, state="readonly")
        self.port_cb.grid(row=0, column=1, padx=4)
        ttk.Button(top, text="↻", width=3, command=self.refresh_ports).grid(row=0, column=2)
        self.btn_conn = ttk.Button(top, text="Connect", command=self.toggle_connect)
        self.btn_conn.grid(row=0, column=3, padx=6)
        ttk.Button(top, text="Raw Monitor", command=self.open_raw).grid(row=0, column=4)
        self.conn_lbl = tk.Label(top, text="● Disconnected", fg="#c00000", font=bold)
        self.conn_lbl.grid(row=0, column=5, padx=10)
        self.chip_lbl = tk.Label(top, text="Flash: not detected", fg="#666", font=bold)
        self.chip_lbl.grid(row=1, column=0, columnspan=4, sticky="w", pady=(4, 0))
        self.vio_lbl = tk.Label(top, text="IO voltage: --", fg="#666", font=bold)
        self.vio_lbl.grid(row=1, column=4, columnspan=2, sticky="w", pady=(4, 0))
        self.ver_lbl = tk.Label(top, text=self.version_text(None), fg="#333", font=("Segoe UI", 10))
        self.ver_lbl.grid(row=2, column=0, columnspan=6, sticky="w", pady=(2, 0))
        # program count: top right corner of the window
        sc = ttk.Frame(top)
        sc.grid(row=0, column=7, rowspan=3, sticky="ne", padx=(8, 0))
        self.stats = Stats()
        sl = ttk.Frame(sc)
        sl.pack(anchor="e")
        ttk.Label(sl, text="Program count", font=bold).pack(side="left", padx=(0, 8))
        self.stat_lbls = []
        for title, color in (("Pass", "#0a7a2a"), ("Fail", "#c00000"), ("Total", "#000000")):
            lb = tk.Label(sl, text="%s: 0" % title, fg=color, font=bold)
            lb.pack(side="left", padx=(0, 8))
            self.stat_lbls.append((title, lb))
        self.update_stats_labels()
        sb2 = ttk.Frame(sc)
        sb2.pack(anchor="e", pady=(2, 0))
        ttk.Button(sb2, text="Reset count", command=self.reset_stats).pack(side="left", padx=(0, 4))
        ttk.Button(sb2, text="Open history", command=self.open_history).pack(side="left")

        row2 = ttk.Frame(self, padding=(4, 4, 4, 0))
        row2.pack(fill="x")
        ttk.Button(row2, text="About", command=self.open_about).pack(side="right", padx=(6, 0))
        ttk.Button(row2, text="Supported SPI Flash…", command=self.open_supported).pack(side="right")
        ttk.Label(row2, text="SPI clock:").pack(side="left")
        self.speed_var = tk.StringVar(value="Normal")
        cb = ttk.Combobox(row2, textvariable=self.speed_var, width=9, state="readonly",
                          values=[s[0] for s in SPEEDS])
        cb.pack(side="left", padx=(2, 10))
        cb.bind("<<ComboboxSelected>>", lambda e: self.apply_link_settings())
        ttk.Label(row2, text="Pin drive:").pack(side="left")
        self.drive_var = tk.StringVar(value="Slow edge")
        cb2 = ttk.Combobox(row2, textvariable=self.drive_var, width=10, state="readonly",
                           values=[d[0] for d in DRIVES])
        cb2.pack(side="left", padx=(2, 10))
        cb2.bind("<<ComboboxSelected>>", lambda e: self.apply_link_settings())
        self.wp_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row2, text="WP# High", variable=self.wp_var,
                        command=self.apply_link_settings).pack(side="left")
        self.novs_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2, text="Ignore VSENSE", variable=self.novs_var).pack(side="left", padx=8)
        ttk.Label(row2, text="(Link Test finds the fastest stable SPI clock / pin drive)",
                  foreground="#666").pack(side="left")

        ff = ttk.LabelFrame(self, text="Firmware File", padding=4)
        ff.pack(fill="x", padx=4, pady=4)
        ttk.Button(ff, text="\U0001F4C2 Load File…", command=self.load_file).pack(side="left")
        self.file_lbl = ttk.Label(ff, text="No file loaded.", foreground="#555")
        self.file_lbl.pack(side="left", padx=8)
        self.chip_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(ff, text="Chip Erase first if file > half the flash (erases ALL data, fastest)",
                        variable=self.chip_var).pack(side="right")

        # Commands: 7 equal columns; row 1 = device / link commands, row 2 = flash commands + Stop
        cf = ttk.LabelFrame(self, text="Commands", padding=4)
        cf.pack(fill="x", padx=4)
        self.cmd_buttons = []
        cmds = [
            ("\U0001F50E Auto Detect", self.do_auto_detect), ("\U0001F50D Read ID", self.do_read_id),
            ("\U0001F4CB Read SR", self.do_read_sr), ("⚙ Config SR", self.do_config_sr),
            ("\U0001F4F6 Link Test", self.do_link_test), ("\U0001F4C4 Hex Dump", self.do_hexdump),
            ("\U0001F501 Reset", self.do_reset),
            ("\U0001F9F9 Sector Erase", self.do_sector_erase), ("\U0001F5D1 Chip Erase", self.do_chip_erase),
            ("\U0001F4E5 Program", self.do_program), ("✅ Verify", self.do_verify),
            ("\U0001F4BE Read->File", self.do_read_file),
        ]
        for c in range(7):
            cf.columnconfigure(c, weight=1, uniform="cmd")
        for i, (t, fn) in enumerate(cmds):
            b = ttk.Button(cf, text=t, command=lambda f=fn: self.run(f))
            b.grid(row=i // 7, column=i % 7, padx=3, pady=3, ipady=4, sticky="ew")
            self.cmd_buttons.append(b)
        self.btn_stop = ttk.Button(cf, text="■ Stop", command=self.stop, state="disabled")
        self.btn_stop.grid(row=1, column=5, columnspan=2, padx=3, pady=3, ipady=4, sticky="ew")

        pf = ttk.Frame(self, padding=(4, 4, 4, 0))
        pf.pack(fill="x")
        ttk.Label(pf, text="Address (hex):").pack(side="left")
        self.addr_var = tk.StringVar(value="000000")
        ttk.Entry(pf, textvariable=self.addr_var, width=9).pack(side="left", padx=(2, 12))
        ttk.Label(pf, text="Length (hex):").pack(side="left")
        self.len_var = tk.StringVar(value="200000")   # whole flash; Auto Detect sets it to the detected size
        ttk.Entry(pf, textvariable=self.len_var, width=9).pack(side="left", padx=(2, 12))
        self.verify_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(pf, text="Verify after program", variable=self.verify_var).pack(side="left", padx=6)
        self.dbl_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(pf, text="Double-check Read->File (CRC on board)",
                        variable=self.dbl_var).pack(side="left", padx=6)

        # compact status: state + message + percent on one line, a thin progress bar below
        sf = tk.Frame(self, bg="#e9eef3", bd=1, relief="solid")
        sf.pack(fill="x", padx=4, pady=4)
        line = tk.Frame(sf, bg="#e9eef3")
        line.pack(fill="x", padx=8, pady=(2, 0))
        self.pct_lbl = tk.Label(line, text="0%", width=5, anchor="e", bg="#e9eef3", font=("Segoe UI", 10, "bold"))
        self.pct_lbl.pack(side="right")
        self.state_lbl = tk.Label(line, text="IDLE  待機", bg="#e9eef3", anchor="w",
                                  font=("Segoe UI", 10, "bold"), fg="#444")
        self.state_lbl.pack(side="left")
        self.msg_lbl = tk.Label(line, text="Load a file, Connect, then run a command.", bg="#e9eef3",
                                anchor="w", fg="#333")
        self.msg_lbl.pack(side="left", fill="x", expand=True, padx=(10, 0))
        ttk.Style(self).configure("Slim.Horizontal.TProgressbar", thickness=6)
        self.prog = ttk.Progressbar(sf, maximum=100, style="Slim.Horizontal.TProgressbar")
        self.prog.pack(fill="x", padx=8, pady=(1, 4))

        # the log stays hidden until its button is clicked
        lh = ttk.Frame(self, padding=(4, 0, 4, 2))
        lh.pack(fill="x")
        self.log_btn = ttk.Button(lh, text="▶ Show Log", command=self.toggle_log)
        self.log_btn.pack(side="left")
        ttk.Label(lh, text="LED0 (yellow, RC7): on = command running",
                  foreground="#666").pack(side="left", padx=10)
        self.log_frame = ttk.LabelFrame(self, text="Log", padding=2)
        self.log_text = tk.Text(self.log_frame, height=16, bg="#10141a", fg="#9be39b", insertbackground="white",
                                font=("Consolas", 10), state="disabled", wrap="word")
        sb = ttk.Scrollbar(self.log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log_text.pack(fill="both", expand=True)
        self.log_text.tag_configure("err", foreground="#ff7b7b")
        self.log_text.tag_configure("ok", foreground="#7bff9b")
        self._set_enabled(False)

    def place_right(self, win):
        """Show a pop-up window to the right of the main window (top-aligned, cascaded if others are open).
        Falls back to overlapping the main window's right edge if the screen is too narrow."""
        self.update_idletasks()
        win.update_idletasks()
        n = sum(1 for w in self.winfo_children() if isinstance(w, tk.Toplevel) and w is not win and w.winfo_viewable())
        x = self.winfo_rootx() + self.winfo_width() + 8
        y = self.winfo_rooty() + 32 * n
        x = max(0, min(x, self.winfo_screenwidth() - win.winfo_reqwidth()))
        y = max(0, min(y, self.winfo_screenheight() - win.winfo_reqheight() - 40))
        win.geometry("+%d+%d" % (x, y))

    def about_lines(self):
        """(label, value) rows of the About window."""
        if self.bridge_info:
            fw = "%s  (board %s)" % (self.bridge_info[1], self.bridge_info[0])
        else:
            fw = "not connected"
        return [
            ("Program", APP_NAME),
            ("GUI version", "v%s" % VERSION),
            ("Program updated", BUILD_DATE),
            ("MCU", MCU_NAME),
            ("MCU firmware version", fw),
            ("Designer", AUTHOR),
            ("Email", AUTHOR_EMAIL),
        ]

    def open_about(self):
        if self.about_win and self.about_win.winfo_exists():
            self.about_win.destroy()          # re-open to refresh the firmware version
        win = self.about_win = tk.Toplevel(self)
        win.title("About " + APP_NAME)
        win.transient(self)
        win.resizable(False, False)
        win.withdraw()
        ttk.Label(win, text=APP_NAME, font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 0))
        ttk.Label(win, text="1.2 V SPI-NOR flash programmer (USB bridge on a Curiosity Nano)",
                  foreground="#666").grid(row=1, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 8))
        for r, (k, v) in enumerate(self.about_lines(), start=2):
            ttk.Label(win, text=k + ":", font=("Segoe UI", 10, "bold")).grid(row=r, column=0, sticky="nw",
                                                                           padx=(14, 8), pady=1)
            ttk.Label(win, text=v).grid(row=r, column=1, sticky="w", padx=(0, 14), pady=1)
        ttk.Button(win, text="Close", command=win.destroy).grid(row=20, column=0, columnspan=2, pady=12)
        self.place_right(win)
        win.deiconify()

    def toggle_log(self):
        self.log_shown = not self.log_shown
        if self.log_shown:
            self.log_new_err = False
            self.log_frame.pack(fill="both", expand=True, padx=4, pady=(0, 4))
            self.log_text.see("end")
        else:
            self.log_frame.pack_forget()
        self.update_log_btn()
        self.geometry("")                 # re-fit the window to the new content

    def update_log_btn(self):
        if self.log_shown:
            self.log_btn.configure(text="▼ Hide Log")
        else:
            self.log_btn.configure(text="▶ Show Log" + ("   ⚠ new error" if self.log_new_err else ""))

    def open_supported(self):
        """Supported SPI Flash list in its own window (the detected part is highlighted)."""
        if self.sup_win and self.sup_win.winfo_exists():
            self.sup_win.lift()
            return
        win = self.sup_win = tk.Toplevel(self)
        win.title("Supported SPI Flash")
        win.transient(self)
        win.withdraw()
        cols = ("vendor", "part", "id", "size", "vcc")
        tv = self.sup_tv = ttk.Treeview(win, columns=cols, show="headings", height=len(flashdb.KNOWN))
        for c, title, w in zip(cols, ("Vendor", "Part", "JEDEC ID", "Density", "VCC"), (110, 130, 100, 90, 110)):
            tv.heading(c, text=title)
            tv.column(c, width=w, anchor="w")
        tv.tag_configure("custom", foreground="#0b5cad")
        tv.pack(fill="both", expand=True, padx=8, pady=8)
        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(bar, text="Highlighted = detected part.  Blue * = custom (custom_flash.json).",
                  foreground="#777").pack(side="left")
        ttk.Button(bar, text="Close", command=win.destroy).pack(side="right")
        ttk.Button(bar, text="Custom Flash…", command=self.open_custom).pack(side="right", padx=6)
        win.bind("<Destroy>", lambda e: setattr(self, "sup_tv", None) if e.widget is win else None)
        self.fill_supported()
        self.place_right(win)
        win.deiconify()

    def set_supported_sel(self, iid):
        self.sup_sel = iid
        tv = self.sup_tv
        if tv is not None:
            tv.selection_set([iid] if iid and tv.exists(iid) else [])

    def fill_supported(self):
        tv = self.sup_tv
        if tv is None:
            return
        tv.delete(*tv.get_children())
        tv.configure(height=len(flashdb.KNOWN))
        for i in flashdb.KNOWN.values():
            tv.insert("", "end", iid="%02X%02X%02X" % i.jedec, tags=("custom",) if i.custom else (),
                      values=(i.vendor, i.part + (" *" if i.custom else ""), "%02X %02X %02X" % i.jedec,
                              flashdb.density_text(i), "%.2f-%.2f V" % i.voltage))
        self.set_supported_sel(self.sup_sel)

    def reload_custom(self):
        """Re-read custom_flash.json; the flash is forgotten so the next command re-detects with the new data."""
        self.custom_file = flashdb.custom_path(STATS_DIR)
        _, errors = flashdb.load_custom(self.custom_file)
        self.fill_supported()
        self.flash = None
        for e in errors:
            self.log("Custom flash ignored: " + e, "err")
        return errors

    def open_custom(self):
        """Custom Flash dialog: add / edit / delete user-defined SPI-NOR parts (custom_flash.json)."""
        if getattr(self, "custom_win", None) and self.custom_win.winfo_exists():
            self.custom_win.lift()
            return
        try:
            items = flashdb.read_custom_raw(self.custom_file)
        except ValueError as e:
            messagebox.showerror("Custom Flash", str(e))
            return
        dlg = self.custom_win = tk.Toplevel(self)
        dlg.title("Custom SPI Flash  (custom_flash.json)")
        dlg.transient(self)
        dlg.withdraw()
        dlg.resizable(False, False)
        ttk.Label(dlg, text="Add a 1.2 V SPI-NOR that is not in the list. Density, page size and erase sizes are "
                            "read from the chip's SFDP.\nThe bridge always uses 3-byte addresses, 256 B pages, "
                            "4 KB erase (20h) and the %.2f-%.2f V window." %
                  (flashdb.VIO_MIN_MV / 1000.0, flashdb.VIO_MAX_MV / 1000.0),
                  justify="left").grid(row=0, column=0, columnspan=4, sticky="w", padx=8, pady=(8, 4))
        cols = ("vendor", "part", "id")
        tv = ttk.Treeview(dlg, columns=cols, show="headings", height=5, selectmode="browse")
        for c, t, w in zip(cols, ("Vendor", "Part", "JEDEC ID"), (130, 150, 100)):
            tv.heading(c, text=t)
            tv.column(c, width=w)
        tv.grid(row=1, column=0, columnspan=4, sticky="ew", padx=8)
        fields = [
            ("vendor", "Vendor *", ""), ("part", "Part *", ""), ("jedec", "JEDEC ID (hex) *", "EF 65 18"),
            ("chip_erase_s", "Chip erase max (s) *", "60"), ("size_mbit", "Density (Mbit, optional check)", ""),
            ("sr_bits", "SR1 writable bits", "BP2=4, BP1=3, BP0=2"), ("sr_mask", "SR1 readback mask", ""),
            ("vcc", "VCC min-max (V)", "1.14-1.26"),
        ]
        vars_ = {}
        for r, (key, label, hint) in enumerate(fields):
            ttk.Label(dlg, text=label).grid(row=2 + r, column=0, sticky="w", padx=8, pady=2)
            vars_[key] = tk.StringVar()
            ttk.Entry(dlg, textvariable=vars_[key], width=26).grid(row=2 + r, column=1, sticky="w", pady=2)
            ttk.Label(dlg, text=("e.g. " + hint) if hint else "", foreground="#777").grid(
                row=2 + r, column=2, columnspan=2, sticky="w", padx=6)
        sr2 = tk.BooleanVar(value=False)
        ttk.Checkbutton(dlg, text="Has Status Register 2 (WRSR must rewrite SR2: Winbond / GigaDevice style)",
                        variable=sr2).grid(row=2 + len(fields), column=0, columnspan=4, sticky="w", padx=8)
        ttk.Label(dlg, text="* required. Bits 0/1 (WIP/WEL) cannot be listed. Mask empty = all listed bits.",
                  foreground="#777").grid(row=3 + len(fields), column=0, columnspan=4, sticky="w", padx=8)

        def entry_dict():
            v = {k: x.get().strip() for k, x in vars_.items()}
            d = {"vendor": v["vendor"], "part": v["part"], "jedec": v["jedec"], "chip_erase_s": v["chip_erase_s"],
                 "has_sr2": sr2.get()}
            if v["size_mbit"]:
                d["size_mbit"] = v["size_mbit"]
            if v["sr_bits"]:
                d["sr_bits"] = flashdb.parse_sr_text(v["sr_bits"])
            if v["sr_mask"]:
                d["sr_mask"] = v["sr_mask"]
            if v["vcc"]:
                lo, sep, hi = v["vcc"].partition("-")
                if not sep:
                    raise ValueError("VCC: use min-max, e.g. 1.14-1.26")
                d["vcc_min"], d["vcc_max"] = lo.strip(), hi.strip()
            return d

        def refresh_list():
            tv.delete(*tv.get_children())
            for n, d in enumerate(items):
                tv.insert("", "end", iid=str(n), values=(d.get("vendor", ""), d.get("part", ""), d.get("jedec", "")))

        def fill(d):
            for k in vars_:
                vars_[k].set("")
            for k in ("vendor", "part", "jedec", "chip_erase_s", "size_mbit", "sr_mask"):
                vars_[k].set(str(d.get(k, "")))
            vars_["sr_bits"].set(flashdb.sr_text(d.get("sr_bits")))
            if "vcc_min" in d or "vcc_max" in d:
                vars_["vcc"].set("%s-%s" % (d.get("vcc_min", ""), d.get("vcc_max", "")))
            sr2.set(bool(d.get("has_sr2")))

        def on_select(_e=None):
            sel = tv.selection()
            if sel:
                fill(items[int(sel[0])])

        def commit(new_items):
            try:
                flashdb.save_custom(self.custom_file, new_items)
            except (ValueError, OSError) as e:
                messagebox.showerror("Custom Flash", str(e), parent=dlg)
                return False
            items[:] = new_items
            refresh_list()
            self.reload_custom()
            return True

        def same_id(x, jid):
            try:
                return flashdb.parse_jedec(x.get("jedec", "")) == jid
            except ValueError:
                return False

        def save():
            try:
                d = entry_dict()
                info = flashdb.entry_to_info(d)
            except ValueError as e:
                messagebox.showerror("Custom Flash", str(e), parent=dlg)
                return
            new = [x for x in items if not same_id(x, info.jedec)]
            d["jedec"] = "%02X %02X %02X" % info.jedec
            new.append(d)
            if commit(new):
                self.log("Custom flash saved: %s %s (%02X %02X %02X). Run Auto Detect." %
                         ((info.vendor, info.part) + info.jedec), "ok")

        def delete():
            sel = tv.selection()
            if sel and messagebox.askyesno("Custom Flash", "Delete this entry?", parent=dlg):
                commit([x for n, x in enumerate(items) if str(n) != sel[0]])

        def from_detected():
            f = self.flash
            if not f or f["known"]:
                messagebox.showinfo("Custom Flash", "Run Auto Detect with the unlisted flash connected first.",
                                    parent=dlg)
                return
            fill({"jedec": "%02X %02X %02X" % f["jedec"], "vendor": f["vendor"].split(" (")[0]})
            if f["sfdp"]:
                vars_["size_mbit"].set(str(f["sfdp"]["density_bits"] >> 20))
            vars_["sr_bits"].set(flashdb.sr_text({"BP2": 4, "BP1": 3, "BP0": 2}))
            vars_["vcc"].set("1.14-1.26")

        def open_folder():
            os.makedirs(os.path.dirname(self.custom_file), exist_ok=True)
            if not os.path.isfile(self.custom_file):
                flashdb.save_custom(self.custom_file, items)
            if hasattr(os, "startfile"):
                os.startfile(os.path.dirname(self.custom_file))

        tv.bind("<<TreeviewSelect>>", on_select)
        bf = ttk.Frame(dlg)
        bf.grid(row=4 + len(fields), column=0, columnspan=4, pady=8)
        for t, c in (("Use detected flash", from_detected), ("Save / Update", save), ("Delete", delete),
                     ("Open folder", open_folder), ("Close", dlg.destroy)):
            ttk.Button(bf, text=t, command=c).pack(side="left", padx=4)
        ttk.Label(dlg, text="File: " + self.custom_file, foreground="#777").grid(
            row=5 + len(fields), column=0, columnspan=4, sticky="w", padx=8, pady=(0, 8))
        refresh_list()
        self.place_right(dlg)
        dlg.deiconify()

    # ------------------------------------------------------------- helpers
    def _pump(self):
        try:
            while True:
                kind, a, b = self.q.get_nowait()
                if kind == "log":
                    self.log_text.configure(state="normal")
                    self.log_text.insert("end", a + "\n", b or ())
                    self.log_text.see("end")
                    self.log_text.configure(state="disabled")
                    if b == "err" and not self.log_shown and not self.log_new_err:
                        self.log_new_err = True
                        self.update_log_btn()
                elif kind == "state":
                    self.state_lbl.configure(text=a[0], fg=a[1])
                    if a[2] is not None:
                        self.msg_lbl.configure(text=a[2])
                elif kind == "prog":
                    self.prog["value"] = a
                    self.pct_lbl.configure(text="%d%%" % int(a))
                elif kind == "chip":
                    self.chip_lbl.configure(text=a[0], fg=a[1])
                elif kind == "ver":
                    self.ver_lbl.configure(text=a)
                elif kind == "sel":            # highlight the detected part in the Supported list
                    self.set_supported_sel(a)
                elif kind == "vio":
                    self.vio_lbl.configure(text=a[0], fg=a[1])
                elif kind == "len":
                    self.len_var.set(a)
                elif kind == "stats":
                    self.update_stats_labels()
                elif kind == "done":
                    self.busy = False
                    self._set_enabled(self.bridge is not None)
                elif kind == "raw" and self.raw_text is not None:
                    self.raw_text.configure(state="normal")
                    self.raw_text.insert("end", a.decode("ascii", "replace"))
                    self.raw_text.see("end")
                    self.raw_text.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(50, self._pump)

    def log(self, s, tag=None):
        self.q.put(("log", s, tag))

    def set_state(self, name, color, msg=None):
        self.q.put(("state", (name, color, msg), None))

    def set_prog(self, pct):
        self.q.put(("prog", max(0, min(100, pct)), None))

    def update_stats_labels(self):
        for (title, lb), n in zip(self.stat_lbls, self.stats.parts()):
            lb.configure(text="%s: %d" % (title, n))

    def reset_stats(self):
        if messagebox.askyesno("Reset count", "Reset the OK / FAIL counters to zero?"):
            self.stats.reset()
            self.q.put(("stats", None, None))

    def open_history(self):
        if os.path.exists(self.stats.hist):
            os.startfile(self.stats.hist)
        else:
            messagebox.showinfo("History", "No program history yet.")

    def _set_enabled(self, conn):
        for b in self.cmd_buttons:
            b.configure(state="normal" if conn and not self.busy else "disabled")
        self.btn_stop.configure(state="normal" if self.busy else "disabled")
        self.btn_conn.configure(state="disabled" if self.busy else "normal")

    def refresh_ports(self):
        ports = list(list_ports.comports())
        names = []
        best = None
        for p in ports:
            label = "%s - %s" % (p.device, p.description)
            names.append(label)
            # The Nano debugger CDC shows up as "USB Serial Device" with Microchip VID 03EB
            is_nano = (p.vid == 0x03EB) or any(h in (p.description or "").lower() for h in PORT_HINTS)
            if best is None and is_nano:
                best = label
        self.port_cb["values"] = names
        if best:
            self.port_var.set(best)
        elif names and not self.port_var.get():
            self.port_var.set(names[0])

    def parse_hex(self, var, name):
        try:
            return int(var.get().strip().replace("0x", ""), 16)
        except ValueError:
            raise BridgeError("%s is not a hex number" % name)

    # ---------------------------------------------------------- connection
    def _auto_connect(self):
        """Connect automatically when exactly one Microchip (VID 03EB) port is present."""
        nanos = [p for p in list_ports.comports() if p.vid == 0x03EB]
        if len(nanos) == 1 and not self.bridge:
            self.port_var.set("%s - %s" % (nanos[0].device, nanos[0].description))
            self.toggle_connect()

    def toggle_connect(self):
        if self.bridge:
            self.bridge.close()
            self.bridge = None
            self.conn_lbl.configure(text="● Disconnected", fg="#c00000")
            self.btn_conn.configure(text="Connect")
            self._set_enabled(False)
            self.log("Disconnected.")
            self.ver_lbl.configure(text=self.version_text(None))
            self.bridge_info = None
            self.set_supported_sel(None)
            return
        sel = self.port_var.get()
        if not sel:
            messagebox.showwarning("Port", "Select a COM port first (Curiosity Virtual COM Port).")
            return
        port = sel.split(" - ")[0]
        try:
            self.bridge = Bridge(port)
            self.bridge.tap = lambda b: self.q.put(("raw", b, None))
        except Exception as e:
            self.bridge = None
            messagebox.showerror("Connect", str(e))
            return
        self.conn_lbl.configure(text="● Connected", fg="#0a7a2a")
        self.btn_conn.configure(text="Disconnect")
        self._set_enabled(True)
        self.run(self.do_connect_check)

    @staticmethod
    def parse_info(reply):
        """'OK PIC18F16Q20-CNANO SPINOR-BRIDGE 5.1.0' -> ('PIC18F16Q20-CNANO', '5.1.0').
        Older firmware says MX25S1633F-BRIDGE; anything unexpected is returned as-is in the board field."""
        parts = reply.split()
        if len(parts) >= 4 and parts[0] == "OK" and parts[2].endswith("-BRIDGE"):
            return parts[1], parts[3]
        return reply, "?"

    @staticmethod
    def version_text(info):
        """info = (board, firmware version) from the bridge, or None when not connected."""
        bridge = "%s  firmware %s" % info if info else "not connected"
        return "Programmer GUI v%s    |    Bridge: %s" % (VERSION, bridge)

    def do_connect_check(self):
        b = self.bridge
        b.flush()
        b.cmd("PING")
        board, fw = self.parse_info(b.cmd("INFO"))
        self.bridge_info = (board, fw)
        self.q.put(("ver", self.version_text((board, fw)), None))
        self.log("Bridge alive. Board %s, firmware %s; Programmer GUI v%s." % (board, fw, VERSION), "ok")
        self.apply_link_settings_now()
        self.detect_flash()

    def apply_link_settings(self):
        if self.bridge and not self.busy:
            self.run(self.apply_link_settings_now)

    def apply_link_settings_now(self):
        b = self.bridge
        sp = dict(SPEEDS)[self.speed_var.get()]
        dr = dict(DRIVES)[self.drive_var.get()]
        b.cmd("SPEED %X" % sp)
        b.cmd("SLEW %X" % dr)
        b.cmd("WP %d" % (1 if self.wp_var.get() else 0))
        self.log("Link: SPI clock=%s, pin drive=%s, WP#=%s" %
                 (self.speed_var.get(), self.drive_var.get(), "High" if self.wp_var.get() else "Low"))

    # ------------------------------------------------- voltage + flash detect
    @staticmethod
    def mv_text(mv):
        return "%.3f V" % (mv / 1000.0)

    def check_vio(self):
        """Measure the 1.2 V rail on VSENSE and arm/disarm the firmware interlock (VCHK).
        Highest priority: anything but 1.14-1.26 V disables every program/erase/WRSR."""
        b = self.bridge
        if self.novs_var.get():
            b.set_vcheck(False)
            self.vio = ("absent", 0)
            self.q.put(("vio", ("IO voltage: check OFF (VSENSE ignored)", "#b36b00"), None))
            return self.vio
        mv, mv_pu = b.read_vio()
        if mv_pu - mv > VSENSE_ABSENT_MV:
            b.set_vcheck(False)
            self.vio = ("absent", mv)
            self.q.put(("vio", ("IO voltage: VSENSE not wired", "#b36b00"), None))
            return self.vio
        b.set_vcheck(True)
        ok = flashdb.VIO_MIN_MV <= mv <= flashdb.VIO_MAX_MV
        self.vio = ("ok" if ok else "bad", mv)
        self.q.put(("vio", ("IO voltage: %s %s" % (self.mv_text(mv), "OK (1.2 V)" if ok else "OUT OF RANGE"),
                            "#0a7a2a" if ok else "#c00000"), None))
        return self.vio

    def detect_flash(self):
        """Auto Detect: voltage interlock, JEDEC ID (9Fh), then SFDP (5Ah) for density/page/erase info."""
        b = self.bridge
        self.flash = None
        state, mv = self.check_vio()
        if state == "bad":
            self.log("IO voltage %s is outside %.2f-%.2f V: programming is DISABLED (1.2 V required)." %
                     (self.mv_text(mv), flashdb.VIO_MIN_MV / 1000.0, flashdb.VIO_MAX_MV / 1000.0), "err")
        elif state == "absent":
            self.log("1.2 V check is off (VSENSE not wired / ignored): relying on ID + SFDP only.", "err")
        try:
            b.cmd("RDP")              # ABh: wake the flash if it was left in Deep Power-Down
        except BridgeError:
            pass                      # bridge firmware < 5.1.0 has no RDP command
        jid = b.read_id_bytes()
        self.log("JEDEC ID: %02X %02X %02X" % jid)
        dead = jid in ((0, 0, 0), (0xFF, 0xFF, 0xFF))
        sfdp, err = None, ""
        if not dead:
            for _ in range(3):
                try:
                    sfdp = flashdb.parse_sfdp(b.read_sfdp(0, 256))
                    break
                except flashdb.SfdpError as e:
                    err = str(e)
        res = flashdb.identify(jid, sfdp)
        if dead:
            res["blockers"].insert(0, "no response from flash (ID %02X %02X %02X): check 1.2 V, OE, wiring" % jid)
        if state == "bad":
            res["blockers"].insert(0, "IO voltage %s is not 1.2 V" % self.mv_text(mv))
        if sfdp and not res["known"] and not dead:
            # not a listed part: show what the device itself reports, field by field (JESD216H)
            self.log("Unlisted device - decoded from SFDP: %s" % res["name"], "err")
            for ln in res["sfdp_lines"]:
                self.log("  " + ln)
        elif sfdp:
            self.log("SFDP: JESD216 rev %d.%d, %d parameter header(s), %d Mbit, %s-byte address, page %d B, "
                     "erase %s" % (sfdp["major"], sfdp["minor"], sfdp["nph"], sfdp["density_bits"] // (1 << 20),
                                   sfdp["addr_bytes"], res["page"],
                                   "/".join("%dK" % (sz // 1024) for sz in res["erase_sizes"]) or "?"))
        elif err:
            self.log("SFDP read failed: " + err, "err")
        for w in res["warnings"]:
            self.log("Warning: " + w, "err")
        self.flash = res
        self.q.put(("sel", "%02X%02X%02X" % res["info"].jedec if res["info"] else None, None))
        if res["blockers"]:
            for r in res["blockers"]:
                self.log("Blocked: " + r, "err")
            if sfdp and not res["known"] and not dead:
                self.q.put(("chip", ("Flash: %s  (SFDP only - not supported, read-only)" % res["name"],
                                     "#b36b00"), None))
                # Hex Dump / Read->File still work; 3-byte addressing reaches 16 MB at most
                self.q.put(("len", "%X" % min(res["size"], 0x1000000), None))
            else:
                self.q.put(("chip", ("Flash: %s  (programming blocked)" % res["name"], "#c00000"), None))
        else:
            self.log("Detected %s %s  %02X %02X %02X  %d Mbit (%d KB)" %
                     (res["vendor"], res["info"].part, jid[0], jid[1], jid[2], res["size"] * 8 // (1 << 20),
                      res["size"] // 1024), "ok")
            self.q.put(("chip", ("Flash: %s  %02X %02X %02X  %d KB" %
                                 (res["name"], jid[0], jid[1], jid[2], res["size"] // 1024), "#0a7a2a"), None))
            self.q.put(("len", "%X" % res["size"], None))
        return res

    def flash_size(self):
        f = getattr(self, "flash", None)
        return min(f["size"], 0x1000000) if f and f["size"] else FLASH_SIZE

    def guard(self):
        """Hard interlock before any program/erase/WRSR: 1.2 V rail and a fully recognised flash.
        The voltage is re-measured every time; the firmware checks it again before each flash write."""
        state, mv = self.check_vio()
        if state == "bad":
            raise BridgeError("IO voltage %s is not 1.2 V (%.2f-%.2f V): programming disabled" %
                              (self.mv_text(mv), flashdb.VIO_MIN_MV / 1000.0, flashdb.VIO_MAX_MV / 1000.0))
        f = getattr(self, "flash", None)
        if f is None or f["blockers"]:
            f = self.detect_flash()
        if f["blockers"]:
            raise BridgeError("programming disabled: " + "; ".join(f["blockers"]))
        return f

    # ------------------------------------------------------- task runner
    def run(self, fn):
        if self.busy or not self.bridge:
            return
        self.busy = True
        self._set_enabled(True)
        self.bridge.cancel.clear()
        self.set_prog(0)
        threading.Thread(target=self._worker, args=(fn,), daemon=True).start()

    def _worker(self, fn):
        name = fn.__name__.replace("do_", "").replace("_", " ").upper()
        self.set_state("RUNNING  執行中", "#b36b00", name)
        t0 = time.time()
        try:
            self.bridge.cmd("LED 1")
        except Exception:
            pass
        try:
            fn()
            self.set_state("DONE  完成", "#0a7a2a", "%s finished in %.1f s" % (name, time.time() - t0))
            self.set_prog(100)
        except Cancelled:
            self.log("Stopped by user.", "err")
            self.set_state("STOPPED  已停止", "#c00000", name)
            try:
                self.bridge.flush(0.4, 4.0)
            except Exception:
                pass
        except Exception as e:
            self.log("[FAIL] %s" % e, "err")
            self.set_state("FAILED  失敗", "#c00000", str(e))
        finally:
            try:
                self.bridge.cancel.clear()
                self.bridge.cmd("LED 0")
            except Exception:
                pass
            self.q.put(("done", None, None))

    def stop(self):
        if self.bridge:
            self.bridge.cancel.set()

    # ------------------------------------------------------------ actions
    def do_auto_detect(self):
        res = self.detect_flash()
        if res["blockers"]:
            raise BridgeError("; ".join(res["blockers"]))

    def do_read_id(self):
        jid = self.bridge.read_id_bytes()
        info = flashdb.KNOWN.get(flashdb.ALIASES.get(jid, jid))
        self.log("ID: %02X %02X %02X  %s" % (jid + (info.name if info else "(not a supported device)",)),
                 "ok" if info else "err")

    def sr_layout(self):
        f = getattr(self, "flash", None)
        return f["info"].sr_bits if f and f["info"] else SR_BITS

    def decode_sr(self, v):
        names = [n for n, bit in self.sr_layout() + [("WEL", 1), ("WIP", 0)] if v & (1 << bit)]
        return "0x%02X  [%s]" % (v, " ".join(names) or "all clear")

    def do_read_sr(self):
        b = self.bridge
        self.log("SR = " + self.decode_sr(b.read_sr()))
        f = getattr(self, "flash", None)
        if f and f["info"] and f["info"].has_sr2:
            self.log("SR2 = 0x%02X" % b.read_sr2())
        else:
            self.log("CR = 0x%02X" % b.read_cr())

    def do_config_sr(self):
        f = self.guard()
        layout = f["info"].sr_bits
        done = threading.Event()
        result = {}
        cur = self.bridge.read_sr()
        cur2 = self.bridge.read_sr2() if f["info"].has_sr2 else None

        def dialog():
            dlg = tk.Toplevel(self)
            dlg.title("Config Status Register")
            dlg.transient(self)
            dlg.withdraw()
            vars_ = {}
            for i, (n, bit) in enumerate(layout):
                v = tk.BooleanVar(value=bool(cur & (1 << bit)))
                vars_[bit] = v
                ttk.Checkbutton(dlg, text="%s (bit %d)" % (n, bit), variable=v,
                                command=lambda: upd()).grid(row=i, column=0, sticky="w", padx=10, pady=2)
            lbl = ttk.Label(dlg, text="")
            lbl.grid(row=0, column=1, rowspan=3, padx=16)

            def val():
                return sum(1 << bit for bit, v in vars_.items() if v.get())

            def upd():
                lbl.configure(text="SR = 0x%02X" % val())

            def default():
                for v in vars_.values():
                    v.set(False)
                upd()

            def ok():
                result["v"] = val()
                dlg.destroy()

            fr = ttk.Frame(dlg)
            fr.grid(row=7, column=0, columnspan=2, pady=8)
            ttk.Button(fr, text="Default", command=default).pack(side="left", padx=4)
            ttk.Button(fr, text="OK", command=ok).pack(side="left", padx=4)
            ttk.Button(fr, text="Cancel", command=dlg.destroy).pack(side="left", padx=4)
            upd()
            dlg.bind("<Destroy>", lambda e: done.set() if e.widget is dlg else None)
            self.place_right(dlg)
            dlg.deiconify()
            dlg.grab_set()

        self.after(0, dialog)
        done.wait()
        if "v" not in result:
            self.log("Config SR cancelled.")
            return
        b = self.bridge
        # GD25UF16E: a 1-byte WRSR clears the writable SR2 bits, so rewrite SR2 unchanged as the 2nd byte
        b.write_sr(result["v"], cur2)
        back = b.read_sr()
        want = result["v"] & f["info"].sr_mask
        if (back & f["info"].sr_mask) == want:
            self.log("SR written: " + self.decode_sr(back), "ok")
        else:
            raise BridgeError("SR readback %s != wanted 0x%02X (SRP/SRWD=1 with WP# low? tick WP# High)" %
                              (self.decode_sr(back), want))

    def do_link_test(self):
        """200 x RDID at every clock with slew-limited pins first; apply the fastest stable one
        (one step slower than the first perfect result for margin)."""
        b = self.bridge
        self.log("Link test: 200 x RDID per setting ...")
        results = []
        total_steps = len(SPEEDS) * len(DRIVES)
        step = 0
        for dn, dv in DRIVES:
            for sn, sv in SPEEDS:
                b.cmd("SPEED %X" % sv)
                b.cmd("SLEW %X" % dv)
                r = b.cmd("LINK C8", timeout=10)  # 0xC8 = 200
                good, total = [int(x, 16) for x in r[5:].split("/")]
                self.log("  drive=%-9s clock=%-8s  %d/%d" % (dn, sn, good, total),
                         "ok" if good == total else "err")
                results.append((dn, dv, sn, sv, good == total))
                step += 1
                self.set_prog(step * 100 // total_steps)
            if any(r[4] for r in results if r[0] == dn):
                break                      # a stable slow-edge setting exists: no need to try fast edges
        stable = [r for r in results if r[4]]
        if not stable:
            b.cmd("SPEED %X" % dict(SPEEDS)[self.speed_var.get()])
            raise BridgeError("No stable setting found. Check 1.2V supply, OE, wiring.")
        dn, dv = stable[0][0], stable[0][1]
        same = [r for r in stable if r[0] == dn]
        pick = same[1] if len(same) > 1 else same[0]      # one step slower than the fastest stable
        self.speed_var.set(pick[2])
        self.drive_var.set(dn)
        b.cmd("SPEED %X" % pick[3])
        b.cmd("SLEW %X" % dv)
        self.log("Applied: drive=%s, clock=%s (fastest stable was %s)." % (dn, pick[2], same[0][2]), "ok")

    def do_hexdump(self):
        addr = self.parse_hex(self.addr_var, "Address")
        n = min(self.parse_hex(self.len_var, "Length"), 0x1000)
        data = self.bridge.read(addr, n)
        for i in range(0, len(data), 16):
            c = data[i:i + 16]
            self.log("%06X  %-47s  %s" % (addr + i, " ".join("%02X" % x for x in c),
                                           "".join(chr(x) if 32 <= x < 127 else "." for x in c)))
        if self.parse_hex(self.len_var, "Length") > 0x1000:
            self.log("(limited to 4KB; use Read->File for more)")

    def do_reset(self):
        self.bridge.cmd("RST")
        self.log("Flash software reset done.", "ok")

    def do_sector_erase(self):
        self.guard()
        addr = self.parse_hex(self.addr_var, "Address") & ~(SECTOR - 1)
        self.bridge.cmd("SE %X" % addr, timeout=5)
        self.log("Sector 0x%06X erased." % addr, "ok")

    def do_chip_erase(self):
        f = self.guard()
        ev, ans = threading.Event(), {}

        def ask():
            ans["v"] = messagebox.askyesno("Chip Erase", "Erase the entire %d MB %s flash?" %
                                           (f["size"] // 0x100000, f["name"]))
            ev.set()

        self.after(0, ask)
        ev.wait()
        if not ans["v"]:
            self.log("Chip erase cancelled.")
            return
        ce = f["info"].chip_erase_s
        self.log("Chip erase (up to ~%d s) ..." % ce)
        self.bridge.cmd("CE", timeout=ce + 20)
        self.log("Chip erased.", "ok")

    def _need_file(self):
        if self.fw_data is None:
            raise BridgeError("Load a file first.")
        start = self.parse_hex(self.addr_var, "Address")
        size = self.flash_size()
        if start + len(self.fw_data) > size:
            raise BridgeError("File does not fit: 0x%06X + %d bytes > %d MB flash" %
                              (start, len(self.fw_data), size // 0x100000))
        return start

    @staticmethod
    def plan_erase(start, end, sizes=None):
        """Cover [start, end) with the largest aligned erase blocks: [(cmd, addr, size, est_seconds)].
        `sizes` = erase sizes the SFDP table advertises with the standard opcodes (None = all)."""
        a = start & ~(SECTOR - 1)
        e = (end + SECTOR - 1) & ~(SECTOR - 1)
        ops = []
        use64 = not sizes or 0x10000 in sizes
        use32 = not sizes or 0x8000 in sizes
        while a < e:
            if use64 and a % 0x10000 == 0 and a + 0x10000 <= e:
                ops.append(("BE", a, 0x10000, T_BE64))
            elif use32 and a % 0x8000 == 0 and a + 0x8000 <= e:
                ops.append(("B32", a, 0x8000, T_BE32))
            else:
                ops.append(("SE", a, SECTOR, T_SE))
            a += ops[-1][2]
        return ops

    def do_program(self):
        t0 = time.time()
        name = os.path.basename(self.file_path) if getattr(self, "file_path", None) else ""
        crc = hexfile.crc32(self.fw_data) if self.fw_data else 0
        try:
            self._program_impl()
        except Cancelled:
            raise
        except Exception as e:
            self.stats.record(False, name, crc, time.time() - t0, str(e)[:120])
            self.q.put(("stats", None, None))
            raise
        self.stats.record(True, name, crc, time.time() - t0,
                          "verified" if self.verify_var.get() else "not verified")
        self.q.put(("stats", None, None))

    def _program_impl(self):
        b = self.bridge
        f = self.guard()
        start = self._need_file()
        data = self.fw_data
        n = len(data)
        pages = []
        pos = 0
        while pos < n:
            addr = start + pos
            size = min(PAGE - (addr % PAGE), n - pos)
            chunk = data[pos:pos + size]
            if chunk.count(0xFF) != len(chunk):
                pages.append((addr, chunk))
            pos += size

        chip = self.chip_var.get() and n > f["size"] // 2
        ce = f["info"].chip_erase_s
        ops = [("CE", 0, f["size"], ce * 0.8)] if chip else self.plan_erase(start, start + n, f["erase_sizes"])
        verify = self.verify_var.get()
        t_erase = sum(o[3] for o in ops)
        t_prog = len(pages) * T_PAGE
        t_ver = n * T_VERIFY_BYTE if verify else 0
        total = max(t_erase + t_prog + t_ver, 1e-9)

        def pct(done):
            self.set_prog(done * 100.0 / total)

        kinds = {}
        for o in ops:
            kinds[o[0]] = kinds.get(o[0], 0) + 1
        self.log("Program %d bytes at 0x%06X: erase %s, write %d pages%s" %
                 (n, start, ", ".join("%dx%s" % (v, k) for k, v in kinds.items()), len(pages),
                  ", verify" if verify else ""))

        done = 0.0
        self.set_state("ERASING  抹除中", "#b36b00", "Erase")
        for i, (cmd, addr, size, est) in enumerate(ops):
            if cmd == "CE":
                b.cmd("CE", timeout=ce + 20)
            else:
                b.cmd("%s %X" % (cmd, addr), timeout=15)
            done += est
            pct(done)
            if i % 16 == 0 or i == len(ops) - 1:
                self.set_state("ERASING  抹除中", "#b36b00", "Erase %d%%" % int(done * 100 / total))
        self.log("Erase done (%d ops)." % len(ops))

        self.set_state("WRITING  燒錄中", "#b36b00", "Write")
        for i, (addr, chunk) in enumerate(pages):
            b.write_page(addr, chunk)
            done += T_PAGE
            if i % 32 == 0 or i == len(pages) - 1:
                pct(done)
                self.set_state("WRITING  燒錄中", "#b36b00", "Write %d%%" % int(done * 100 / total))
        b.cmd("SYNC", timeout=3)
        self.log("Program done (%d pages written, %d blank pages skipped)." %
                 (len(pages), (n + PAGE - 1) // PAGE - len(pages)), "ok")

        if verify:
            self._verify(start, lambda k: pct(t_erase + t_prog + k * T_VERIFY_BYTE))

    def _verify(self, start, progress=None):
        """Compare flash against the loaded file with per-64KB board CRCs."""
        b = self.bridge
        data = self.fw_data
        n = len(data)
        self.set_state("VERIFYING  驗證中", "#b36b00", "Verify")
        for off in range(0, n, VERIFY_CHUNK):
            part = data[off:off + VERIFY_CHUNK]
            if b.crc(start + off, len(part)) != hexfile.crc32(part):
                cur = b.read(start + off, len(part))
                for i, (x, y) in enumerate(zip(part, cur)):
                    if x != y:
                        raise BridgeError("VERIFY MISMATCH at 0x%06X: file %02X, flash %02X" %
                                          (start + off + i, x, y))
                raise BridgeError("VERIFY MISMATCH in 0x%06X block (CRC differs, data equal on re-read)" %
                                  (start + off))
            done = off + len(part)
            if progress:
                progress(done)
            else:
                self.set_prog(done * 100.0 / n)
            self.set_state("VERIFYING  驗證中", "#b36b00", "Verify %d%%" % (done * 100 // n))
        self.log("VERIFY OK  (CRC32 %08X, %d bytes)" % (hexfile.crc32(data), n), "ok")

    def do_verify(self):
        self._verify(self._need_file())

    def do_read_file(self):
        addr = self.parse_hex(self.addr_var, "Address")
        n = self.parse_hex(self.len_var, "Length")
        self.log("Read->File: 0x%06X, 0x%X bytes (%d KB)" % (addr, n, (n + 1023) // 1024))
        if n <= 0 or addr + n > self.flash_size():
            raise BridgeError("Address/Length out of range (flash is 0x%X bytes)" % self.flash_size())
        ev, ans = threading.Event(), {}

        def ask():
            ans["p"] = filedialog.asksaveasfilename(defaultextension=".bin",
                                                    initialfile="flash_%06X_%X.bin" % (addr, n),
                                                    filetypes=[("Binary", "*.bin"), ("All", "*.*")])
            ev.set()

        self.after(0, ask)
        ev.wait()
        if not ans["p"]:
            self.log("Read->File cancelled.")
            return
        rd = 70 if self.dbl_var.get() else 100
        self.set_state("READING  讀取中", "#b36b00", "Read")
        data = self.bridge.read(addr, n, lambda k: self.set_prog(k * rd // n))
        if self.dbl_var.get():
            self.set_state("CHECKING  確認中", "#b36b00", "Double-check")
            for off in range(0, n, VERIFY_CHUNK):
                part = data[off:off + VERIFY_CHUNK]
                board = self.bridge.crc(addr + off, len(part))
                if board != hexfile.crc32(part):
                    raise BridgeError("Double-check failed at 0x%06X: PC CRC %08X != board CRC %08X" %
                                      (addr + off, hexfile.crc32(part), board))
                self.set_prog(rd + (off + len(part)) * (100 - rd) // n)
            self.log("Double-check OK (CRC32 %08X)." % hexfile.crc32(data), "ok")
        with open(ans["p"], "wb") as f:
            f.write(data)
        self.log("Saved %d bytes to %s" % (len(data), ans["p"]), "ok")

    # --------------------------------------------------------------- misc
    def load_file(self):
        p = filedialog.askopenfilename(filetypes=[("Firmware", "*.bin *.hex *.ihx"), ("All", "*.*")])
        if not p:
            return
        try:
            start, data = hexfile.load_file(p)
        except Exception as e:
            messagebox.showerror("Load File", str(e))
            return
        self.fw_start, self.fw_data = start, data
        self.file_path = p
        if p.lower().endswith((".hex", ".ihx")):
            self.addr_var.set("%06X" % start)
        self.file_lbl.configure(
            text="%s   %d bytes   0x%06X-0x%06X   CRC32 %08X" %
                 (os.path.basename(p), len(data), start, start + len(data) - 1, hexfile.crc32(data)),
            foreground="#000")
        self.log("Loaded " + p)

    def open_raw(self):
        if self.raw_win and self.raw_win.winfo_exists():
            self.raw_win.lift()
            return
        self.raw_win = tk.Toplevel(self)
        self.raw_win.title("Raw Monitor (commands and replies)")
        self.raw_win.withdraw()
        self.raw_text = tk.Text(self.raw_win, width=80, height=24, state="disabled",
                                bg="#10141a", fg="#dddddd", font=("Consolas", 10))
        self.raw_text.pack(fill="both", expand=True)
        ent = ttk.Entry(self.raw_win)
        ent.pack(fill="x")

        def send(_):
            if self.bridge and not self.busy and ent.get().strip():
                t = ent.get().strip()
                ent.delete(0, "end")
                self.run(lambda: self.log("RAW: %s -> %s" % (t, self.bridge.cmd(t))))

        ent.bind("<Return>", send)
        self.place_right(self.raw_win)
        self.raw_win.deiconify()

    def _on_close(self):
        if self.bridge:
            self.bridge.cancel.set()
            self.bridge.close()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
