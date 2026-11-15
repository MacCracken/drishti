#!/usr/bin/env python3
# superres_ref.py — spec-literal reference for the AV1 superres UPSCALING process.
#
# Ports spec 7.16 ("Upscaling process", 08.decoding.process.md) VERBATIM, sharing NO code with
# src/av1_superres.cyr. The pseudocode it transcribes:
#
#   downscaledPlaneW = Round2(FrameWidth, subX)
#   upscaledPlaneW = Round2(UpscaledWidth, subX)
#   planeH = Round2(FrameHeight, subY)
#   stepX = ((downscaledPlaneW << SUPERRES_SCALE_BITS) + (upscaledPlaneW / 2)) / upscaledPlaneW
#   err = (upscaledPlaneW * stepX) - (downscaledPlaneW << SUPERRES_SCALE_BITS)
#   initialSubpelX =
#     (-((upscaledPlaneW - downscaledPlaneW) << (SUPERRES_SCALE_BITS - 1)) + upscaledPlaneW / 2) / upscaledPlaneW +
#     (1 << (SUPERRES_EXTRA_BITS - 1)) - err / 2
#   initialSubpelX &= SUPERRES_SCALE_MASK
#   miW = MiCols >> subX
#   minX = 0
#   maxX = miW * MI_SIZE - 1
#   for ( y = 0; y < planeH; y++ ) {
#       for ( x = 0; x < upscaledPlaneW; x++ ) {
#           srcX = -(1 << SUPERRES_SCALE_BITS) + initialSubpelX + x*stepX
#           srcXPx = (srcX >> SUPERRES_SCALE_BITS)
#           srcXSubpel = (srcX & SUPERRES_SCALE_MASK) >> SUPERRES_EXTRA_BITS
#           sum = 0
#           for ( k = 0; k < SUPERRES_FILTER_TAPS; k++ ) {
#               sampleX = Clip3(minX, maxX, srcXPx + (k - SUPERRES_FILTER_OFFSET))
#               px = frame[plane][y][sampleX]
#               sum += px * Upscale_Filter[srcXSubpel][k]
#           }
#           outputFrame[plane][y][x] = Clip1(Round2(sum, FILTER_BITS))
#       }
#   }
#
# THE POINT OF THIS PORT (0.8.3 bite 3): maxX is the MI-ALIGNED plane width, not the visible
# downscaled width, so a tap past the picture reads the reconstructed OVERHANG columns. The
# known answers below use a 13-wide downscaled frame (MiCols 4 -> 16 luma, 8 chroma) whose
# overhang columns hold values unlike the last visible column, so a decoder that clamps at the
# visible width produces different output in the last upscaled columns.
#
# The spec's "/" is integer division truncating toward zero (C semantics); Python's // floors,
# so the divisions below go through cdiv. ">>" on a negative srcX is arithmetic (floor) in both.

import os
import re

SUPERRES_SCALE_BITS = 14
SUPERRES_SCALE_MASK = (1 << 14) - 1
SUPERRES_EXTRA_BITS = 8
SUPERRES_FILTER_TAPS = 8
SUPERRES_FILTER_OFFSET = 3
FILTER_BITS = 7
MI_SIZE = 4

# Upscale_Filter[64][8], copied from the spec text (7.16). Checked against the spec markdown
# below whenever build/spec-dl/08.decoding.process.md is present.
Upscale_Filter = [
    [0, 0, 0, 128, 0, 0, 0, 0], [0, 0, -1, 128, 2, -1, 0, 0],
    [0, 1, -3, 127, 4, -2, 1, 0], [0, 1, -4, 127, 6, -3, 1, 0],
    [0, 2, -6, 126, 8, -3, 1, 0], [0, 2, -7, 125, 11, -4, 1, 0],
    [-1, 2, -8, 125, 13, -5, 2, 0], [-1, 3, -9, 124, 15, -6, 2, 0],
    [-1, 3, -10, 123, 18, -6, 2, -1], [-1, 3, -11, 122, 20, -7, 3, -1],
    [-1, 4, -12, 121, 22, -8, 3, -1], [-1, 4, -13, 120, 25, -9, 3, -1],
    [-1, 4, -14, 118, 28, -9, 3, -1], [-1, 4, -15, 117, 30, -10, 4, -1],
    [-1, 5, -16, 116, 32, -11, 4, -1], [-1, 5, -16, 114, 35, -12, 4, -1],
    [-1, 5, -17, 112, 38, -12, 4, -1], [-1, 5, -18, 111, 40, -13, 5, -1],
    [-1, 5, -18, 109, 43, -14, 5, -1], [-1, 6, -19, 107, 45, -14, 5, -1],
    [-1, 6, -19, 105, 48, -15, 5, -1], [-1, 6, -19, 103, 51, -16, 5, -1],
    [-1, 6, -20, 101, 53, -16, 6, -1], [-1, 6, -20, 99, 56, -17, 6, -1],
    [-1, 6, -20, 97, 58, -17, 6, -1], [-1, 6, -20, 95, 61, -18, 6, -1],
    [-2, 7, -20, 93, 64, -18, 6, -2], [-2, 7, -20, 91, 66, -19, 6, -1],
    [-2, 7, -20, 88, 69, -19, 6, -1], [-2, 7, -20, 86, 71, -19, 6, -1],
    [-2, 7, -20, 84, 74, -20, 7, -2], [-2, 7, -20, 81, 76, -20, 7, -1],
    [-2, 7, -20, 79, 79, -20, 7, -2], [-1, 7, -20, 76, 81, -20, 7, -2],
    [-2, 7, -20, 74, 84, -20, 7, -2], [-1, 6, -19, 71, 86, -20, 7, -2],
    [-1, 6, -19, 69, 88, -20, 7, -2], [-1, 6, -19, 66, 91, -20, 7, -2],
    [-2, 6, -18, 64, 93, -20, 7, -2], [-1, 6, -18, 61, 95, -20, 6, -1],
    [-1, 6, -17, 58, 97, -20, 6, -1], [-1, 6, -17, 56, 99, -20, 6, -1],
    [-1, 6, -16, 53, 101, -20, 6, -1], [-1, 5, -16, 51, 103, -19, 6, -1],
    [-1, 5, -15, 48, 105, -19, 6, -1], [-1, 5, -14, 45, 107, -19, 6, -1],
    [-1, 5, -14, 43, 109, -18, 5, -1], [-1, 5, -13, 40, 111, -18, 5, -1],
    [-1, 4, -12, 38, 112, -17, 5, -1], [-1, 4, -12, 35, 114, -16, 5, -1],
    [-1, 4, -11, 32, 116, -16, 5, -1], [-1, 4, -10, 30, 117, -15, 4, -1],
    [-1, 3, -9, 28, 118, -14, 4, -1], [-1, 3, -9, 25, 120, -13, 4, -1],
    [-1, 3, -8, 22, 121, -12, 4, -1], [-1, 3, -7, 20, 122, -11, 3, -1],
    [-1, 2, -6, 18, 123, -10, 3, -1], [0, 2, -6, 15, 124, -9, 3, -1],
    [0, 2, -5, 13, 125, -8, 2, -1], [0, 1, -4, 11, 125, -7, 2, 0],
    [0, 1, -3, 8, 126, -6, 2, 0], [0, 1, -3, 6, 127, -4, 1, 0],
    [0, 1, -2, 4, 127, -3, 1, 0], [0, 0, -1, 2, 128, -1, 0, 0],
]


def check_table_against_spec():
    here = os.path.dirname(os.path.abspath(__file__))
    md = os.path.join(here, '..', '..', 'build', 'spec-dl', '08.decoding.process.md')
    if not os.path.exists(md):
        return 'spec markdown not present; embedded table used unchecked'
    text = open(md).read()
    body = text[text.index('Upscale_Filter[SUPERRES_FILTER_SHIFTS][SUPERRES_FILTER_TAPS] = {'):]
    body = body[:body.index('}\n~~~~~') + 1]
    rows = [[int(v) for v in r.split(',')] for r in re.findall(r'\{([^{}]*)\}', body)]
    assert rows == Upscale_Filter, 'embedded Upscale_Filter differs from the spec markdown'
    return 'Upscale_Filter matches the spec markdown (64 rows)'


def cdiv(a, b):
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def round2(x, n):
    return (x + (1 << (n - 1))) >> n if n else x


def clip3(lo, hi, x):
    return lo if x < lo else (hi if x > hi else x)


def upscale_plane(frame, FrameWidth, UpscaledWidth, FrameHeight, MiCols, subX, subY, BitDepth):
    """frame[y][x] holds the downscaled plane INCLUDING its MI-grid overhang columns."""
    downscaledPlaneW = round2(FrameWidth, subX)
    upscaledPlaneW = round2(UpscaledWidth, subX)
    planeH = round2(FrameHeight, subY)
    stepX = cdiv((downscaledPlaneW << SUPERRES_SCALE_BITS) + cdiv(upscaledPlaneW, 2), upscaledPlaneW)
    err = (upscaledPlaneW * stepX) - (downscaledPlaneW << SUPERRES_SCALE_BITS)
    initialSubpelX = (cdiv(-((upscaledPlaneW - downscaledPlaneW) << (SUPERRES_SCALE_BITS - 1))
                           + cdiv(upscaledPlaneW, 2), upscaledPlaneW)
                      + (1 << (SUPERRES_EXTRA_BITS - 1)) - cdiv(err, 2))
    initialSubpelX &= SUPERRES_SCALE_MASK
    miW = MiCols >> subX
    minX = 0
    maxX = miW * MI_SIZE - 1
    out = []
    for y in range(planeH):
        row = []
        for x in range(upscaledPlaneW):
            srcX = -(1 << SUPERRES_SCALE_BITS) + initialSubpelX + x * stepX
            srcXPx = srcX >> SUPERRES_SCALE_BITS
            srcXSubpel = (srcX & SUPERRES_SCALE_MASK) >> SUPERRES_EXTRA_BITS
            s = 0
            for k in range(SUPERRES_FILTER_TAPS):
                sampleX = clip3(minX, maxX, srcXPx + (k - SUPERRES_FILTER_OFFSET))
                s += frame[y][sampleX] * Upscale_Filter[srcXSubpel][k]
            row.append(clip3(0, (1 << BitDepth) - 1, round2(s, FILTER_BITS)))
        out.append(row)
    return out


# ---- the fixture asserted by tests/av1_superres.tcyr (test_superres_mi_clamp) ----
# FrameWidth 13 (MiCols = 2 * ((13 + 7) >> 3) = 4: 16 luma / 8 chroma MI columns), UpscaledWidth 26,
# FrameHeight 2, 4:2:0, 8-bit. Visible luma columns 0..12 are the ramp 20 + 15x; the OVERHANG columns
# 13..15 are 250, 3, 200. Visible chroma columns 0..6 are 40 + 20x; the overhang column 7 is 0.
FW, UW, FH, MICOLS = 13, 26, 2, 4
LUMA_ROW = [20 + 15 * x for x in range(13)] + [250, 3, 200]
CHROMA_ROW = [40 + 20 * x for x in range(7)] + [0]


def fixture():
    luma = upscale_plane([LUMA_ROW] * FH, FW, UW, FH, MICOLS, 0, 0, 8)
    chroma = upscale_plane([CHROMA_ROW] * 1, FW, UW, FH, MICOLS, 1, 1, 8)
    # the same rows with the clamp at the VISIBLE width — what the pre-0.8.3 decoder computed
    vis_l = [LUMA_ROW[:13] + [LUMA_ROW[12]] * 3]
    vis_c = [CHROMA_ROW[:7] + [CHROMA_ROW[6]]]
    old_l = upscale_plane(vis_l, FW, UW, 1, MICOLS, 0, 0, 8)[0]
    old_c = upscale_plane(vis_c, FW, UW, 1, MICOLS, 1, 1, 8)[0]
    return luma[0], chroma[0], old_l, old_c


if __name__ == '__main__':
    print(check_table_against_spec())
    l, c, ol, oc = fixture()
    print('luma   (26):', l)
    print('chroma (13):', c)
    print('luma columns that differ under a visible-width clamp:', [i for i in range(26) if l[i] != ol[i]])
    print('chroma columns that differ under a visible-width clamp:', [i for i in range(13) if c[i] != oc[i]])
