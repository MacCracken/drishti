#!/usr/bin/env python3
"""superres_upscale_ref.py -- superres upscaling (7.16): the row loop, the step / x0 geometry and whole frames, the
spec's form against dav1d's.

tests/av1_superres.tcyr pins drishti's upscaler with known answers whose generators were scratchpad ports of dav1d
alone, all lost: resize_ref.py (0.7.85, the row loop, resize_c), upscale_geom.py (0.7.86, the geometry, scale_fac
and get_upscale_x0) and sr_ref.py (0.7.87, whole frames). This replaces the three with two transcriptions:

  * SPEC (7.16), from superres_ref.py, which ports it verbatim: per plane, stepX = ((downscaledPlaneW << 14) +
    upscaledPlaneW / 2) / upscaledPlaneW, the initialSubpelX formula, and per sample srcX = -(1 << 14) +
    initialSubpelX + x * stepX, 8 taps of Upscale_Filter[(srcX & 0x3fff) >> 8] clamped to [0, maxX], Round2(., 7),
    Clip1. The row function below is that loop for one row, with stepX / initialSubpelX / maxX as inputs (the
    test drives drishti's row with them directly).
  * DAV1D: resize_c (src/mc_tmpl.c), which keeps the integer position src_x and the fraction mx apart (mx += dx;
    src_x += mx >> 14; mx &= 0x3fff) and filters with dav1d_resize_filter, the spec's table negated, negating the
    sum back; and the geometry from src/decode.c: scale_fac(in, out) = ((in << 14) + (out >> 1)) / out and
    get_upscale_x0, with chroma widths (w + ss_hor) >> ss_hor.

The port ASSERTS the two equal: the geometry on every (downscaled, upscaled) width pair superres can produce up to
1024 (upscaled from 1 to 2 times the downscaled width), and the row on 20,000 random rows, widths, steps, starting
fractions and bit depths. It then asserts the spec form reproduces every known answer of the three tests, plus
test_superres_mi_clamp's (whose port, superres_ref.py, printed them without asserting).
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from superres_ref import (Upscale_Filter, upscale_plane, cdiv, round2, clip3, LUMA_ROW, CHROMA_ROW,   # noqa: E402
                          SUPERRES_SCALE_BITS, SUPERRES_SCALE_MASK, SUPERRES_EXTRA_BITS)

DAV1D_RESIZE = [[-v for v in row] for row in Upscale_Filter]   # upscale_filter_ref.py checks this IS tables.c's


# ---- the spec ---------------------------------------------------------------------------------------------------
def spec_geometry(down_w, up_w):
    stepX = cdiv((down_w << SUPERRES_SCALE_BITS) + cdiv(up_w, 2), up_w)
    err = up_w * stepX - (down_w << SUPERRES_SCALE_BITS)
    x0 = (cdiv(-((up_w - down_w) << (SUPERRES_SCALE_BITS - 1)) + cdiv(up_w, 2), up_w)
          + (1 << (SUPERRES_EXTRA_BITS - 1)) - cdiv(err, 2))
    return stepX, x0 & SUPERRES_SCALE_MASK


def spec_row(src, maxX, dst_w, stepX, initialSubpelX, bd):
    out = []
    for x in range(dst_w):
        srcX = -(1 << SUPERRES_SCALE_BITS) + initialSubpelX + x * stepX
        px = srcX >> SUPERRES_SCALE_BITS
        sub = (srcX & SUPERRES_SCALE_MASK) >> SUPERRES_EXTRA_BITS
        s = sum(src[clip3(0, maxX, px + k - 3)] * Upscale_Filter[sub][k] for k in range(8))
        out.append(clip3(0, (1 << bd) - 1, round2(s, 7)))
    return out


# ---- dav1d ------------------------------------------------------------------------------------------------------
def c_div(a, b):
    """C's / (truncating)"""
    return cdiv(a, b)


def dav1d_scale_fac(ref_sz, this_sz):
    return c_div((ref_sz << 14) + (this_sz >> 1), this_sz)


def dav1d_get_upscale_x0(in_w, out_w, step):
    err = out_w * step - (in_w << 14)
    x0 = c_div(-((out_w - in_w) << 13) + (out_w >> 1), out_w) + 128 - c_div(err, 2)
    return x0 & 0x3fff


def dav1d_resize_row(src, src_w, dst_w, dx, mx0, bd):
    def iclip(v, lo, hi):
        return lo if v < lo else (hi if v > hi else v)
    out = []
    mx, src_x = mx0, -1
    for _ in range(dst_w):
        F = DAV1D_RESIZE[mx >> 8]
        s = sum(F[k] * src[iclip(src_x + k - 3, 0, src_w - 1)] for k in range(8))
        out.append(iclip((-s + 64) >> 7, 0, (1 << bd) - 1))
        mx += dx
        src_x += mx >> 14
        mx &= 0x3fff
    return out


# ---- the test's known answers ------------------------------------------------------------------------------------
RAMP = [10 + 20 * i for i in range(8)]                                    # 10, 30, .., 150
# test_superres_upscale_row: (dst_w, dx, mx0, expected) on RAMP, maxX 7
ROW_KATS = [
    (16, 8192, 8321, [8, 10, 18, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 142, 150]),
    (12, 10923, 5461, [9, 10, 22, 37, 50, 63, 76, 90, 103, 116, 130, 145]),
]
# test_superres_geometry: (down_w, up_w, step, x0)
GEOM_KATS = [(8, 16, 8192, 12417), (8, 12, 10923, 13780), (8, 10, 13107, 14876), (13, 16, 13312, 14977),
             (6, 8, 12288, 14465), (100, 128, 12800, 14721)]
# ...and its geometry -> row chain on RAMP
CHAIN_KATS = [
    (8, 16, [8, 13, 24, 35, 45, 55, 65, 75, 85, 95, 105, 115, 125, 136, 147, 152]),
    (8, 12, [9, 18, 33, 47, 60, 73, 87, 100, 113, 127, 142, 151]),
]
# test_superres_upscale_frame's chroma row: 4:2:0, luma 8 -> 16, chroma 4 -> 8, every chroma row 20, 60, 100, 140
CHROMA_KAT = [17, 27, 48, 70, 90, 112, 133, 143]
# test_superres_mi_clamp: FrameWidth 13 -> 26, MiCols 4, luma / chroma rows of superres_ref.py's fixture
MI_LUMA = [19, 23, 30, 39, 46, 54, 61, 69, 76, 84, 91, 99, 106, 114, 121, 129, 136, 144, 151, 158, 166, 177, 184,
           179, 183, 234]
MI_CHROMA = [39, 45, 56, 68, 79, 89, 100, 114, 120, 125, 151, 173, 129]


def main():
    # 1. by hand. 8 -> 16: stepX = ((8 << 14) + 8) / 16 = 131080 / 16 = 8192 (8192.5, truncated); err = 16 * 8192 -
    #    131072 = 0; initialSubpelX = (-(8 << 13) + 8) / 16 + 128 - 0 = -65528 / 16 + 128 = -4095 + 128 = -3967
    #    (C truncates -4095.5 toward zero), and -3967 & 0x3fff = 16384 - 3967 = 12417.
    assert spec_geometry(8, 16) == (8192, 12417) and (-3967) & 0x3fff == 12417
    # 2. dav1d equals the spec: geometry on every pair superres can produce, rows on random inputs
    ng = 0
    for down in range(1, 1025):
        for up in range(down, 2 * down + 1):
            step = dav1d_scale_fac(down, up)
            assert spec_geometry(down, up) == (step, dav1d_get_upscale_x0(down, up, step)), (down, up)
            ng += 1
    rng = random.Random(7016)
    nr = 0
    for _ in range(20000):
        bd = rng.choice((8, 10, 12))
        src_w = rng.randrange(1, 40)
        src = [rng.randrange(1 << bd) for _ in range(src_w)]
        if rng.randrange(2):
            down = rng.randrange(1, 40)
            up = rng.randrange(down, 2 * down + 1)
            dx, mx0 = spec_geometry(down, up)
        else:
            dx, mx0 = rng.randrange(8192, 16385), rng.randrange(0x4000)
        dst_w = rng.randrange(1, 80)
        assert spec_row(src, src_w - 1, dst_w, dx, mx0, bd) == dav1d_resize_row(src, src_w, dst_w, dx, mx0, bd), \
            (bd, src_w, dx, mx0, dst_w)
        nr += 1
    # 3. the test's known answers, from the spec form
    for (dst_w, dx, mx0, want) in ROW_KATS:
        assert spec_row(RAMP, 7, dst_w, dx, mx0, 8) == want, (dst_w, dx, mx0)
    assert spec_row([200] * 8, 7, 16, 8192, 8321, 8) == [200] * 16
    for (down, up, step, x0) in GEOM_KATS:
        assert spec_geometry(down, up) == (step, x0), (down, up, spec_geometry(down, up))
    for (down, up, want) in CHAIN_KATS:
        step, x0 = spec_geometry(down, up)
        assert spec_row(RAMP, down - 1, up, step, x0, 8) == want, (down, up)
    # whole frames through the spec's own plane loop: mono 8x3 -> 16x3 (MiCols 2, so maxX = 7), 4:2:0 8x4 -> 16x4
    # (luma maxX 7; chroma downscaledPlaneW 4, maxX = (2 >> 1) * 4 - 1 = 3)
    luma16 = CHAIN_KATS[0][2]
    assert upscale_plane([RAMP] * 3, 8, 16, 3, 2, 0, 0, 8) == [luma16] * 3
    assert upscale_plane([RAMP] * 4, 8, 16, 4, 2, 0, 0, 8) == [luma16] * 4
    assert upscale_plane([[20, 60, 100, 140]] * 2, 8, 16, 4, 2, 1, 1, 8) == [CHROMA_KAT] * 2
    # test_superres_mi_clamp (superres_ref.py's fixture), asserted at last
    assert upscale_plane([LUMA_ROW] * 2, 13, 26, 2, 4, 0, 0, 8) == [MI_LUMA] * 2
    assert upscale_plane([CHROMA_ROW], 13, 26, 2, 4, 1, 1, 8) == [MI_CHROMA]
    print('superres_upscale_ref: dav1d equals spec 7.16 on %d geometry pairs and %d rows; every known answer of '
          'tests/av1_superres.tcyr (row, geometry, chain, frame, MI clamp) reproduced -- OK' % (ng, nr))
    return 0


if __name__ == '__main__':
    sys.exit(main())
