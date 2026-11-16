#!/usr/bin/env python3
"""emu_edge_ref.py -- the frame-boundary block fetch: the spec's per-sample clamp AND dav1d's emu_edge_c.

av1_mc_emu_edge (src/av1_mc.cyr) fetches a bw x bh block at (x, y) from a visible iw x ih reference plane, which the
block may overhang on any side. tests/av1_mc_emu_edge.tcyr pins it with five cases; their generator, a scratchpad
port of dav1d's emu_edge_c alone (emu_edge.py), was lost.

The SPEC states the rule per sample. 7.11.3.4 reads the reference at
    ref[ Clip3( 0, lastY, y ) ][ Clip3( 0, lastX, x ) ]
with lastX = iw - 1 and lastY = ih - 1, so every block sample is that clamp of its own coordinates. dav1d's
emu_edge_c (src/mc_tmpl.c), which drishti follows, builds the same block another way: it copies the visible part,
replicates it left and right, then replicates the top and bottom rows, with every extension count clipped to
bw - 1 (bh - 1). This port transcribes both, ASSERTS them equal on every block and plane of 1..6 samples a side at
every position from fully outside on one side to fully outside on the other, and asserts the spec form reproduces
the test's five cases, one derived by hand below.
"""
import sys


def spec_fetch(ref, iw, ih, x, y, bw, bh):
    return [[ref[min(max(y + r, 0), ih - 1)][min(max(x + c, 0), iw - 1)] for c in range(bw)] for r in range(bh)]


def dav1d_emu_edge(ref, iw, ih, x, y, bw, bh):
    """emu_edge_c, step for step"""
    def iclip(v, lo, hi):
        return lo if v < lo else (hi if v > hi else v)
    ry = iclip(y, 0, ih - 1)
    rx = iclip(x, 0, iw - 1)
    left_ext = iclip(-x, 0, bw - 1)
    right_ext = iclip(x + bw - iw, 0, bw - 1)
    assert left_ext + right_ext < bw
    top_ext = iclip(-y, 0, bh - 1)
    bottom_ext = iclip(y + bh - ih, 0, bh - 1)
    assert top_ext + bottom_ext < bh
    dst = [[None] * bw for _ in range(bh)]
    center_w = bw - left_ext - right_ext
    center_h = bh - top_ext - bottom_ext
    for yy in range(center_h):   # the visible portion, each line extended left and right
        row = dst[top_ext + yy]
        for k in range(center_w):
            row[left_ext + k] = ref[ry + yy][rx + k]
        for k in range(left_ext):
            row[k] = row[left_ext]
        for k in range(right_ext):
            row[left_ext + center_w + k] = row[left_ext + center_w - 1]
    for yy in range(top_ext):    # copy the top
        dst[yy] = list(dst[top_ext])
    for yy in range(bottom_ext):  # copy the bottom
        dst[top_ext + center_h + yy] = list(dst[top_ext + center_h - 1])
    return dst


def checksum(block):
    return sum(v * (i + 1) for i, v in enumerate(val for row in block for val in row))


# tests/av1_mc_emu_edge.tcyr: the 6x5 plane ref[r][c] = r * 10 + c, 4x4 blocks
#   (name, x, y, checksum, {index: value})
KATS = [
    ("center", 1, 1, 4560, {0: 11, 15: 44}),
    ("top-left", -2, -1, 1620, {0: 0, 3: 1, 8: 10}),
    ("bottom-right", 4, 3, 5992, {0: 34, 15: 45}),
    ("bottom-left", -1, 3, 5456, {0: 30}),
    ("wholly-left", -6, 1, 4200, {0: 10, 3: 10}),
]
# by hand, "center": the block is ref[1..4][1..4], value 10 * (rr + 1) + (cc + 1) at index 4 * rr + cc; the
# position-weighted sum is sum_rr sum_cc (4rr + cc + 1)(10rr + cc + 11). Row 0: 1*11 + 2*12 + 3*13 + 4*14 = 130;
# row 1: 5*21 + 6*22 + 7*23 + 8*24 = 590; row 2: 9*31 + 10*32 + 11*33 + 12*34 = 1370; row 3: 13*41 + 14*42 + 15*43 +
# 16*44 = 2470; total 4560. (My first per-row figures were wrong; this assert caught them.)


def main():
    n = 0
    for iw in range(1, 7):
        for ih in range(1, 7):
            ref = [[r * 10 + c for c in range(iw)] for r in range(ih)]
            for bw in range(1, 7):
                for bh in range(1, 7):
                    for x in range(-bw - 2, iw + 3):
                        for y in range(-bh - 2, ih + 3):
                            assert spec_fetch(ref, iw, ih, x, y, bw, bh) == dav1d_emu_edge(ref, iw, ih, x, y, bw, bh), \
                                (iw, ih, bw, bh, x, y)
                            n += 1
    ref = [[r * 10 + c for c in range(6)] for r in range(5)]
    rows = [sum((4 * rr + cc + 1) * (10 * rr + cc + 11) for cc in range(4)) for rr in range(4)]
    assert rows == [130, 590, 1370, 2470] and sum(rows) == 4560
    for (name, x, y, cs, px) in KATS:
        out = spec_fetch(ref, 6, 5, x, y, 4, 4)
        flat = [v for row in out for v in row]
        assert checksum(out) == cs, (name, checksum(out), cs)
        for i, v in px.items():
            assert flat[i] == v, (name, i, flat[i], v)
    print('emu_edge_ref: the spec clamp == dav1d emu_edge_c on %d fetches; all 5 cases of '
          'tests/av1_mc_emu_edge.tcyr reproduced -- OK' % n)
    return 0


if __name__ == '__main__':
    sys.exit(main())
