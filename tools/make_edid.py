#!/usr/bin/env python3
"""Generate a minimal, valid EDID 1.3 for a 1920x1200@60 (CVT-RB) 16:10 display.
Usage: python3 make_edid.py  -> writes tablet.edid. Edit W/H/MM_* for other shapes."""
import struct

W, H = 1920, 1200
# CVT reduced blanking 1920x1200@60: pixel clock 154.00 MHz
PCLK = 15400             # in 10 kHz units
HBLANK = 160             # 2080 - 1920
HSYNC_OFF, HSYNC_W = 48, 32
VBLANK = 35              # 1235 - 1200
VSYNC_OFF, VSYNC_W = 3, 6
MM_W, MM_H = 345, 215    # ~16" 16:10, only affects DPI reporting

e = bytearray(128)
e[0:8] = b"\x00\xff\xff\xff\xff\xff\xff\x00"
# Manufacturer "TAB" (3 x 5-bit letters, A=1), product 0x0001, serial 1
m = ((ord('T')-64) << 10) | ((ord('A')-64) << 5) | (ord('B')-64)
e[8:10] = struct.pack(">H", m)
e[10:12] = struct.pack("<H", 0x0001)
e[12:16] = struct.pack("<I", 1)
e[16] = 1          # week
e[17] = 36         # year 2026 - 1990
e[18], e[19] = 1, 3  # EDID 1.3
e[20] = 0x80       # digital input
e[21], e[22] = MM_W // 10, MM_H // 10
e[23] = 120        # gamma 2.2
e[24] = 0x0A       # RGB colour, preferred timing in DTD 1
# chromaticity (sRGB-ish)
e[25:35] = bytes([0xEE, 0x91, 0xA3, 0x54, 0x4C, 0x99, 0x26, 0x0F, 0x50, 0x54])
e[35:38] = bytes([0, 0, 0])   # no established timings
e[38:54] = bytes([0x01, 0x01] * 8)  # standard timings unused

def dtd(off):
    e[off:off+2] = struct.pack("<H", PCLK)
    e[off+2] = W & 0xFF
    e[off+3] = HBLANK & 0xFF
    e[off+4] = ((W >> 8) << 4) | (HBLANK >> 8)
    e[off+5] = H & 0xFF
    e[off+6] = VBLANK & 0xFF
    e[off+7] = ((H >> 8) << 4) | (VBLANK >> 8)
    e[off+8] = HSYNC_OFF & 0xFF
    e[off+9] = HSYNC_W & 0xFF
    e[off+10] = ((VSYNC_OFF & 0xF) << 4) | (VSYNC_W & 0xF)
    e[off+11] = ((HSYNC_OFF >> 8) << 6) | ((HSYNC_W >> 8) << 4) | ((VSYNC_OFF >> 4) << 2) | (VSYNC_W >> 4)
    e[off+12] = MM_W & 0xFF
    e[off+13] = MM_H & 0xFF
    e[off+14] = ((MM_W >> 8) << 4) | (MM_H >> 8)
    e[off+15] = 0
    e[off+16] = 0
    e[off+17] = 0x1E  # digital separate sync, +hsync, -vsync (CVT-RB)

def text(off, tag, s):
    e[off:off+5] = bytes([0, 0, 0, tag, 0])
    s = (s + "\n").ljust(13)[:13]
    e[off+5:off+18] = s.encode("ascii")

dtd(54)
text(72, 0xFC, "Tablet 16x10")               # monitor name
# range limits: 50-75 Hz, 30-90 kHz, max pclk 160 MHz
e[90:95] = bytes([0, 0, 0, 0xFD, 0])
e[95:108] = bytes([50, 75, 30, 90, 16, 0x0A, 0x20, 0x20, 0x20, 0x20, 0x20, 0x20, 0x20])
text(108, 0xFE, "VirtScreen")                # unspecified text
e[126] = 0  # no extensions
e[127] = (-sum(e[:127])) & 0xFF

open("tablet.edid", "wb").write(e)
print(len(e), "bytes, checksum", hex(e[127]))
