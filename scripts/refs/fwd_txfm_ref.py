#!/usr/bin/env python3
"""fwd_txfm_ref.py — the AV1 FORWARD transform, derived from the spec's inverse (7.13), and its checks.

The AV1 spec defines only the inverse transform. The forward transform is the encoder's own choice: any one works,
since the decoder reconstructs through the normative inverse. A good one makes Inv(Fwd(r)) ~ r. drishti's is the
TRANSPOSE of the spec's inverse, at the spec's own constants:

  * the 1D DCT (7.13.2.3), ADST8 / ADST16 (7.13.2.7 / .8) are fixed sequences of operations on an array T: a
    permutation, then butterflies B( a, b, angle, flip ) and Hadamards H( a, b, flip ) (7.13.2.1), then (ADST) an
    output permutation. Each is a near-orthogonal linear map, so its transpose inverts it up to a power of two. The
    transpose of a sequence is the transposed operations in REVERSE order:
      - B( a, b, angle, 0 ) is the rotation [c -s; s c]; its transpose [c s; -s c] is B( a, b, -angle, 0 );
      - B( a, b, angle, 1 ) is [s c; c -s], symmetric: its own transpose;
      - H( a, b, 0 ) = [1 1; 1 -1] and H( a, b, 1 ) = [-1 1; 1 1] are symmetric: their own transposes (without the
        inverse's clamp, a conformance bound on decoded data);
      - a permutation T[ i ] = s(i) * copyT[ p(i) ] transposes to T[ p(i) ] = s(i) * copyT[ i ];
    and each transposed B rounds its two outputs with Round2( , 12 ) exactly as the inverse's does;
  * ADST4 (7.13.2.6) is x = M * T, then Round2( x, 12 ): its transpose is Round2( M^T * T, 12 ), M exact integers;
  * the identity transforms (7.13.2.11-14) are scalings: their own transposes;
  * the lossless Walsh-Hadamard (7.13.2.10) is an exactly invertible lifting, so the forward is its exact INVERSE
    (the steps undone in reverse order), not its transpose; Inv(Fwd(r)) == r exactly.

The 2D forward undoes 7.13.3 in reverse order: the FLIPADST flips of 7.12.3 on the input, the column transforms, then
the row transforms, then x sqrt(2) (5793 / 4096, the spec's identity-4 constant) where the inverse scales by
1 / sqrt(2) (2896 / 4096) for a 2:1 rectangle. Every 1D transform of length N has gain^2 = N / 2 (checked below for
every one), so a forward of total scale 2 ^ ( rowShift + 6 - log2W - log2H ) inverts 7.13.3's rowShift + 4. Where
that power of two is applied is libaom's choice (av1_fwd_txfm_shift_ls: shift[0] up before the columns, shift[1]
after them, shift[2] after the rows), kept for its precision and so libaom can be compared; this port derives the
total and asserts libaom's table sums to it for all 19 sizes. Coefficients are row-major, spec layout (Dequant[ i ][
j ], i the vertical frequency); a 64-point dimension keeps only its first 32 (7.13.3 reads nothing beyond).

Checks (all asserted; exit 1 on any failure):
  1. the derivation: each forward 1D matrix equals the TRANSPOSE of the spec inverse's, exactly, in unrounded
     rational arithmetic (fractions); every 1D gain^2 is N / 2 to within the 12-bit constants' rounding;
  2. the shifts: libaom's table sums to the derived total for every size;
  3. the round trip: Inv(Fwd(r)) through the spec's 7.13.3 + 7.12.3 flip, on seeded residuals at 8 and 12 bits, is
     within the per-size bound printed (and pinned in tests/av1_ftx.tcyr); the lossless WHT is EXACT;
  4. --libaom: libaom's own forward, compiled from ref/ (scripts/refs/fwd_txfm_libaom.c), equals this port bit for
     bit: every 1D kernel at cos_bit 12, every 2D (size, type) with its cos_bit forced to 12, and av1_fwht4x4_c;
     with libaom's own cos_bit (10..13 bits) it differs by rounding only, reported, not asserted.

--emit prints the Cyrius known-answer table tests/av1_ftx.tcyr asserts (digests over seeded residuals).
"""

import fractions
import math
import os
import random
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SPEC = os.path.join(ROOT, "build", "spec-dl", "08.decoding.process.md")
FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
        print("FAIL:", msg)


# ---------------------------------------------------------------------------------------------------------------
# 7.13.2.1 — Cos128_Lookup, read from the spec markdown when it is present; it must also be round(4096 cos(a pi/128))
# ---------------------------------------------------------------------------------------------------------------
COS128_LIT = [
    4096, 4095, 4091, 4085, 4076, 4065, 4052, 4036, 4017, 3996, 3973, 3948, 3920, 3889, 3857, 3822,
    3784, 3745, 3703, 3659, 3612, 3564, 3513, 3461, 3406, 3349, 3290, 3229, 3166, 3102, 3035, 2967,
    2896, 2824, 2751, 2675, 2598, 2520, 2440, 2359, 2276, 2191, 2106, 2019, 1931, 1842, 1751, 1660,
    1567, 1474, 1380, 1285, 1189, 1092, 995, 897, 799, 700, 601, 501, 401, 301, 201, 101, 0]


def load_cos128():
    if os.path.exists(SPEC):
        txt = open(SPEC).read()
        m = re.search(r"Cos128_Lookup\[ 65 \] = \{([^}]*)\}", txt)
        check(m is not None, "Cos128_Lookup found in the spec markdown")
        vals = [int(v) for v in re.findall(r"-?\d+", m.group(1))]
        check(vals == COS128_LIT, "the literal Cos128_Lookup is the spec's")
    for a in range(65):
        check(COS128_LIT[a] == int(math.floor(4096 * math.cos(a * math.pi / 128) + 0.5)),
              f"Cos128_Lookup[{a}] = round(4096 cos)")
    return COS128_LIT


COS128 = load_cos128()
SINPI = (1321, 2482, 3344, 3803)          # SINPI_1_9 .. SINPI_4_9 (7.13.2.6)
TX_W_LOG2 = [2, 3, 4, 5, 6, 2, 3, 3, 4, 4, 5, 5, 6, 2, 4, 3, 5, 4, 6]   # Tx_Width_Log2 (additional tables)
TX_H_LOG2 = [2, 3, 4, 5, 6, 3, 2, 4, 3, 5, 4, 6, 5, 4, 2, 5, 3, 6, 4]   # Tx_Height_Log2
ROW_SHIFT = [0, 1, 2, 2, 2, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2]   # Transform_Row_Shift (7.13.3)
# libaom av1/encoder/av1_fwd_txfm2d.c av1_fwd_txfm_shift_ls (shift[0], shift[1], shift[2]); check 2 derives the sum
FWD_SHIFT = [(2, 0, 0), (2, -1, 0), (2, -2, 0), (2, -4, 0), (0, -2, -2), (2, -1, 0), (2, -1, 0), (2, -2, 0),
             (2, -2, 0), (2, -4, 0), (2, -4, 0), (0, -2, -2), (2, -4, -2), (2, -1, 0), (2, -1, 0), (2, -2, 0),
             (2, -2, 0), (0, -2, 0), (2, -4, 0)]
TX_NAMES = ["4x4", "8x8", "16x16", "32x32", "64x64", "4x8", "8x4", "8x16", "16x8", "16x32", "32x16", "32x64",
            "64x32", "4x16", "16x4", "8x32", "32x8", "16x64", "64x16"]

# PlaneTxType (6.10.35 order) and the 1D kind of its rows / columns (7.13.3); flips (7.12.3)
DCT, ADST, IDTX = 0, 1, 2
ROW_KIND = [DCT, DCT, ADST, ADST, DCT, ADST, ADST, ADST, ADST, IDTX, IDTX, DCT, IDTX, ADST, IDTX, ADST]
COL_KIND = [DCT, ADST, DCT, ADST, ADST, DCT, ADST, ADST, ADST, IDTX, DCT, IDTX, ADST, IDTX, ADST, IDTX]
FLIP_UD = {4, 8, 14, 6}     # FLIPADST_DCT, FLIPADST_ADST, V_FLIPADST, FLIPADST_FLIPADST
FLIP_LR = {5, 7, 15, 6}     # DCT_FLIPADST, ADST_FLIPADST, H_FLIPADST, FLIPADST_FLIPADST


def round2(x, n):
    if n == 0:
        return x
    return (x + (1 << (n - 1))) >> n       # Python >> is arithmetic: floor, as Round2 is (section 4)


def cos128(angle):
    a2 = angle & 255
    if a2 <= 64:
        return COS128[a2]
    if a2 <= 128:
        return -COS128[128 - a2]
    if a2 <= 192:
        return -COS128[a2 - 128]
    return COS128[256 - a2]


def sin128(angle):
    return cos128(angle - 64)


def brev(nbits, x):
    t = 0
    for i in range(nbits):
        t |= ((x >> i) & 1) << (nbits - 1 - i)
    return t


# ---------------------------------------------------------------------------------------------------------------
# The spec's inverse 1D transforms as operation lists, transcribed from 7.13.2.3 / 7.13.2.7 / 7.13.2.8 step by step
# ---------------------------------------------------------------------------------------------------------------
def idct_ops(n):
    ops = []

    def B(a, b, ang, fl):
        ops.append(("B", a, b, ang, fl))

    def H(a, b, fl):
        ops.append(("H", a, b, fl))
    if n == 6:
        for i in range(16):
            B(32 + i, 63 - i, 63 - 4 * brev(4, i), 0)                       # 2
    if n >= 5:
        for i in range(8):
            B(16 + i, 31 - i, 6 + (brev(3, 7 - i) << 3), 0)                 # 3
    if n == 6:
        for i in range(16):
            H(32 + i * 2, 33 + i * 2, i & 1)                                # 4
    if n >= 4:
        for i in range(4):
            B(8 + i, 15 - i, 12 + (brev(2, 3 - i) << 4), 0)                 # 5
    if n >= 5:
        for i in range(8):
            H(16 + 2 * i, 17 + 2 * i, i & 1)                                # 6
    if n == 6:
        for i in range(4):
            for j in range(2):
                B(62 - i * 4 - j, 33 + i * 4 + j, 60 - 16 * brev(2, i) + 64 * j, 1)   # 7
    if n >= 3:
        for i in range(2):
            B(4 + i, 7 - i, 56 - 32 * i, 0)                                 # 8
    if n >= 4:
        for i in range(4):
            H(8 + 2 * i, 9 + 2 * i, i & 1)                                  # 9
    if n >= 5:
        for i in range(2):
            for j in range(2):
                B(30 - 4 * i - j, 17 + 4 * i + j, 24 + (j << 6) + ((1 - i) << 5), 1)   # 10
    if n == 6:
        for i in range(8):
            for j in range(2):
                H(32 + i * 4 + j, 35 + i * 4 - j, i & 1)                    # 11
    for i in range(2):
        B(2 * i, 2 * i + 1, 32 + 16 * i, 1 - i)                             # 12
    if n >= 3:
        for i in range(2):
            H(4 + 2 * i, 5 + 2 * i, i)                                      # 13
    if n >= 4:
        for i in range(2):
            B(14 - i, 9 + i, 48 + 64 * i, 1)                                # 14
    if n >= 5:
        for i in range(4):
            for j in range(2):
                H(16 + 4 * i + j, 19 + 4 * i - j, i & 1)                    # 15
    if n == 6:
        for i in range(2):
            for j in range(4):
                B(61 - i * 8 - j, 34 + i * 8 + j, 56 - i * 32 + (j >> 1) * 64, 1)     # 16
    for i in range(2):
        H(i, 3 - i, 0)                                                      # 17
    if n >= 3:
        B(6, 5, 32, 1)                                                      # 18
    if n >= 4:
        for i in range(2):
            for j in range(2):
                H(8 + 4 * i + j, 11 + 4 * i - j, i)                         # 19
    if n >= 5:
        for i in range(4):
            B(29 - i, 18 + i, 48 + (i >> 1) * 64, 1)                        # 20
    if n == 6:
        for i in range(4):
            for j in range(4):
                H(32 + 8 * i + j, 39 + 8 * i - j, i & 1)                    # 21
    if n >= 3:
        for i in range(4):
            H(i, 7 - i, 0)                                                  # 22
    if n >= 4:
        for i in range(2):
            B(13 - i, 10 + i, 32, 1)                                        # 23
    if n >= 5:
        for i in range(2):
            for j in range(4):
                H(16 + i * 8 + j, 23 + i * 8 - j, i)                        # 24
    if n == 6:
        for i in range(8):
            B(59 - i, 36 + i, 48 if i < 4 else 112, 1)                      # 25
    if n >= 4:
        for i in range(8):
            H(i, 15 - i, 0)                                                 # 26
    if n >= 5:
        for i in range(4):
            B(27 - i, 20 + i, 32, 1)                                        # 27
    if n == 6:
        for i in range(8):
            H(32 + i, 47 - i, 0)                                            # 28
            H(48 + i, 63 - i, 1)
    if n >= 5:
        for i in range(16):
            H(i, 31 - i, 0)                                                 # 29
    if n == 6:
        for i in range(8):
            B(55 - i, 40 + i, 32, 1)                                        # 30
    if n == 6:
        for i in range(32):
            H(i, 63 - i, 0)                                                 # 31
    return ops


def iadst8_ops():
    ops = []
    for i in range(4):
        ops.append(("B", 2 * i, 2 * i + 1, 60 - 16 * i, 1))                 # 2
    for i in range(4):
        ops.append(("H", i, 4 + i, 0))                                      # 3
    for i in range(2):
        ops.append(("B", 4 + 3 * i, 5 + i, 48 - 32 * i, 1))                 # 4
    for i in range(2):
        for j in range(2):
            ops.append(("H", 4 * j + i, 2 + 4 * j + i, 0))                  # 5
    for i in range(2):
        ops.append(("B", 2 + 4 * i, 3 + 4 * i, 32, 1))                      # 6
    return ops


def iadst16_ops():
    ops = []
    for i in range(8):
        ops.append(("B", 2 * i, 2 * i + 1, 62 - 8 * i, 1))                  # 2
    for i in range(8):
        ops.append(("H", i, 8 + i, 0))                                      # 3
    for i in range(2):
        ops.append(("B", 8 + 2 * i, 9 + 2 * i, 56 - 32 * i, 1))             # 4
        ops.append(("B", 13 + 2 * i, 12 + 2 * i, 8 + 32 * i, 1))
    for i in range(4):
        for j in range(2):
            ops.append(("H", 8 * j + i, 4 + 8 * j + i, 0))                  # 5
    for i in range(2):
        for j in range(2):
            ops.append(("B", 4 + 8 * j + 3 * i, 5 + 8 * j + i, 48 - 32 * i, 1))   # 6
    for i in range(2):
        for j in range(4):
            ops.append(("H", 4 * j + i, 2 + 4 * j + i, 0))                  # 7
    for i in range(4):
        ops.append(("B", 2 + 4 * i, 3 + 4 * i, 32, 1))                      # 8
    return ops


def adst_in_perm(n):     # 7.13.2.4: T[ i ] = copyT[ idx ]
    n0 = 1 << n
    return [(i - 1) if (i & 1) else (n0 - i - 1) for i in range(n0)]


def adst_out_perm(n):    # 7.13.2.5: T[ i ] = ( i & 1 ) ? -copyT[ idx ] : copyT[ idx ]
    out = []
    for i in range(1 << n):
        a = (i >> 3) & 1
        b = ((i >> 2) & 1) ^ ((i >> 3) & 1)
        c = ((i >> 1) & 1) ^ ((i >> 2) & 1)
        d = (i & 1) ^ ((i >> 1) & 1)
        out.append((((d << 3) | (c << 2) | (b << 1) | a) >> (4 - n), -1 if (i & 1) else 1))
    return out


# --- executing operations. `exact` runs in rational arithmetic with no rounding (for the matrix checks) ---------
def op_B(T, a, b, ang, fl, exact):
    c, s = cos128(ang), sin128(ang)
    x = T[a] * c - T[b] * s
    y = T[a] * s + T[b] * c
    if exact:
        x, y = x / 4096, y / 4096
    else:
        x, y = round2(x, 12), round2(y, 12)
    if fl:
        x, y = y, x
    T[a], T[b] = x, y


def op_H(T, a, b, fl, r):
    if fl:
        a, b = b, a
    x, y = T[a], T[b]
    if r is None:
        T[a], T[b] = x + y, x - y
    else:
        lo, hi = -(1 << (r - 1)), (1 << (r - 1)) - 1
        T[a], T[b] = min(max(x + y, lo), hi), min(max(x - y, lo), hi)


def run_inverse_ops(T, ops, r, exact):
    for op in ops:
        if op[0] == "B":
            op_B(T, op[1], op[2], op[3], op[4], exact)
        else:
            op_H(T, op[1], op[2], op[3], None if exact else r)


def run_forward_ops(T, ops, exact):
    for op in reversed(ops):           # the transpose: reversed order ...
        if op[0] == "B":
            ang = op[3] if op[4] else -op[3]    # ... B flip 0 -> B( -angle ), B flip 1 and H are symmetric
            op_B(T, op[1], op[2], ang, op[4], exact)
        else:
            op_H(T, op[1], op[2], op[3], None)  # no clamp: that bound is on decoded data


# --- the spec's inverse 1D transforms (7.13.2.3 .. 7.13.2.15) ----------------------------------------------------
def inv_dct(T, n, r, exact=False):
    T[:] = [T[brev(n, i)] for i in range(1 << n)]                 # 7.13.2.2
    run_inverse_ops(T, idct_ops(n), r, exact)


def adst4_matrix():
    # x = M * T before the final Round2( , 12 ) of 7.13.2.6 (exact integers); column m = the response to unit T[m]
    M = [[0] * 4 for _ in range(4)]
    for m in range(4):
        t = [0, 0, 0, 0]
        t[m] = 1
        x = inv_adst4_pre(t)
        for k in range(4):
            M[k][m] = x[k]
    return M


def inv_adst4_pre(T):
    s0 = SINPI[0] * T[0]
    s1 = SINPI[1] * T[0]
    s2 = SINPI[2] * T[1]
    s3 = SINPI[3] * T[2]
    s4 = SINPI[0] * T[2]
    s5 = SINPI[1] * T[3]
    s6 = SINPI[3] * T[3]
    a7 = T[0] - T[2]
    b7 = a7 + T[3]
    s0 = s0 + s3
    s1 = s1 - s4
    s3 = s2
    s2 = SINPI[2] * b7
    s0 = s0 + s5
    s1 = s1 - s6
    x0 = s0 + s3
    x1 = s1 + s3
    x2 = s2
    x3 = s0 + s1
    x3 = x3 - s3
    return [x0, x1, x2, x3]


def inv_adst(T, n, r, exact=False):
    if n == 2:
        x = inv_adst4_pre(T)
        T[:] = [v / 4096 for v in x] if exact else [round2(v, 12) for v in x]
        return
    ip = adst_in_perm(n)
    T[:] = [T[ip[i]] for i in range(1 << n)]
    run_inverse_ops(T, iadst8_ops() if n == 3 else iadst16_ops(), r, exact)
    op = adst_out_perm(n)
    c = list(T)
    T[:] = [sg * c[idx] for (idx, sg) in op]


IDTX_MUL = {2: (5793, 12), 3: (2, 0), 4: (11586, 12), 5: (4, 0)}   # 7.13.2.11 .. 7.13.2.14


def inv_identity(T, n, exact=False):
    m, sh = IDTX_MUL[n]
    T[:] = [(v * m / (1 << sh)) if exact else round2(v * m, sh) for v in T]


def inv_wht(T, shift):              # 7.13.2.10
    a, c, d, b = (T[0] >> shift), (T[1] >> shift), (T[2] >> shift), (T[3] >> shift)
    a += c
    d -= b
    e = (a - d) >> 1
    b = e - b
    c = e - c
    a -= b
    d += c
    T[:] = [a, b, c, d]


def inv_1d(T, kind, n, r, exact=False):
    if kind == DCT:
        inv_dct(T, n, r, exact)
    elif kind == ADST:
        inv_adst(T, n, r, exact)
    else:
        inv_identity(T, n, exact)


# --- the forward 1D transforms, derived -------------------------------------------------------------------------
ADST4_M = adst4_matrix()


def fwd_dct(T, n, exact=False):
    run_forward_ops(T, idct_ops(n), exact)
    c = list(T)
    for i in range(1 << n):                       # the brev permutation's transpose (brev is an involution)
        T[brev(n, i)] = c[i]


def fwd_adst(T, n, exact=False):
    if n == 2:
        x = [sum(ADST4_M[k][m] * T[k] for k in range(4)) for m in range(4)]    # M^T * T
        T[:] = [v / 4096 for v in x] if exact else [round2(v, 12) for v in x]
        return
    op = adst_out_perm(n)
    c = list(T)
    T[:] = [0] * (1 << n)
    for i, (idx, sg) in enumerate(op):            # the output permutation's transpose
        T[idx] = sg * c[i]
    run_forward_ops(T, iadst8_ops() if n == 3 else iadst16_ops(), exact)
    ip = adst_in_perm(n)
    c = list(T)
    for i in range(1 << n):                       # the input permutation's transpose
        T[ip[i]] = c[i]


def fwd_identity(T, n, exact=False):
    inv_identity(T, n, exact)                     # a scaling is its own transpose


def fwd_1d(T, kind, n, exact=False):
    if kind == DCT:
        fwd_dct(T, n, exact)
    elif kind == ADST:
        fwd_adst(T, n, exact)
    else:
        fwd_identity(T, n, exact)


def fwd_wht(T):
    # The exact inverse of 7.13.2.10's lifting (shift 0): its outputs are (a, b, c, d) in T[0..3]; undo d += c,
    # a -= b, recompute e from the restored a and d, undo c = e - c and b = e - b, then d -= b and a += c; its inputs
    # were read as a = T[0], c = T[1], d = T[2], b = T[3].
    a, b, c, d = T
    d -= c
    a += b
    e = (a - d) >> 1
    c = e - c
    b = e - b
    d += b
    a -= c
    T[:] = [a, c, d, b]


def kind_ok(kind, n):
    return (kind == DCT and 2 <= n <= 6) or (kind == ADST and 2 <= n <= 4) or (kind == IDTX and 2 <= n <= 5)


def combo_ok(txsz, txtype):
    return kind_ok(ROW_KIND[txtype], TX_W_LOG2[txsz]) and kind_ok(COL_KIND[txtype], TX_H_LOG2[txsz])


# --- 2D --------------------------------------------------------------------------------------------------------
def fwd_2d(res, txsz, txtype, lossless=False):
    """res: h*w row-major spatial residual -> h*w row-major coefficients (spec layout), 0 outside 32x32."""
    lw, lh = TX_W_LOG2[txsz], TX_H_LOG2[txsz]
    w, h = 1 << lw, 1 << lh
    if lossless:
        buf = [0] * 16
        for j in range(4):                               # columns: the inverse's second pass, undone first
            t = [res[i * 4 + j] for i in range(4)]
            fwd_wht(t)
            for i in range(4):
                buf[i * 4 + j] = t[i]
        out = [0] * 16
        for i in range(4):                               # rows, then x 4: the inverse's row pass reads T >> 2
            t = buf[i * 4:(i + 1) * 4]
            fwd_wht(t)
            for j in range(4):
                out[i * 4 + j] = t[j] * 4
        return out
    s0, s1, s2 = FWD_SHIFT[txsz]
    ud, lr = txtype in FLIP_UD, txtype in FLIP_LR
    buf = [0] * (w * h)
    for j in range(w):
        src = (w - 1 - j) if lr else j
        t = [res[((h - 1 - i) if ud else i) * w + src] for i in range(h)]
        t = [v << s0 for v in t] if s0 >= 0 else [round2(v, -s0) for v in t]
        fwd_1d(t, COL_KIND[txtype], lh)
        t = [round2(v, -s1) for v in t] if s1 <= 0 else [v << s1 for v in t]
        for i in range(h):
            buf[i * w + j] = t[i]
    out = [0] * (w * h)
    rect = abs(lw - lh) == 1
    for i in range(h):
        t = buf[i * w:(i + 1) * w]
        fwd_1d(t, ROW_KIND[txtype], lw)
        t = [round2(v, -s2) for v in t] if s2 <= 0 else [v << s2 for v in t]
        if rect:
            t = [round2(v * 5793, 12) for v in t]
        for j in range(w):
            out[i * w + j] = t[j] if (i < 32 and j < 32) else 0
    return out


def inv_2d(deq, txsz, txtype, bd, lossless=False):
    """7.13.3 then the 7.12.3 flip: h*w coefficients -> the h*w residual reconstruct adds."""
    lw, lh = TX_W_LOG2[txsz], TX_H_LOG2[txsz]
    w, h = 1 << lw, 1 << lh
    row_shift = 0 if lossless else ROW_SHIFT[txsz]
    col_shift = 0 if lossless else 4
    rclamp, cclamp = bd + 8, max(bd + 6, 16)
    R = [0] * (w * h)
    for i in range(h):
        t = [deq[i * w + j] if (i < 32 and j < 32) else 0 for j in range(w)]
        if abs(lw - lh) == 1:
            t = [round2(v * 2896, 12) for v in t]
        if lossless:
            inv_wht(t, 2)
        else:
            inv_1d(t, ROW_KIND[txtype], lw, rclamp)
        for j in range(w):
            R[i * w + j] = round2(t[j], row_shift)
    lo, hi = -(1 << (cclamp - 1)), (1 << (cclamp - 1)) - 1
    R = [min(max(v, lo), hi) for v in R]
    for j in range(w):
        t = [R[i * w + j] for i in range(h)]
        if lossless:
            inv_wht(t, 0)
        else:
            inv_1d(t, COL_KIND[txtype], lh, cclamp)
        for i in range(h):
            R[i * w + j] = round2(t[i], col_shift)
    ud, lr = (not lossless) and txtype in FLIP_UD, (not lossless) and txtype in FLIP_LR
    out = [0] * (w * h)
    for i in range(h):
        for j in range(w):
            out[i * w + j] = R[((h - 1 - i) if ud else i) * w + ((w - 1 - j) if lr else j)]
    return out


# --- the seeded residuals tests/av1_ftx.tcyr regenerates (an LCG every i64 language computes alike) ---------------
def lcg_block(seed, count, maxv):
    x = seed
    out = []
    for _ in range(count):
        x = (x * 1103515245 + 12345) & 0x7fffffff
        out.append(((x >> 8) % (2 * maxv + 1)) - maxv)
    return out


def digests(c):
    return sum((k + 1) * v for k, v in enumerate(c)), sum(v * v for v in c)


# ---------------------------------------------------------------------------------------------------------------
def check_derivation():
    """1. forward 1D matrix == transpose of the inverse's (exact, no rounding); gains^2 ~ N / 2."""
    F = fractions.Fraction
    for kind, sizes in ((DCT, range(2, 7)), (ADST, range(2, 5)), (IDTX, range(2, 6))):
        for n in sizes:
            N = 1 << n
            inv_cols, fwd_cols = [], []
            for m in range(N):
                t = [F(0)] * N
                t[m] = F(1)
                u = list(t)
                inv_1d(t, kind, n, None, exact=True)
                fwd_1d(u, kind, n, exact=True)
                inv_cols.append(t)
                fwd_cols.append(u)
            # Inv[k][m] = inv_cols[m][k]; Fwd[k][m] = fwd_cols[m][k]; need Fwd == Inv^T
            ok = all(fwd_cols[m][k] == inv_cols[k][m] for m in range(N) for k in range(N))
            check(ok, f"forward {['DCT', 'ADST', 'IDTX'][kind]}{N} is the exact transpose of the spec inverse")
            # gain^2: (Inv Inv^T)[k][k] ~ N / 2, off-diagonal ~ 0 (the 12-bit constants are rounded)
            worst = 0.0
            for k in range(N):
                for l in range(N):
                    g = float(sum(inv_cols[m][k] * inv_cols[m][l] for m in range(N)))
                    worst = max(worst, abs(g - (N / 2 if k == l else 0)) / (N / 2))
            check(worst < 2e-3, f"{['DCT', 'ADST', 'IDTX'][kind]}{N}: gain^2 = N/2 within 0.2% (worst {worst:.2e})")


def check_shifts():
    """2. libaom's shift placement sums to the derived 2D scale exponent for every size."""
    for t in range(19):
        want = ROW_SHIFT[t] + 6 - TX_W_LOG2[t] - TX_H_LOG2[t]
        check(sum(FWD_SHIFT[t]) == want, f"{TX_NAMES[t]}: shift[0]+shift[1]+shift[2] = {want}")


def roundtrip_bounds():
    """3. The round trip, two ways, per size over every legal type:
      - pixels: |Inv(Fwd(r)) - r| for 8- and 12-bit residuals: flat extremes, a checkerboard, random. A size with a
        64-point dimension keeps only the lowest 32 of its 64 frequencies (7.13.3), so a residual with energy above
        them cannot survive any forward transform; there r is band-limited, Inv(D) for a random D on the kept 32;
      - coefficients: |Fwd(Inv(D)) - D| for random D on the kept region, at magnitudes an 8- or 12-bit block yields.
    The lossless WHT is checked EXACT."""
    pix, coef = {}, {}
    rng = random.Random(20261118)
    for t in range(19):
        w, h = 1 << TX_W_LOG2[t], 1 << TX_H_LOG2[t]
        big = (w == 64) or (h == 64)
        wp = wc = 0
        for typ in range(16):
            if not combo_ok(t, typ):
                continue
            for bd in (8, 12):
                maxv = (1 << bd) - 1
                for trial in range(6 if w * h <= 256 else 2):
                    if big:
                        d = [rng.randint(-maxv, maxv) if ((k // w) < 32 and (k % w) < 32 and (k // w + k % w) < 12)
                             else 0 for k in range(w * h)]
                        r = inv_2d(d, t, typ, bd)
                    elif trial == 0:
                        r = [maxv] * (w * h)                     # a flat extreme: the largest DC
                    elif trial == 1:
                        r = [maxv if ((k // w + k % w) & 1) else -maxv for k in range(w * h)]   # checkerboard
                    else:
                        r = [rng.randint(-maxv, maxv) for _ in range(w * h)]
                    rec = inv_2d(fwd_2d(r, t, typ), t, typ, bd)
                    wp = max(wp, max(abs(a - b) for a, b in zip(rec, r)))
                    d = [rng.randint(-maxv, maxv) if ((k // w) < 32 and (k % w) < 32) else 0 for k in range(w * h)]
                    back = fwd_2d(inv_2d(d, t, typ, bd), t, typ)
                    wc = max(wc, max(abs(a - b) for a, b in zip(back, d)))
        pix[t], coef[t] = wp, wc
    for trial in range(2000):
        maxv = (1 << (8 if trial < 1000 else 12)) - 1
        r = [rng.randint(-maxv, maxv) for _ in range(16)]
        check(inv_2d(fwd_2d(r, 0, 0, lossless=True), 0, 0, 12, lossless=True) == r,
              f"lossless WHT round trip is exact ({r[:4]}...)")
    return pix, coef


def libaom_harness():
    exe = os.path.join(ROOT, "build", "fwd_txfm_libaom")
    src = os.path.join(ROOT, "scripts", "refs", "fwd_txfm_libaom.c")
    lib = os.path.join(ROOT, "ref", "aom-build", "libaom.a")
    if not os.path.exists(lib):
        print("SKIP --libaom: ref/aom-build/libaom.a not built (ref/README.md)")
        return None
    if (not os.path.exists(exe)) or os.path.getmtime(exe) < os.path.getmtime(src):
        cmd = ["cc", "-O1", "-I", os.path.join(ROOT, "ref", "aom"), "-I", os.path.join(ROOT, "ref", "aom-build"),
               src, lib, "-lm", "-lpthread", "-o", exe]
        subprocess.run(cmd, check=True)
    return exe


def check_libaom():
    """4. libaom's own forward, bit for bit at cos_bit 12."""
    exe = libaom_harness()
    if exe is None:
        return
    rng = random.Random(7)
    reqs, want = [], []
    for kind, sizes in ((DCT, range(2, 7)), (ADST, range(2, 5)), (IDTX, range(2, 6))):
        for n in sizes:
            for _ in range(200):
                v = [rng.randint(-(1 << 15), (1 << 15) - 1) for _ in range(1 << n)]
                u = list(v)
                fwd_1d(u, kind, n)
                reqs.append(f"1d {kind} {1 << n} 12 " + " ".join(map(str, v)))
                want.append(("1d", kind, n, u))
    combos = 0
    for t in range(19):
        w, h = 1 << TX_W_LOG2[t], 1 << TX_H_LOG2[t]
        for typ in range(16):
            if not combo_ok(t, typ):
                continue
            combos += 1
            for _ in range(4 if w * h <= 1024 else 2):
                r = [rng.randint(-4095, 4095) for _ in range(w * h)]
                for cb in (12, 0):
                    reqs.append(f"2d {t} {typ} 12 {cb} " + " ".join(map(str, r)))
                    want.append(("2d", t, typ, cb, fwd_2d(r, t, typ)))
    for _ in range(500):
        r = [rng.randint(-4095, 4095) for _ in range(16)]
        reqs.append("wht " + " ".join(map(str, r)))
        want.append(("wht", fwd_2d(r, 0, 0, lossless=True)))
    out = subprocess.run([exe], input="\n".join(reqs) + "\n", capture_output=True, text=True, check=True).stdout
    lines = out.strip().split("\n")
    check(len(lines) == len(reqs), f"libaom answered every request ({len(lines)} of {len(reqs)})")
    n1 = n2 = nw = 0
    own_worst = {}
    for line, w8 in zip(lines, want):
        got = [int(x) for x in line.split()]
        if w8[0] == "1d":
            check(got == w8[3], f"libaom 1D {['DCT', 'ADST', 'IDTX'][w8[1]]}{1 << w8[2]} at cos_bit 12 == the port")
            n1 += 1
        elif w8[0] == "wht":
            spec = [got[(k % 4) * 4 + k // 4] for k in range(16)]     # libaom out[c * 4 + r] -> spec (r, c)
            check(spec == w8[1], "libaom av1_fwht4x4_c == the port's lossless forward")
            nw += 1
        else:
            _, t, typ, cb, mine = w8
            w, h = 1 << TX_W_LOG2[t], 1 << TX_H_LOG2[t]
            spec = [0] * (w * h)
            for i in range(h):
                for j in range(w):
                    spec[i * w + j] = got[j * h + i] if (i < 32 and j < 32) else 0   # out[c * h + r] -> (r, c)
            if cb == 12:
                check(spec == mine, f"libaom 2D {TX_NAMES[t]} type {typ} at cos_bit 12 == the port")
                n2 += 1
            else:
                d = max(abs(a - b) for a, b in zip(spec, mine))
                own_worst[t] = max(own_worst.get(t, 0), d)
    print(f"libaom: {n1} 1D vectors, {n2} 2D blocks over {combos} (size, type) pairs and {nw} lossless blocks "
          "bit-exact at cos_bit 12")
    print("libaom at its own cos_bit (10..13 bits) differs from the 12-bit port by at most, per size:")
    print("  " + "  ".join(f"{TX_NAMES[t]}:{own_worst[t]}" for t in sorted(own_worst)))


def emit():
    """The Cyrius known answers: per legal (size, type), D1 / D2 digests of fwd_2d over seeded 8- and 12-bit
    residuals, seed = 1 + 16 * txsz + type."""
    print("# generated by scripts/refs/fwd_txfm_ref.py --emit")
    print("# 1D: kind n d1 d2 over lcg_block(500 + 10 * kind + n, 2^n, 32767)")
    for kind, sizes in ((DCT, range(2, 7)), (ADST, range(2, 5)), (IDTX, range(2, 6))):
        for n in sizes:
            v = lcg_block(500 + 10 * kind + n, 1 << n, 32767)
            fwd_1d(v, kind, n)
            print("    ftx_kat1(%d, %d, %d, %d);" % ((kind, n) + digests(v)))
    # The WHT kernel alone: inside the 2D lossless path a LOGICAL shift for its e = ( a - d ) >> 1 is an equivalent
    # mutant in wrapping 64-bit arithmetic (it adds 2^63, the second pass spreads that to multiples of 2^62, and the
    # final x 4 sends them to 0 mod 2^64), so the kernel is pinned on its own; each vector has a - d < 0.
    print("# 1D WHT: seed d1 d2 over lcg_block(seed, 4, 32767); a - d < 0 for every seed but 600")
    for seed in (600, 601, 602, 603, 605):
        v = lcg_block(seed, 4, 32767)
        check(((v[0] + v[1]) - (v[3] - v[2]) < 0) == (seed != 600), f"WHT vector {seed}: the sign of a - d")
        fwd_wht(v)
        print("    ftx_katw(%d, %d, %d);" % ((seed,) + digests(v)))
    v = [0, 0, 0, 5]
    fwd_wht(v)
    check(v == [3, -3, 2, -3], "fwd_wht([0, 0, 0, 5]) by hand: d = 5, a = 0, e = (0 - 5) >> 1 = -3, c = -3, "
          "b = -3, d = 5 - 3 = 2, a = 0 + 3 = 3; out (a, c, d, b)")
    print("# fwd_wht([0, 0, 0, 5]) =", v)
    print("# 2D: txsz type d1_8 d2_8 d1_12 d2_12 rt8 rt12 over lcg_block(1 + 16 * txsz + type, w * h, 255 / 4095);")
    print("# rt = max |Inv(Fwd(r)) - r| through 7.13.3 + the 7.12.3 flip at 8 / 12 bits")
    rows = []
    for t in range(19):
        w, h = 1 << TX_W_LOG2[t], 1 << TX_H_LOG2[t]
        for typ in range(16):
            if not combo_ok(t, typ):
                continue
            seed = 1 + 16 * t + typ
            r8, r12 = lcg_block(seed, w * h, 255), lcg_block(seed, w * h, 4095)
            c8, c12 = fwd_2d(r8, t, typ), fwd_2d(r12, t, typ)
            a1, a2 = digests(c8)
            b1, b2 = digests(c12)
            e8 = max(abs(x - y) for x, y in zip(inv_2d(c8, t, typ, 8), r8))
            e12 = max(abs(x - y) for x, y in zip(inv_2d(c12, t, typ, 12), r12))
            rows.append((t, typ, a1, a2, b1, b2, e8, e12))
    for r in rows:
        print("    ftx_kat(%d, %d, %d, %d, %d, %d, %d, %d);" % r)
    lb = []
    for seed in (101, 102, 103):
        lb.append(digests(fwd_2d(lcg_block(seed, 16, 4095), 0, 0, lossless=True)))
    print("# lossless (seed 101..103, 12-bit):", lb)
    print(f"# {len(rows)} (size, type) pairs")


def main():
    check_derivation()
    check_shifts()
    pix, coef = roundtrip_bounds()
    print("round trip, worst per size over every legal type (8- and 12-bit): |Inv(Fwd(r)) - r|")
    print("  " + "  ".join(f"{TX_NAMES[t]}:{pix[t]}" for t in range(19)))
    print("and |Fwd(Inv(D)) - D| on the kept coefficients:")
    print("  " + "  ".join(f"{TX_NAMES[t]}:{coef[t]}" for t in range(19)))
    if "--libaom" in sys.argv:
        check_libaom()
    if "--emit" in sys.argv:
        emit()
    if FAILS:
        print(f"{len(FAILS)} FAILED")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
