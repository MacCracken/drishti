#!/usr/bin/env python3
# warp_estimation_ref.py — spec-literal reference port for AV1 warp_estimation
# (spec 7.11.3.8) + resolve_divisor (7.11.3.7) + the Div_Lut table.
#
# This is the KNOWN-ANSWER oracle for drishti's av1_warp_estimation. It is
# derived from the AV1 spec and cross-checked (spec + libaom + dav1d) via the
# multi-source reconciliation; it must NEVER be back-derived from the Cyrius.
#
# Reconciled facts (see docs/development/state.md / the 0.7.93 bite notes):
#   * Div_Lut[i] = round(2^22 / (256+i)), i=0..256 (257 entries). Anchored:
#     Div_Lut[0]=16384=2^14, Div_Lut[256]=8192=2^13 (both exact); no exact half
#     ever occurs so rounding is deterministic.
#   * The find_warp_samples CandList is ALREADY in 1/8-pel: each entry is
#     [midY*8, midX*8, midY*8+mv[0], midX*8+mv[1]] (see warp_samples_ref.py).
#     So NO extra *8 is applied inside warp_estimation.
#   * LS macros (LS_STEP=2, down-shift 2): LS_SQUARE(a)=(a+1)^2+1,
#     LS_PRODUCT1(a,b)=(a+1)(b+1), LS_PRODUCT2(a,b)=(a+1)(b+1)+1. The +1
#     Tikhonov regularization is NORMATIVE (keeps A PSD / invertible).
#   * Bx[1]/By[0] use PRODUCT1 (unbiased); Bx[0]/By[1] use PRODUCT2 (biased) —
#     forced by the identity-warp landing (zero motion -> wm=(.,.,1,0,0,1)).
#   * det==0 is the SOLE LocalValid=0 exit of 7.11.3.8.
#
# DEFERRED (NOT modelled here — un-witnessable without a conformance vector):
#   * The libaom LS_MAT_MIN/MAX accumulator clamp (existence/bounds unverified).
#   * The shear-realizability rejection (get_shear_params, ~7.11.3.6) — a
#     SEPARATE process run AFTER warp_estimation, not a LocalValid exit here.

DIV_LUT_BITS = 8
DIV_LUT_PREC_BITS = 14
DIV_LUT_NUM = 256                    # table has DIV_LUT_NUM+1 = 257 entries (0..256)

WARPEDMODEL_PREC_BITS = 16
WARPEDMODEL_TRANS_CLAMP = 1 << 23
WARPEDMODEL_NONDIAG_CLAMP = 1 << 13  # 8192; the clamp half-window is CLAMP-1 = 8191
LS_MV_MAX = 256
LS_STEP = 2
MI_SIZE = 4


def gen_div_lut():
    # Div_Lut[i] = round(2^(PREC+BITS) / (2^BITS + i)) via integer round-half-up.
    # No exact half ever occurs (2^23 has no odd factor > 1), so this is exact.
    num = 1 << (DIV_LUT_PREC_BITS + DIV_LUT_BITS)     # 2^22 = 4194304
    lut = []
    for i in range(DIV_LUT_NUM + 1):                  # 0..256
        d = (1 << DIV_LUT_BITS) + i                   # 256..512
        lut.append((num + (d >> 1)) // d)             # round-half-up, exact
    return lut


DIV_LUT = gen_div_lut()


def floor_log2(x):
    # matches dr_floor_log2: MSB index of x (x >= 1)
    s = 0
    v = x
    while v != 0:
        v >>= 1
        s += 1
    return s - 1


def round2(x, n):
    # matches av1_round2 (arithmetic; here x >= 0)
    if n == 0:
        return x
    return (x + (1 << (n - 1))) >> n


def round2_signed(x, n):
    # matches av1_round2_signed: round-half-AWAY-from-zero
    if x >= 0:
        return round2(x, n)
    return -round2(-x, n)


def resolve_divisor(d):
    # spec 7.11.3.7; caller guarantees d != 0. Returns (divShift, divFactor).
    ad = abs(d)
    n = floor_log2(ad)
    e = ad - (1 << n)
    if n > DIV_LUT_BITS:
        f = round2(e, n - DIV_LUT_BITS)
    else:
        f = e << (DIV_LUT_BITS - n)
    assert 0 <= f <= DIV_LUT_NUM, f
    div_shift = n + DIV_LUT_PREC_BITS
    div_factor = -DIV_LUT[f] if d < 0 else DIV_LUT[f]
    return (div_shift, div_factor)


def ls_square(a):
    return (a * a * 4 + a * 4 * LS_STEP + LS_STEP * LS_STEP * 2) >> 2


def ls_product1(a, b):
    return (a * b * 4 + (a + b) * 2 * LS_STEP + LS_STEP * LS_STEP) >> 2


def ls_product2(a, b):
    return (a * b * 4 + (a + b) * 2 * LS_STEP + LS_STEP * LS_STEP * 2) >> 2


def clip3(lo, hi, v):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def warp_estimation(cand, num, mi_row, mi_col, w4, h4, mvr, mvc):
    # cand: list of [srcY, srcX, dstY, dstX] already in 1/8-pel (num used).
    # Returns (valid, [wm0..wm5]). On invalid, wm is left as identity.
    wm = [0, 0, 1 << WARPEDMODEL_PREC_BITS, 0, 0, 1 << WARPEDMODEL_PREC_BITS]
    mid_y = mi_row * MI_SIZE + h4 * 2 - 1
    mid_x = mi_col * MI_SIZE + w4 * 2 - 1
    suy = mid_y * 8
    sux = mid_x * 8
    duy = suy + mvr
    dux = sux + mvc
    a00 = a01 = a11 = 0
    bx0 = bx1 = by0 = by1 = 0
    for i in range(num):
        sy = cand[i][0] - suy
        sx = cand[i][1] - sux
        dy = cand[i][2] - duy
        dx = cand[i][3] - dux
        if abs(sx - dx) < LS_MV_MAX and abs(sy - dy) < LS_MV_MAX:
            a00 += ls_square(sx)
            a01 += ls_product1(sx, sy)
            a11 += ls_square(sy)
            bx0 += ls_product2(sx, dx)
            bx1 += ls_product1(sy, dx)
            by0 += ls_product1(sx, dy)
            by1 += ls_product2(sy, dy)
    det = a00 * a11 - a01 * a01
    if det == 0:
        return (0, wm)
    div_shift, div_factor = resolve_divisor(det)
    div_shift -= WARPEDMODEL_PREC_BITS
    if div_shift < 0:
        div_factor <<= (-div_shift)
        div_shift = 0
    one = 1 << WARPEDMODEL_PREC_BITS

    def mult(v):
        return round2_signed(v * div_factor, div_shift)

    def diag(v):
        return clip3(one - WARPEDMODEL_NONDIAG_CLAMP + 1,
                     one + WARPEDMODEL_NONDIAG_CLAMP - 1, mult(v))

    def nondiag(v):
        return clip3(-WARPEDMODEL_NONDIAG_CLAMP + 1,
                     WARPEDMODEL_NONDIAG_CLAMP - 1, mult(v))

    wm[2] = diag(a11 * bx0 - a01 * bx1)
    wm[3] = nondiag(a00 * bx1 - a01 * bx0)
    wm[4] = nondiag(a11 * by0 - a01 * by1)
    wm[5] = diag(a00 * by1 - a01 * by0)
    vx = mvc * (1 << (WARPEDMODEL_PREC_BITS - 3)) - (mid_x * (wm[2] - one) + mid_y * wm[3])
    vy = mvr * (1 << (WARPEDMODEL_PREC_BITS - 3)) - (mid_x * wm[4] + mid_y * (wm[5] - one))
    wm[0] = clip3(-WARPEDMODEL_TRANS_CLAMP, WARPEDMODEL_TRANS_CLAMP - 1, vx)
    wm[1] = clip3(-WARPEDMODEL_TRANS_CLAMP, WARPEDMODEL_TRANS_CLAMP - 1, vy)
    return (1, wm)


# ------------------------------------------------------------------ vectors
def cand_of(cy, cx, smvr, smvc):
    # a sample block whose center is pixel (cy, cx) carrying motion (smvr, smvc)
    return [cy * 8, cx * 8, cy * 8 + smvr, cx * 8 + smvc]


def main():
    # --- Div_Lut digest + the 9 anchored spot values ---
    ck = 0
    for i, v in enumerate(DIV_LUT):
        ck = (ck + (i + 1) * v) & 0x7FFFFFFFFFFFFFFF
    print("DIV_LUT len=%d sum=%d checksum=%d" % (len(DIV_LUT), sum(DIV_LUT), ck))
    for i in (0, 1, 2, 3, 64, 128, 192, 255, 256):
        print("  Div_Lut[%3d] = %d" % (i, DIV_LUT[i]))

    # --- resolve_divisor boundary witnesses (f=0, f=256, small n, negative) ---
    print("resolve_divisor:")
    for d in (1, 7, 255, 256, 511, 512, 1023, -1023, 4194304):
        ds, df = resolve_divisor(d)
        print("  D=%d -> divShift=%d divFactor=%d" % (d, ds, df))

    # --- warp_estimation KAT cases ---
    # A: pure translation (all samples share the block MV -> identity 2x2).
    A = [cand_of(23, 31, 16, 24), cand_of(23, 39, 16, 24), cand_of(39, 23, 16, 24)]
    # B: a genuine affine (sample MV varies with position -> non-identity).
    B = [cand_of(23, 31, 16, 24), cand_of(23, 55, 40, 24),
         cand_of(55, 31, 16, 72), cand_of(55, 55, 40, 72)]
    # C: guard witness — sample[2] has a delta-MV >= LS_MV_MAX (dropped by the
    #    |sx-dx|<256 guard). Expected output must EQUAL the 2-sample prefix.
    C = [cand_of(23, 31, 16, 24), cand_of(23, 55, 40, 24),
         cand_of(55, 31, 16, 24 + 300)]   # smvc off by 300/8-pel -> |sx-dx|>=256
    C2 = C[:2]
    # E: extreme zoom to engage the diag clamp (wm[2] pushed past 73727).
    E = [cand_of(20, 20, 0, -96), cand_of(20, 60, 0, 96),
         cand_of(60, 20, -96, 0), cand_of(60, 60, 96, 0)]
    # F: a MILD affine (rotation+shear) whose four 2x2 params are all distinct and
    #    un-clamped -> witnesses that the Cramer products are not transposed.
    F = [cand_of(20, 20, -8, -12), cand_of(20, 58, -12, 8),
         cand_of(58, 20, 8, -12), cand_of(58, 58, 4, 10)]
    # G: strong contraction (E's MVs reversed) -> diag LOWER clamp (wm[2] -> 57345).
    G = [cand_of(20, 20, 0, 96), cand_of(20, 60, 0, -96),
         cand_of(60, 20, 96, 0), cand_of(60, 60, -96, 0)]
    # H: reversed shear -> nondiag LOWER clamp (-8191).
    H = [cand_of(20, 20, 12, 8), cand_of(20, 60, -12, 8),
         cand_of(60, 20, 12, -8), cand_of(60, 60, -12, -8)]
    # J1: a SINGLE sample (NumSamples==1, a real find_warp_samples outcome) — witnesses
    #     BOTH the arithmetic-shift LS macros (by0 = ls_product1(8,-45) is negative, so a
    #     LOGICAL >> corrupts it) AND the signed rounding of mult (wm[3]=-6317 not -6316).
    J1 = [cand_of(39, 40, -38, -7)]
    # J2: a clean 2-sample case with a small negative product1 term (no overflow) — a
    #     second, independent witness that the LS product1 shift is arithmetic.
    J2 = [cand_of(30, 50, 2, -4), cand_of(48, 44, 6, 3)]
    # K: a determinant of 1 (single sample sx=sy=dx=dy=-1) -> resolve_divisor divShift=14,
    #    minus WARPEDMODEL_PREC_BITS = -2 < 0 -> witnesses the divFactor<<(-divShift) rescale
    #    branch. Raw cand (srcY=311 is not a multiple of 8, so not expressible via cand_of).
    K = [[311, 311, 311, 311]]
    # CV: like C, but sample 2 is dropped by the VERTICAL LS_MV_MAX conjunct (|sy-dy|>=256,
    #     |sx-dx|<256) -> equals the same 2-prefix; witnesses the sy-dy guard branch.
    CV = [cand_of(23, 31, 16, 24), cand_of(23, 55, 40, 24), cand_of(55, 31, 316, 24)]
    # TC: a large MV (col +1100, row -1100 in 1/8-pel) with near-identity samples pushes the
    #     translation past +-2^23 -> witnesses BOTH translation clamp BOUNDS (hi wm[0], lo wm[1]).
    TC = [cand_of(23, 31, -1100, 1100), cand_of(23, 39, -1100, 1100),
          cand_of(39, 23, -1100, 1100)]
    cases = [
        ("A_translation", A, 3, 8, 8, 4, 4, 16, 24),
        ("B_affine", B, 4, 8, 8, 4, 4, 16, 24),
        ("C_guarded", C, 3, 8, 8, 4, 4, 16, 24),
        ("C2_prefix", C2, 2, 8, 8, 4, 4, 16, 24),
        ("E_clamp", E, 4, 8, 8, 4, 4, 0, 0),
        ("F_affine", F, 4, 8, 8, 4, 4, 0, 0),
        ("G_diaglo", G, 4, 8, 8, 4, 4, 0, 0),
        ("H_ndiaglo", H, 4, 8, 8, 4, 4, 0, 0),
        ("J1_single", J1, 1, 8, 8, 4, 4, 7, 1),
        ("J2_negprod", J2, 2, 8, 8, 4, 4, 0, 0),
        ("K_divshiftneg", K, 1, 8, 8, 4, 4, 0, 0),
        ("CV_vertguard", CV, 3, 8, 8, 4, 4, 16, 24),
        ("TC_transclamp", TC, 3, 8, 8, 4, 4, -1100, 1100),
        ("D_empty", [], 0, 8, 8, 4, 4, 16, 24),
    ]
    print("warp_estimation:")
    for name, cand, num, mr, mc, w4, h4, mvr, mvc in cases:
        valid, wm = warp_estimation(cand, num, mr, mc, w4, h4, mvr, mvc)
        print("  %-14s valid=%d wm=[%d,%d,%d,%d,%d,%d]"
              % (name, valid, wm[0], wm[1], wm[2], wm[3], wm[4], wm[5]))


if __name__ == "__main__":
    main()
