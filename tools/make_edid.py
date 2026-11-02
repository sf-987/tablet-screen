#!/usr/bin/env python3
"""Generate a minimal, valid EDID 1.3 with a single CVT reduced-blanking detailed timing.

    make_edid.py WIDTH HEIGHT [--hz 60] [--mm-width 316 --mm-height 198] [--name "Tablet"] -o out.edid

Examples:
    make_edid.py 3840 2400 --hz 30 -o tablet.edid      # evdi virtual head for a 16:10 tablet
    make_edid.py 1920 1200 -o tablet-1200p.edid         # for a programmable dummy plug

Physical size only affects the DPI the desktop computes for the output. The EDID checksum
is computed; evdi and the kernel's edid_override reject EDIDs with bad checksums.
"""
import argparse, struct, sys


def cvt_rb(w, h, hz):
    """CVT 1.2 reduced blanking (v1): returns pixel clock (MHz) and blanking numbers."""
    hblank, hsync_off, hsync_w = 160, 48, 32
    vfp, vsync, vbp = 3, 6, 6
    ht = w + hblank
    vbl = max(int((460e-6 * hz * h) / (1 - 460e-6 * hz)) + 1, vfp + vsync + vbp)
    vt = h + vbl
    pclk = round(ht * vt * hz / 1e6 * 4) / 4       # 0.25 MHz granularity
    return pclk, hblank, hsync_off, hsync_w, vbl, vfp, vsync


def make(w, h, hz, mm_w, mm_h, name, product=1):
    pclk, hblank, hso, hsw, vbl, vso, vsw = cvt_rb(w, h, hz)
    if pclk > 655.35:
        sys.exit(f"pixel clock {pclk} MHz exceeds EDID 1.3 limit; lower the refresh rate")
    e = bytearray(128)
    e[0:8] = b"\x00\xff\xff\xff\xff\xff\xff\x00"
    mfr = ((ord('T') - 64) << 10) | ((ord('A') - 64) << 5) | (ord('B') - 64)   # "TAB"
    e[8:10] = struct.pack(">H", mfr)
    e[10:12] = struct.pack("<H", product)
    e[12:16] = struct.pack("<I", product)
    e[16], e[17] = 1, 36                       # week 1, 2026
    e[18], e[19] = 1, 3                        # EDID 1.3
    e[20] = 0x80                               # digital input
    e[21], e[22] = mm_w // 10, mm_h // 10      # cm
    e[23] = 120                                # gamma 2.2
    e[24] = 0x0A                               # RGB, preferred timing is DTD 1
    e[25:35] = bytes([0xEE, 0x91, 0xA3, 0x54, 0x4C, 0x99, 0x26, 0x0F, 0x50, 0x54])  # sRGB-ish
    e[35:38] = bytes(3)                        # no established timings
    e[38:54] = bytes([0x01, 0x01] * 8)         # standard timings unused
    pk = int(round(pclk * 100))
    o = 54                                     # DTD 1
    e[o:o+2] = struct.pack("<H", pk)
    e[o+2] = w & 0xFF; e[o+3] = hblank & 0xFF; e[o+4] = ((w >> 8) << 4) | (hblank >> 8)
    e[o+5] = h & 0xFF; e[o+6] = vbl & 0xFF;    e[o+7] = ((h >> 8) << 4) | (vbl >> 8)
    e[o+8] = hso & 0xFF; e[o+9] = hsw & 0xFF;  e[o+10] = ((vso & 0xF) << 4) | (vsw & 0xF)
    e[o+11] = ((hso >> 8) << 6) | ((hsw >> 8) << 4) | ((vso >> 4) << 2) | (vsw >> 4)
    e[o+12] = mm_w & 0xFF; e[o+13] = mm_h & 0xFF; e[o+14] = ((mm_w >> 8) << 4) | (mm_h >> 8)
    e[o+15] = e[o+16] = 0
    e[o+17] = 0x1E                             # digital, separate sync, +H -V

    def text(off, tag, s):
        e[off:off+5] = bytes([0, 0, 0, tag, 0])
        e[off+5:off+18] = (s + "\n").ljust(13)[:13].encode("ascii", "replace")

    text(72, 0xFC, name)                       # monitor name
    e[90:95] = bytes([0, 0, 0, 0xFD, 0])        # range limits: 24-75 Hz, 30-160 kHz, 700 MHz
    e[95:108] = bytes([24, 75, 30, 160, 70, 0x0A] + [0x20] * 7)
    text(108, 0xFE, "virtual")
    e[126] = 0                                 # no extension blocks
    e[127] = (-sum(e[:127])) & 0xFF
    return bytes(e), pclk, vbl


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("width", type=int); ap.add_argument("height", type=int)
    ap.add_argument("--hz", type=float, default=60.0)
    ap.add_argument("--mm-width", type=int, default=316); ap.add_argument("--mm-height", type=int, default=198)
    ap.add_argument("--name", default="Tablet 16x10")
    ap.add_argument("-o", "--output", default="tablet.edid")
    a = ap.parse_args()
    data, pclk, vbl = make(a.width, a.height, a.hz, a.mm_width, a.mm_height, a.name)
    open(a.output, "wb").write(data)
    print(f"{a.output}: {a.width}x{a.height} @ {a.hz:g} Hz, pixel clock {pclk} MHz, checksum 0x{data[127]:02x}")


if __name__ == "__main__":
    main()
