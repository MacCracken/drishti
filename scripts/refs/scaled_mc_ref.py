#!/usr/bin/env python3
# scaled_mc_ref.py — spec-literal reference for AV1 SCALED-reference motion compensation:
# the 7.11.3.4 block inter prediction process driven by a non-unit step from 7.11.3.3.
# The oracle for drishti's av1_mc_put_8tap_scaled. Never back-derived from the Cyrius.
#
# Like bilinear_mc_ref.py this is written in the **spec** convention (16 phases, rows summing
# to 128, spec InterRound0/InterRound1) while drishti carries dav1d's halved 15-phase table
# with every round one bit smaller — so agreement is a CROSS-CONVENTION result, not a
# restatement. It imports the geometry from scaled_geom_ref (7.11.3.3) and the table from
# bilinear_mc_ref (machine-generated from the digest-pinned spec markdown), so there is
# exactly one transcription of each.
#
# Transcribed verbatim from 08.decoding.process.md md5 51249ad97e9fd97dc3b0dc0e14de83b0:
#
#   for ( r = 0; r < intermediateHeight; r++ )
#     for ( c = 0; c < w; c++ ) {
#       s = 0
#       p = x + xStep * c
#       for ( t = 0; t < 8; t++ )
#         s += Subpel_Filters[ interpFilter ][ (p >> 6) & SUBPEL_MASK ][ t ] *
#              ref[ plane ][ Clip3( 0, lastY, (y >> 10) + r - 3 ) ]
#                          [ Clip3( 0, lastX, (p >> 10) + t - 3 ) ]
#       intermediate[ r ][ c ] = Round2(s, InterRound0)
#     }
#
#   for ( r = 0; r < h; r++ )
#     for ( c = 0; c < w; c++ ) {
#       s = 0
#       p = (y & 1023) + yStep * r
#       for ( t = 0; t < 8; t++ )
#         s += Subpel_Filters[ interpFilter ][ (p >> 6) & SUBPEL_MASK ][ t ] *
#              intermediate[ (p >> 10) + t ][ c ]
#       pred[ r ][ c ] = Round2(s, InterRound1)
#     }
#
# NOTE the two asymmetries that are easy to get wrong and are pinned by dedicated mutations:
#   - the horizontal pass uses the FULL startY (its integer part is the row origin, via
#     (y >> 10) + r - 3), while the vertical pass uses only (startY & 1023) — the integer
#     part has already been consumed.
#   - the `- 3` tap offset appears in the HORIZONTAL source column only. The vertical pass
#     indexes intermediate[(p >> 10) + t] with no -3, because the intermediate array already
#     starts 3 rows above the block.

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bilinear_mc_ref import (SPEC_SUBPEL_FILTERS, filter_idx_spec, inter_rounds, fill_val,
                             clip3)
from scaled_geom_ref import (SPEC_MD5, round2, scale_factor, scaled_start,
                             scaled_step, scaled_mid_h)


def clip1(v, bd):
    return clip3(0, (1 << bd) - 1, v)


def make_plane(p, pw, ph, bd):
    return [[fill_val(p, r, c, bd) for c in range(pw)] for r in range(ph)]


def plane_dims(w, h, plane, subx, suby):
    if plane == 0:
        return w, h
    return (w + subx) >> subx, (h + suby) >> suby


def put_8tap_scaled(plane_data, lastx, lasty, startx, starty, stepx, stepy,
                    w, h, filt_x, filt_y, bd, compound=0):
    """Spec 7.11.3.4 with a non-unit step. Returns list[h][w]."""
    r0, r1, _ = inter_rounds(bd, compound)
    hset = filter_idx_spec(filt_x, w)
    vset = filter_idx_spec(filt_y, h)
    inter_h = scaled_mid_h(h, stepy)

    inter = [[0] * w for _ in range(inter_h)]
    for r in range(inter_h):
        sy = clip3(0, lasty, (starty >> 10) + r - 3)
        for c in range(w):
            p = startx + stepx * c
            ftab = SPEC_SUBPEL_FILTERS[hset][(p >> 6) & 15]
            s = 0
            for t in range(8):
                sx = clip3(0, lastx, (p >> 10) + t - 3)
                s += ftab[t] * plane_data[sy][sx]
            inter[r][c] = round2(s, r0)

    out = [[0] * w for _ in range(h)]
    for r in range(h):
        p = (starty & 1023) + stepy * r
        ftab = SPEC_SUBPEL_FILTERS[vset][(p >> 6) & 15]
        for c in range(w):
            s = 0
            for t in range(8):
                s += ftab[t] * inter[(p >> 10) + t][c]
            v = round2(s, r1)
            out[r][c] = v if compound else clip1(v, bd)
    return out


def run_case(rw, rh, dw, dh, planes, subx, suby, bd, plane, x, y, w, h,
             mvr, mvc, fx, fy, compound=0):
    """Predict from a (rw x rh) reference into a (dw x dh) current frame's coordinate space."""
    sub_x = subx if plane > 0 else 0
    sub_y = suby if plane > 0 else 0
    rpw, rph = plane_dims(rw, rh, plane, subx, suby)
    data = make_plane(plane, rpw, rph, bd)

    # The scale factors are LUMA-derived (RefUpscaledWidth vs FrameWidth) and apply to every
    # plane; subsampling enters only through origX's (2*mv) >> subX and through lastX/lastY.
    xs = scale_factor(rw, dw)
    ys = scale_factor(rh, dh)
    stx, sty = scaled_step(xs), scaled_step(ys)
    sx = scaled_start(x, mvc, sub_x, xs)
    sy = scaled_start(y, mvr, sub_y, ys)
    lastx, lasty = rpw - 1, rph - 1

    out = put_8tap_scaled(data, lastx, lasty, sx, sy, stx, sty, w, h, fx, fy, bd, compound)
    return out, (xs, ys, stx, sty, sx, sy, lastx, lasty)


def checksum(block):
    ck = 0
    i = 0
    for row in block:
        for v in row:
            ck += (i + 1) * v
            i += 1
    return ck


# (name, rw, rh, dw, dh, planes, subx, suby, bd, plane, x, y, w, h, mvr, mvc, fx, fy, comp)
CASES = [
    # 2x DOWNSCALE (step 512) and 2x UPSCALE at the conformance bound (step 2048).
    ("s01 2x-down luma",      32, 32, 64, 64, 1, 0, 0,  8, 0,  8,  6,  8,  8,   5,  -3, 0, 0, 0),
    ("s02 2x-up luma",        64, 64, 32, 32, 1, 0, 0,  8, 0,  8,  6,  8,  8,   5,  -3, 0, 0, 0),
    # h=128 at step 2048 -> intermediateHeight is exactly 262, the buffer's tight bound.
    ("s03 2x-up h128 maxmid", 64, 64, 32, 32, 1, 0, 0,  8, 0,  0,  0,  8,128,   0,   0, 0, 0, 0),
    # ASYMMETRIC: different x and y scales on a NON-SQUARE frame. A uniform-scale fixture
    # lets a stepX/stepY or startX/startY swap pass green.
    ("s04 asymmetric",        40, 24, 20, 18, 1, 0, 0,  8, 0,  4,  3,  8,  8,  11,  19, 0, 0, 0),
    # NEGATIVE start: the block sits at the origin with a large negative MV, so the source
    # window runs off the top-left and the per-tap Clip3 does real work.
    ("s05 neg clamp",         48, 48, 32, 32, 1, 0, 0,  8, 0,  0,  0,  8,  8, -40, -40, 0, 0, 0),
    # PAST the far edge: drives the right/bottom clamp.
    ("s06 far clamp",         48, 48, 32, 32, 1, 0, 0,  8, 0, 24, 24,  8,  8, 200, 200, 0, 0, 0),
    # 4:2:0 CHROMA — subX/subY change both origX and lastX.
    ("s07 chroma 420",        40, 24, 20, 18, 3, 1, 1,  8, 1,  2,  2,  4,  4,   7,  -5, 0, 0, 0),
    # 10- and 12-bit (12-bit moves InterRound0 to 5 and InterRound1 to 9).
    ("s08 10-bit",            32, 32, 16, 16, 1, 0, 0, 10, 0,  4,  4,  8,  8,  -3,   5, 0, 0, 0),
    ("s09 12-bit",            32, 32, 16, 16, 1, 0, 0, 12, 0,  4,  4,  8,  8,  -3,   5, 0, 0, 0),
    # non-default filters, incl. mixed axes and BILINEAR under scaling.
    ("s10 sharp",             32, 32, 64, 64, 1, 0, 0,  8, 0,  8,  6,  8,  8,   5,  -3, 2, 2, 0),
    ("s11 mixed filters",     40, 24, 20, 18, 1, 0, 0,  8, 0,  4,  3,  8,  8,  11,  19, 1, 2, 0),
    ("s12 bilinear scaled",   40, 24, 20, 18, 1, 0, 0,  8, 0,  4,  3,  8,  8,  11,  19, 3, 3, 0),
    # narrow block: the w<=4 4-tap remap must still apply under scaling.
    ("s13 w4 remap",          32, 32, 64, 64, 1, 0, 0,  8, 0,  8,  6,  4,  8,   5,  -3, 0, 0, 0),
    # COMPOUND intermediate (no Clip1, InterRound1 = 7).
    ("s14 compound",          32, 32, 64, 64, 1, 0, 0,  8, 0,  8,  6,  8,  8,   5,  -3, 0, 0, 1),
    # 16x-smaller reference (step 64) — the other conformance bound.
    ("s15 16x-smaller",        4,  4, 64, 64, 1, 0, 0,  8, 0,  8,  6,  8,  8,   5,  -3, 0, 0, 0),
]


def main():
    print("# scaled_mc_ref.py — spec 7.11.3.4 with a non-unit step, spec md5 %s" % SPEC_MD5)
    print("# known answers for tests/av1_mc_driver.tcyr (checksum, first, last):")
    for row in CASES:
        (name, rw, rh, dw, dh, planes, subx, suby, bd, plane, x, y, w, h,
         mvr, mvc, fx, fy, comp) = row
        out, geom = run_case(rw, rh, dw, dh, planes, subx, suby, bd, plane, x, y, w, h,
                             mvr, mvc, fx, fy, comp)
        xs, ys, stx, sty, sx, sy, lastx, lasty = geom
        print("#   %-22s ck=%-10d first=%-6d last=%-6d  "
              "[stepX=%d stepY=%d startX=%d startY=%d lastX=%d lastY=%d midH=%d]"
              % (name, checksum(out), out[0][0], out[h - 1][w - 1],
                 stx, sty, sx, sy, lastx, lasty, scaled_mid_h(h, sty)))

    print("\n# .tcyr rows:")
    for row in CASES:
        (name, rw, rh, dw, dh, planes, subx, suby, bd, plane, x, y, w, h,
         mvr, mvc, fx, fy, comp) = row
        out, _ = run_case(rw, rh, dw, dh, planes, subx, suby, bd, plane, x, y, w, h,
                          mvr, mvc, fx, fy, comp)

        def cy(v):
            return str(v) if v >= 0 else "0 - %d" % -v

        print('    mcs_mc("%s", %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %s, %s, '
              '%d, %d, %d, %d, %d, %d);'
              % (name, rw, rh, dw, dh, planes, subx, suby, bd, plane, x, y, w, h,
                 cy(mvr), cy(mvc), fx, fy, comp,
                 checksum(out), out[0][0], out[h - 1][w - 1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
