#!/usr/bin/env python3
"""mv_ref.py -- the MV-prediction foundation: setup_global_mv (7.10.2.1), lower_mv_precision (7.10.2.10), and
Round2Signed (spec 4), spec-literal, cross-checked against libaom's own forms.

tests/av1_mv.tcyr pins these with 12 setup_global_mv cases, 9 lower_mv_precision cases and 6 Round2Signed values,
and tests/av1_intermode.tcyr reuses one (the ROTZOOM projection at mi_row 1 / mi_col 2). Their generator, a
scratchpad port (mv_ref.py, 0.7.62), was lost. This is its replacement, transcribed from the spec text:

    setup global mv (7.10.2.1):
      if ( ref == INTRA_FRAME || typ == IDENTITY ) { mv = 0, 0 }
      else if ( typ == TRANSLATION ) {
        mv[0] = gm_params[ref][0] >> (WARPEDMODEL_PREC_BITS - 3)
        mv[1] = gm_params[ref][1] >> (WARPEDMODEL_PREC_BITS - 3)
      } else {
        x = MiCol * MI_SIZE + bw / 2 - 1
        y = MiRow * MI_SIZE + bh / 2 - 1
        xc = (gm_params[ref][2] - (1 << WARPEDMODEL_PREC_BITS)) * x + gm_params[ref][3] * y + gm_params[ref][0]
        yc = gm_params[ref][4] * x + (gm_params[ref][5] - (1 << WARPEDMODEL_PREC_BITS)) * y + gm_params[ref][1]
        if ( allow_high_precision_mv ) { mv[0] = Round2Signed(yc, WARPEDMODEL_PREC_BITS - 3); mv[1] = .. xc .. }
        else { mv[0] = Round2Signed(yc, WARPEDMODEL_PREC_BITS - 2) * 2; mv[1] = .. xc .. }
      }
      lower_mv_precision( mv )

    lower precision (7.10.2.10): if allow_high_precision_mv, stop. Per component:
      force_integer_mv: a = Abs(v); aInt = (a + 3) >> 3; v = v > 0 ? aInt << 3 : -(aInt << 3)
      else: if (v & 1) v += v > 0 ? -1 : 1

(The translation case puts gm_params[0], the HORIZONTAL offset, into the row. libaom keeps that deliberately to
match the spec — crbug.com/aomedia/3328 — so the port does too.)

The SECOND source is libaom (`ref/aom`): gm_get_motion_vector (av1/common/mv.h), which rounds with
convert_to_trans_prec and snaps with integer_mv_precision (a `% 8` form, unlike the spec's (a + 3) >> 3), and
lower_mv_precision (av1/common/mvref_common.h), which tests is_integer BEFORE allow_hp. The port transcribes both
and ASSERTS them equal to the spec over every input a legal frame header can produce, and records the two places
they differ, both outside that domain:
  * allow_high_precision_mv = 1 with force_integer_mv = 1: the spec stops at allow_hp, libaom snaps. The uncompressed
    header forbids it (force_integer_mv = 1 sets allow_high_precision_mv = 0).
  * TRANSLATION with allow_high_precision_mv = 0 and an odd projected component: the spec lowers it, libaom returns
    it unchanged (it asserts the low bit is clear, which the gm_params syntax guarantees: translation-only offsets
    are coded at a precision that leaves it clear). The test's "translation lp 4/-2" case (40960, -24576 -> 5, -3)
    is such an input; drishti follows the spec there, which is the authority.
"""
import random
import sys

WARPEDMODEL_PREC_BITS = 16
MI_SIZE = 4
INTRA_FRAME = 0
IDENTITY, TRANSLATION, ROTZOOM, AFFINE = 0, 1, 2, 3
ONE = 1 << WARPEDMODEL_PREC_BITS
# Block_Width / Block_Height for the sizes the tests use: MiSize 3 = BLOCK_8X8, 6 = BLOCK_16X16
NUM_4X4_W = [1, 1, 2, 2, 2, 4, 4, 4, 8, 8, 8, 16, 16, 16, 32, 32, 1, 4, 2, 8, 4, 16]
NUM_4X4_H = [1, 2, 1, 2, 4, 2, 4, 8, 4, 8, 16, 8, 16, 32, 16, 32, 4, 1, 8, 2, 16, 4]


def round2(x, n):
    return (x + (1 << (n - 1))) >> n if n else x


def round2signed(x, n):
    """spec 4: Round2Signed(x, n) = x >= 0 ? Round2(x, n) : -Round2(-x, n)"""
    return round2(x, n) if x >= 0 else -round2(-x, n)


# ---- the spec ---------------------------------------------------------------------------------------------------
def lower_mv_precision(mv, allow_hp, force_int):
    if allow_hp:
        return list(mv)
    out = []
    for v in mv:
        if force_int:
            a_int = (abs(v) + 3) >> 3
            v = (a_int << 3) if v > 0 else -(a_int << 3)
        elif v & 1:
            v = v - 1 if v > 0 else v + 1
        out.append(v)
    return out


def setup_global_mv(ref, typ, gm, mi_row, mi_col, mi_size, allow_hp, force_int):
    if ref == INTRA_FRAME or typ == IDENTITY:
        mv = [0, 0]
    elif typ == TRANSLATION:
        mv = [gm[0] >> (WARPEDMODEL_PREC_BITS - 3), gm[1] >> (WARPEDMODEL_PREC_BITS - 3)]
    else:
        bw, bh = 4 * NUM_4X4_W[mi_size], 4 * NUM_4X4_H[mi_size]
        x = mi_col * MI_SIZE + bw // 2 - 1
        y = mi_row * MI_SIZE + bh // 2 - 1
        xc = (gm[2] - ONE) * x + gm[3] * y + gm[0]
        yc = gm[4] * x + (gm[5] - ONE) * y + gm[1]
        if allow_hp:
            mv = [round2signed(yc, WARPEDMODEL_PREC_BITS - 3), round2signed(xc, WARPEDMODEL_PREC_BITS - 3)]
        else:
            mv = [round2signed(yc, WARPEDMODEL_PREC_BITS - 2) * 2, round2signed(xc, WARPEDMODEL_PREC_BITS - 2) * 2]
    return lower_mv_precision(mv, allow_hp, force_int)


# ---- libaom -----------------------------------------------------------------------------------------------------
def c_mod(a, b):
    """C's %, which truncates toward zero"""
    return a - b * int(a / b) if a >= 0 else -((-a) % b)


def aom_integer_mv_precision(mv):
    out = []
    for v in mv:
        mod = c_mod(v, 8)
        if mod != 0:
            v -= mod
            if abs(mod) > 4:
                v += 8 if mod > 0 else -8
        out.append(v)
    return out


def aom_lower_mv_precision(mv, allow_hp, is_integer):
    if is_integer:
        return aom_integer_mv_precision(mv)
    out = list(mv)
    if not allow_hp:
        out = [v + (-1 if v > 0 else 1) if v & 1 else v for v in out]
    return out


def aom_round_power_of_two_signed(v, n):
    return -((-v + ((1 << n) >> 1)) >> n) if v < 0 else (v + ((1 << n) >> 1)) >> n


def aom_gm_get_motion_vector(typ, mat, allow_hp, mi_size, mi_col, mi_row, is_integer):
    if typ == IDENTITY:
        return [0, 0]
    if typ == TRANSLATION:
        res = [mat[0] >> (WARPEDMODEL_PREC_BITS - 3), mat[1] >> (WARPEDMODEL_PREC_BITS - 3)]
        return aom_integer_mv_precision(res) if is_integer else res
    x = mi_col * MI_SIZE + (4 * NUM_4X4_W[mi_size]) // 2 - 1
    y = mi_row * MI_SIZE + (4 * NUM_4X4_H[mi_size]) // 2 - 1
    xc = (mat[2] - ONE) * x + mat[3] * y + mat[0]
    yc = mat[4] * x + (mat[5] - ONE) * y + mat[1]

    def conv(c):
        if allow_hp:
            return aom_round_power_of_two_signed(c, WARPEDMODEL_PREC_BITS - 3)
        return aom_round_power_of_two_signed(c, WARPEDMODEL_PREC_BITS - 2) * 2
    res = [conv(yc), conv(xc)]
    return aom_integer_mv_precision(res) if is_integer else res


# ---- the test's known answers ------------------------------------------------------------------------------------
# tests/av1_mv.tcyr test_setup_global_mv: (name, typ, gm_params[0..5], allow_hp, force_int, ref, mi_col, mi_row,
# mi_size, expected (row, col)). ref 1 = LAST_FRAME.
GMV_KATS = [
    ("identity -> 0", IDENTITY, (0, 0, ONE, 0, 0, ONE), 1, 0, 1, 0, 0, 3, (0, 0)),
    ("intra ref -> 0", ROTZOOM, (99, 99, ONE, 0, 0, ONE), 1, 0, INTRA_FRAME, 0, 0, 3, (0, 0)),
    ("translation hp 5/-3", TRANSLATION, (40960, -24576, 0, 0, 0, 0), 1, 0, 1, 0, 0, 3, (5, -3)),
    ("translation lp 4/-2", TRANSLATION, (40960, -24576, 0, 0, 0, 0), 0, 0, 1, 0, 0, 3, (4, -2)),
    ("translation neg -7/9", TRANSLATION, (-57344, 73728, 0, 0, 0, 0), 1, 0, 1, 0, 0, 3, (-7, 9)),
    ("rotzoom hp 0/3", ROTZOOM, (0, 0, ONE + 8192, 0, 0, ONE), 1, 0, 1, 0, 0, 3, (0, 3)),
    ("rotzoom offset 0/11", ROTZOOM, (0, 0, ONE + 8192, 0, 0, ONE), 1, 0, 1, 2, 1, 3, (0, 11)),
    ("affine-identity -1/1", AFFINE, (4096, -8192, ONE, 0, 0, ONE), 1, 0, 1, 0, 0, 3, (-1, 1)),
    ("rotzoom lp 0/4", ROTZOOM, (0, 0, ONE + 8192, 0, 0, ONE), 0, 0, 1, 0, 0, 3, (0, 4)),
    ("rotzoom force_int 0/32", ROTZOOM, (0, 0, ONE + 40000, 0, 0, ONE), 0, 1, 1, 0, 0, 6, (0, 32)),
    ("full-rotzoom shear+scale 18/4", ROTZOOM, (0, 0, ONE + 8192, -8192, 8192, ONE + 8192), 1, 0, 1, 2, 1, 3,
     (18, 4)),
    ("neg-round Round2Signed -2/0", AFFINE, (0, -12288, ONE, 0, 0, ONE), 1, 0, 1, 0, 0, 3, (-2, 0)),
]
# test_lower_mv_precision: (row, col, allow_hp, force_int, expected row, expected col)
LOWER_KATS = [
    (5, -7, 1, 0, 5, -7), (5, -7, 0, 0, 4, -6), (1, -1, 0, 0, 0, 0), (4, -4, 0, 0, 4, -4),
    (10, -13, 0, 1, 8, -16), (12, -12, 0, 1, 8, -8), (13, -16, 0, 1, 16, -16), (0, 4, 0, 1, 0, 0),
    (16, -8, 0, 1, 16, -8),
]
# test_round2_signed: (x, n, Round2Signed)
ROUND2SIGNED_KATS = [(24576, 13, 3), (-24576, 13, -3), (0, 13, 0), (-3, 1, -2), (-1, 1, -1)]


def main():
    # 1. by hand. "rotzoom offset 0/11": BLOCK_8X8 at mi_col 2 / mi_row 1 -> x = 2*4 + 4 - 1 = 11, y = 1*4 + 4 - 1 =
    #    7; xc = 8192 * 11 = 90112, yc = 0; Round2Signed(90112, 13) = (90112 + 4096) >> 13 = 11. Swapping mi_row and
    #    mi_col (tests/av1_intermode.tcyr's H1 mutation) gives x = 7 -> col 7.
    assert setup_global_mv(1, ROTZOOM, (0, 0, ONE + 8192, 0, 0, ONE), 1, 2, 3, 1, 0) == [0, 11]
    assert setup_global_mv(1, ROTZOOM, (0, 0, ONE + 8192, 0, 0, ONE), 2, 1, 3, 1, 0) == [0, 7]
    #    "neg-round": yc = -12288 -> Round2Signed = -Round2(12288, 13) = -((12288 + 4096) >> 13) = -2, where the
    #    flooring Round2 gives (-12288 + 4096) >> 13 = -1.
    assert round2signed(-12288, 13) == -2 and round2(-12288, 13) == -1
    # 2. the test's known answers
    for (name, typ, gm, hp, fi, ref, mc, mr, ms, want) in GMV_KATS:
        got = setup_global_mv(ref, typ, gm, mr, mc, ms, hp, fi)
        assert tuple(got) == want, (name, got, want)
    for (r, c, hp, fi, er, ec) in LOWER_KATS:
        assert lower_mv_precision([r, c], hp, fi) == [er, ec], (r, c, hp, fi)
    for (x, n, want) in ROUND2SIGNED_KATS:
        assert round2signed(x, n) == want, (x, n)
    assert round2(-3, 1) == -1        # the test's contrast: the flooring Round2 differs from Round2Signed's -2
    # 3. libaom equals the spec on every legal input
    n_low = 0
    for v in range(-4096, 4097):
        for (hp, fi) in ((1, 0), (0, 0), (0, 1)):          # (1, 1) is illegal: force_integer_mv clears allow_hp
            assert lower_mv_precision([v, -v], hp, fi) == aom_lower_mv_precision([v, -v], hp, fi), (v, hp, fi)
            n_low += 1
    assert lower_mv_precision([5, 5], 1, 1) != aom_lower_mv_precision([5, 5], 1, 1)   # the illegal pair differs
    rng = random.Random(7102)
    n_gm = 0
    for _ in range(40000):
        typ = rng.choice((IDENTITY, TRANSLATION, ROTZOOM, AFFINE))
        hp, fi = rng.choice(((1, 0), (0, 0), (0, 1)))
        if typ == TRANSLATION:
            # gm_params syntax: translation-only offsets are coded at 1/8 (allow_hp) or 1/4 sample precision
            step = 1 << (WARPEDMODEL_PREC_BITS - (3 if hp else 2))
            mat = [rng.randrange(-4096, 4097) * step, rng.randrange(-4096, 4097) * step, ONE, 0, 0, ONE]
        else:
            a = rng.randrange(-8192, 8193) * 2
            b = rng.randrange(-8192, 8193) * 2
            mat = [rng.randrange(-(1 << 22), 1 << 22), rng.randrange(-(1 << 22), 1 << 22), ONE + a, b,
                   -b if typ == ROTZOOM else rng.randrange(-8192, 8193) * 2,
                   ONE + a if typ == ROTZOOM else ONE + rng.randrange(-8192, 8193) * 2]
        ms = rng.randrange(22)
        mr = rng.randrange(256)
        mc = rng.randrange(256)
        spec = setup_global_mv(1, typ, mat, mr, mc, ms, hp, fi)
        aom = aom_gm_get_motion_vector(typ, mat, hp, ms, mc, mr, fi)
        assert spec == aom, (typ, mat, hp, fi, ms, mr, mc, spec, aom)
        n_gm += 1
    # ...and the one test case outside libaom's domain is the documented one
    assert aom_gm_get_motion_vector(TRANSLATION, (40960, -24576, 0, 0, 0, 0), 0, 3, 0, 0, 0) == [5, -3]
    print('mv_ref: all %d setup_global_mv, %d lower_mv_precision and %d Round2Signed known answers of '
          'tests/av1_mv.tcyr reproduced; libaom equals the spec on %d precision and %d projection inputs -- OK'
          % (len(GMV_KATS), len(LOWER_KATS), len(ROUND2SIGNED_KATS), n_low, n_gm))
    return 0


if __name__ == '__main__':
    sys.exit(main())
