#!/usr/bin/env python3
"""mc_put8tap_ref.py -- the put_8tap motion-compensation kernel, spec-literal (7.11.3.4) AND dav1d's form.

tests/av1_mc_kernel.tcyr pins av1_mc_put_8tap with known answers. The first six came from a scratchpad port of
dav1d's put_8tap_c alone (mc_put8tap.py), since lost; and a single-implementation port was never the right
oracle (CLAUDE.md: spec-first, multi-source). This port has two independent transcriptions:

  * SPEC: 7.11.3.4's block inter prediction over the unscaled geometry, in the spec's convention: Subpel_Filters
    with 16 phases summing to 128, both passes ALWAYS run (phase 0 is the identity row), InterRound0 = 3 (5 at
    12 bit) on the horizontal pass, InterRound1 = 11 (9 at 12 bit) on the vertical one, then Clip1 (the non-compound
    InterPostRound is 0). The table and the set-selection rule come from bilinear_mc_ref.py, which machine-generates
    the table from the spec markdown.
  * DAV1D: put_8tap_c from src/mc_tmpl.c, transcribed branch for branch: copy / H-only / V-only / H+V, the halved
    15-phase table (mc_subpel_ref.derived_table, equal to dav1d's own entry for entry), intermediate_bits = 4
    (14 - BitDepth above 8 bit), the H-only rounding constant 32 + ((1 << (6 - ib)) >> 1), and GET_H_FILTER /
    GET_V_FILTER's w <= 4 / h <= 4 set selection.

The port ASSERTS the two equal on every phase pair x every filter-type pair for 8x8 and 4x4 blocks at 8 bit, and on
a seeded sweep of sizes and bit depths. It then asserts the spec form reproduces the test's nine known answers, two
pixels derived by hand below. The last three were added here: dav1d's H-only rounding constant survived a mutation
(34 -> 32) against the first six, so three cases on its boundary now pin it, and the port checks they catch every
wrong value (see KATS). drishti's kernel is dav1d's form, so the equality is what makes the test's goldens spec answers.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bilinear_mc_ref import SPEC_SUBPEL_FILTERS, filter_idx_spec, inter_rounds, round2, clip1   # noqa: E402
from mc_subpel_ref import derived_table                                                         # noqa: E402

DAV1D = derived_table()   # [6][15][8], dav1d / drishti convention


def spec_put(plane, x, y, w, h, mx, my, ftype, bd):
    """7.11.3.4 two passes at phases mx / my (0..15) for the w x h block whose top-left is (x, y); ftype = h | v << 2
    in the spec / dav1d filter numbering (0 REGULAR, 1 SMOOTH, 2 SHARP)"""
    r0, r1, post = inter_rounds(bd, 0)
    assert post == 0
    fh = SPEC_SUBPEL_FILTERS[filter_idx_spec(ftype & 3, w)][mx]
    fv = SPEC_SUBPEL_FILTERS[filter_idx_spec(ftype >> 2, h)][my]
    inter = [[round2(sum(fh[t] * plane[y + r - 3][x + c + t - 3] for t in range(8)), r0) for c in range(w)]
             for r in range(h + 7)]
    return [[clip1(round2(sum(fv[t] * inter[r + t][c] for t in range(8)), r1), bd) for c in range(w)]
            for r in range(h)]


def dav1d_put(plane, x, y, w, h, mx, my, ftype, bd, rnd_h=None):
    """dav1d put_8tap_c (src/mc_tmpl.c), branch for branch; rnd_h overrides the H-only rounding constant, so the
    port can show a known answer tells the right constant from a wrong one"""
    ib = 4 if bd <= 10 else 14 - bd
    if rnd_h is None:
        rnd_h = 32 + ((1 << (6 - ib)) >> 1)
    fh = None
    fv = None
    if mx:
        fh = DAV1D[ftype & 3][mx - 1] if w > 4 else DAV1D[3 + (ftype & 1)][mx - 1]
    if my:
        fv = DAV1D[ftype >> 2][my - 1] if h > 4 else DAV1D[3 + ((ftype >> 2) & 1)][my - 1]

    def f8(row_of, F):   # FILTER_8TAP over the 8 samples row_of(-3..4)
        return sum(F[t] * row_of(t - 3) for t in range(8))

    def rnd(v, sh):     # (v + ((1 << sh) >> 1)) >> sh, an arithmetic shift
        return (v + ((1 << sh) >> 1)) >> sh

    pmax = (1 << bd) - 1
    out = [[0] * w for _ in range(h)]
    if fh and fv:
        mid = [[rnd(f8(lambda k, rr=r, cc=c: plane[y + rr - 3][x + cc + k], fh), 6 - ib) for c in range(w)]
               for r in range(h + 7)]
        for r in range(h):
            for c in range(w):
                out[r][c] = min(max(rnd(f8(lambda k, rr=r, cc=c: mid[rr + 3 + k][cc], fv), 6 + ib), 0), pmax)
    elif fh:
        for r in range(h):
            for c in range(w):
                v = (f8(lambda k, rr=r, cc=c: plane[y + rr][x + cc + k], fh) + rnd_h) >> 6
                out[r][c] = min(max(v, 0), pmax)
    elif fv:
        for r in range(h):
            for c in range(w):
                out[r][c] = min(max(rnd(f8(lambda k, rr=r, cc=c: plane[y + rr + k][x + cc], fv), 6), 0), pmax)
    else:
        for r in range(h):
            for c in range(w):
                out[r][c] = plane[y + r][x + c]
    return out


def checksum(block):
    """position-weighted, row-major: sum v * (i + 1) — mc_checksum() in the test"""
    return sum(v * (i + 1) for i, v in enumerate(val for row in block for val in row))


def plane16():
    """the test's plane: src[r][c] = (r * 37 + c * 11 + 20) & 255, 16 x 16"""
    return [[(r * 37 + c * 11 + 20) & 255 for c in range(16)] for r in range(16)]


def plane16_nl(mask):
    """the test's nonlinear plane: src[r][c] = (r * 592 + c * 176 + 320 + r * c * 7) & mask, 16 x 16 (mask 255 for
    8 bit, 4095 for 12). Unlike plane16, whose rows are linear so a block's sums share one residue mod 64, its sums
    spread over several — which the rounding cases need."""
    return [[(r * 592 + c * 176 + 320 + r * c * 7) & mask for c in range(16)] for r in range(16)]


# tests/av1_mc_kernel.tcyr test_put_8tap: (name, plane, bit depth, w, h, mx, my, filter_type, checksum,
# {index: pixel}) — plane 'lin' is plane16, 'nl8' / 'nl12' are plane16_nl(255 / 4095).
#
# The last three pin dav1d's H-only rounding constant, rnd = 34 at 8 / 10 bit and 40 at 12 (intermediate_bits 2):
# the first six never reach a sum where it matters, and 0.8.5's mutation of it to 32 survived them. A wrong rnd' is
# visible only at a sum s whose residue s mod 64 lies between 64 - max(rnd, rnd') and 64 - min(rnd, rnd') - 1, so a
# case tells rnd from EVERY wrong value exactly when its sums include the residues 63 - rnd and 64 - rnd (29 and 30
# at 8 bit, 23 and 24 at 12). The mx6 case has only residue 30 — it catches any rnd' < 34, with a hand derivation;
# the two nonlinear-plane cases have both, and main() checks all 63 wrong constants change each.
KATS = [
    ("integer 8x8", 'lin', 8, 8, 8, 0, 0, 0, 301936, {0: 212}),
    ("H-only 8x8 REGULAR mx8", 'lin', 8, 8, 8, 8, 0, 0, 298113, {0: 218}),
    ("V-only 8x8 REGULAR my8", 'lin', 8, 8, 8, 0, 8, 0, 289226, {}),
    ("H+V 8x8 REGULAR mx8my8", 'lin', 8, 8, 8, 8, 8, 0, 281124, {0: 184, 27: 124, 63: 50}),
    ("H+V 4x4 (w<=4 set) mx5my11", 'lin', 8, 4, 4, 5, 11, 0, 11391, {}),
    ("H+V 8x8 SHARP mx3my13", 'lin', 8, 8, 8, 3, 13, 10, 274009, {}),
    ("H-only 8x8 REGULAR mx6 (residue 30)", 'lin', 8, 8, 8, 6, 0, 0, 300354, {0: 217}),
    ("H-only 8x8 REGULAR mx15 (residues 29, 30)", 'nl8', 8, 8, 8, 15, 0, 0, 268033, {24: 218, 48: 47}),
    ("H-only 8x8 SHARP mx15 12-bit (residues 23, 24)", 'nl12', 12, 8, 8, 15, 0, 2, 4032277, {24: 1461, 32: 2088}),
]
# (case, the wrong constants it must catch)
ROUNDING_KATS = [(KATS[6], range(34)), (KATS[7], [c for c in range(64) if c != 34]),
                 (KATS[8], [c for c in range(64) if c != 40])]
# by hand, the H-only pixel 0 (REGULAR half-pel, 8 bit): row 4 of the plane is 168 + 11c (0 at c = 8, where it wraps);
# the taps read c = 1..8: 179 190 201 212 223 234 245 0; the spec's phase-8 REGULAR row is [0, 2, -14, 76, 76, -14,
# 2, 0]: 380 - 2814 + 16112 + 16948 - 3276 + 490 = 27840; Round2(27840, 3) = 3480; the vertical pass at phase 0:
# Round2(128 * 3480, 11) = Round2(445440, 11) = 218 (446464 / 2048, exactly).
# by hand, the mx6 pixel 0: the same eight samples against the spec's phase-6 REGULAR row [0, 2, -16, 94, 58, -12, 2,
# 0]: 380 - 3216 + 19928 + 12934 - 2808 + 490 = 27708; Round2(27708, 3) = 3464; Round2(128 * 3464, 11) = 217
# (444416 / 2048, exactly). dav1d sums the halved row to 13854, which is 30 mod 64: (13854 + 34) >> 6 = 217, but
# (13854 + 32) >> 6 = 216 — the case the rounding constant decides.


def main():
    # 1. the two transcriptions agree: every phase pair x filter-type pair, 8x8 and 4x4, 8 bit
    rng = random.Random(8058)
    big = [[rng.randrange(256) for _ in range(28)] for _ in range(28)]
    n = 0
    for (w, h) in ((8, 8), (4, 4)):
        for fh in range(3):
            for fv in range(3):
                for mx in range(16):
                    for my in range(16):
                        ft = fh | (fv << 2)
                        assert spec_put(big, 6, 6, w, h, mx, my, ft, 8) == dav1d_put(big, 6, 6, w, h, mx, my, ft, 8), \
                            (w, h, mx, my, ft)
                        n += 1
    # ...and a seeded sweep of sizes and depths
    for _ in range(1500):
        bd = rng.choice((8, 10, 12))
        w = rng.choice((2, 4, 8, 16))
        h = rng.choice((2, 4, 8, 16))
        pl = [[rng.randrange(1 << bd) for _ in range(w + 12)] for _ in range(h + 12)]
        mx = rng.randrange(16)
        my = rng.randrange(16)
        ft = rng.randrange(3) | (rng.randrange(3) << 2)
        assert spec_put(pl, 4, 4, w, h, mx, my, ft, bd) == dav1d_put(pl, 4, 4, w, h, mx, my, ft, bd), (bd, w, h)
        n += 1
    # 2. the spec form reproduces the test's known answers
    planes = {'lin': plane16(), 'nl8': plane16_nl(255), 'nl12': plane16_nl(4095)}
    s0 = sum(f * v for f, v in zip(DAV1D[0][5], planes['lin'][4][1:9]))
    assert s0 == 13854 and s0 % 64 == 30 and (s0 + 34) >> 6 == 217 and (s0 + 32) >> 6 == 216
    for (name, pl, bd, w, h, mx, my, ft, cs, px) in KATS:
        out = spec_put(planes[pl], 4, 4, w, h, mx, my, ft, bd)
        flat = [v for row in out for v in row]
        assert checksum(out) == cs, (name, checksum(out), cs)
        for i, v in px.items():
            assert flat[i] == v, (name, i, flat[i], v)
    # 3. the rounding cases have teeth: each one's answer changes under every wrong H-only constant it claims
    for ((name, pl, bd, w, h, mx, my, ft, cs, px), wrongs) in ROUNDING_KATS:
        right = spec_put(planes[pl], 4, 4, w, h, mx, my, ft, bd)
        for wrong in wrongs:
            assert dav1d_put(planes[pl], 4, 4, w, h, mx, my, ft, bd, rnd_h=wrong) != right, (name, wrong)
    print('mc_put8tap_ref: spec 7.11.3.4 == dav1d put_8tap_c on %d blocks; all %d known answers of '
          'tests/av1_mc_kernel.tcyr reproduced; the three rounding cases shown to catch every wrong constant they '
          'claim -- OK' % (n, len(KATS)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
