#!/usr/bin/env python3
# setup_shear_ref.py — spec-literal reference port for AV1 setup_shear (spec 7.11.3.6):
# the warp-model -> shear-params (alpha/beta/gamma/delta) + warpValid derivation.
#
# The KNOWN-ANSWER oracle for drishti's av1_setup_shear. Derived from the AV1 spec and
# cross-checked (spec + libaom + dav1d) via the 3-source reconciliation; NEVER back-derived
# from the Cyrius. Reuses the already-verified resolve_divisor / round2_signed / clip3 from
# warp_estimation_ref.py (the Div_Lut is checksum-pinned there).
#
# Reconciled facts:
#   * divisor = wmmat[2] (the x-scale) — NOT the determinant; RAW divisor output
#     (divShift = FloorLog2(|wmmat[2]|)+14, no -WARPEDMODEL_PREC_BITS rescale, no <0 fixup).
#   * WARP_PARAM_REDUCE_BITS = 6 (reduce to multiples of 64); INT16 clamps -32768..32767.
#   * warpValid = 0 if 4|alpha|+7|beta| >= 65536 OR 4|gamma|+4|delta| >= 65536.
#   * precondition guard: wmmat[2] <= 0 -> warpValid 0 (also protects resolve_divisor).

import sys
sys.path.insert(0, "scripts/refs")
from warp_estimation_ref import resolve_divisor, round2_signed, clip3  # verified primitives

WARPEDMODEL_PREC_BITS = 16
WARP_PARAM_REDUCE_BITS = 6


def setup_shear(wm):
    # wm = wmmat[0..5]. Returns (warpValid, [alpha, beta, gamma, delta]).
    one = 1 << WARPEDMODEL_PREC_BITS
    m2, m3, m4, m5 = wm[2], wm[3], wm[4], wm[5]
    if m2 <= 0:
        return (0, [0, 0, 0, 0])
    div_shift, div_factor = resolve_divisor(m2)          # RAW
    alpha0 = clip3(-32768, 32767, m2 - one)
    beta0 = clip3(-32768, 32767, m3)
    v = m4 * one                                         # wmmat[4] << 16
    gamma0 = clip3(-32768, 32767, round2_signed(v * div_factor, div_shift))
    w = m3 * m4
    delta0 = clip3(-32768, 32767, m5 - round2_signed(w * div_factor, div_shift) - one)
    red = 1 << WARP_PARAM_REDUCE_BITS
    alpha = round2_signed(alpha0, WARP_PARAM_REDUCE_BITS) * red
    beta = round2_signed(beta0, WARP_PARAM_REDUCE_BITS) * red
    gamma = round2_signed(gamma0, WARP_PARAM_REDUCE_BITS) * red
    delta = round2_signed(delta0, WARP_PARAM_REDUCE_BITS) * red
    valid = 1
    if 4 * abs(alpha) + 7 * abs(beta) >= one:
        valid = 0
    if 4 * abs(gamma) + 4 * abs(delta) >= one:
        valid = 0
    return (valid, [alpha, beta, gamma, delta])


def main():
    cases = [
        # identity -> all-zero shear, valid.
        ("identity", [0, 0, 65536, 0, 0, 65536]),
        # real warp_estimation outputs (0.7.93 KATs F / E / G) -> genuine shear params.
        ("est_F", [-185328, -101166, 70077, 211, -868, 68998]),
        ("est_E", [-317031, -312936, 73727, -62, 8191, 65369]),
        ("est_G", [317031, 321126, 57345, 62, -8191, 65493]),
        # fail the 4|alpha|+7|beta| check (big alpha+beta, zero gamma/delta) -> invalid.
        ("bad_ab", [0, 0, 73727, 8191, 0, 65536]),
        # alpha EXACTLY at the first-check boundary (4*16384 = 65536) -> pins the alpha
        # coefficient (4) AND the >= comparator (a > would pass it as valid).
        ("ab_a_bound", [0, 0, 81920, 0, 0, 65536]),
        # beta-dominant boundary: 7*9408 = 65856 >= 65536 but 6*9408 = 56448 < 65536 -> pins
        # the beta coefficient (7).
        ("ab_b_bound", [0, 0, 65536, 9408, 0, 65536]),
        # fail the 4|gamma|+4|delta| check only (identity diag, big m4 + skewed m5) -> invalid.
        ("bad_gd", [0, 0, 65536, 0, 8191, 73727]),
        # coefficient boundary pins (both directions) for the second check. With m2=65536
        # the divisor is exact so gamma0 == m4 and delta0 == m5-65536.
        ("gd_g_bound", [0, 0, 65536, 0, 16384, 65536]),   # 4*16384==65536 reject: gamma decr + >=
        ("gd_g_pass", [0, 0, 65536, 0, 13120, 65536]),    # 4*13120 under / 5*13120 over: gamma incr
        ("gd_d_bound", [0, 0, 65536, 0, 0, 81920]),       # delta-dominant reject: delta decr
        ("gd_d_pass", [0, 0, 65536, 0, 0, 78656]),        # delta pass near boundary: delta incr
        # first-check coeff INCREASE pins: alpha PASS at 13120, beta PASS at 8192.
        ("ab_a_pass", [0, 0, 78656, 0, 0, 65536]),        # 4*13120 under / 5*13120 over: alpha incr
        ("ab_b_pass", [0, 0, 65536, 8192, 0, 65536]),     # 7*8192 under / 8*8192 over: beta incr
        # precondition guard: wmmat[2] == 0 (and a negative variant) -> invalid, params 0.
        ("guard_zero", [0, 0, 0, 0, 0, 65536]),
        ("guard_neg", [0, 0, -100, 5, 5, 65536]),
        # reduce witness: alpha0=100 -> reduced to a multiple of 64 (128), not 100.
        ("reduce", [0, 0, 65636, 0, 0, 65536]),
        # INT16 clamp witness (lower): m2=100 -> alpha0 = 100-65536 clamps to -32768.
        ("clamp_lo", [0, 0, 100, 0, 0, 65536]),
        # INT16 clamp witness (upper): m2=100000 -> alpha0 = 34464 clamps to 32767.
        ("clamp_hi", [0, 0, 100000, 40000, 0, 65536]),
    ]
    for name, wm in cases:
        valid, s = setup_shear(wm)
        print("  %-11s valid=%d alpha=%d beta=%d gamma=%d delta=%d"
              % (name, valid, s[0], s[1], s[2], s[3]))


if __name__ == "__main__":
    main()
