#!/usr/bin/env python3
# warp_affine_ref.py — spec-literal reference for AV1 block_warp (spec 7.11.3.5), the per-8x8
# warp KERNEL. Ported directly from the cached dav1d warp_affine_8x8_c (mc_tmpl.c 799-831),
# reusing the MD5-anchored Warped_Filters table. The oracle for drishti av1_warp_affine_8x8;
# never back-derived from the Cyrius.
#
# Two passes over a 15x15 padded source grid (grid[gr][gc] = source row/col (dy-3+gr, dx-3+gc);
# the (dx,dy) block top-left is grid[3][3]):
#   Horizontal (15 rows x 8 cols -> signed mid): phase mx + beta*r, stepping +alpha per col;
#     offs = 64 + Round2(tmx, 10); dot of Warped_Filters[offs] over grid[r][c..c+7];
#     mid = Round2(dot, 7-ib).  (7-ib, NOT 6-ib: the warp table sums to 128, not 64.)
#   Vertical (8x8): phase my + delta*r, +gamma per col; dot over mid rows r..r+7;
#     out = Clip1(Round2(dot, 7+ib), bd).
# ib = 4 (8/10-bit) or 2 (12-bit).

import sys
sys.path.insert(0, "scripts/refs")
from warp_filter_ref import WARP_FILTER


def intermediate_bits(bd):
    return 2 if bd == 12 else 4


def round2(x, n):
    # av1_round2: (x + (1<<(n-1))) >>> n; Python >> on the biased value is arithmetic.
    return (x + (1 << (n - 1))) >> n


def clip1(v, bd):
    hi = (1 << bd) - 1
    return 0 if v < 0 else (hi if v > hi else v)


def warp_affine_8x8(grid, alpha, beta, gamma, delta, mx, my, bd):
    ib = intermediate_bits(bd)
    mid = [[0] * 8 for _ in range(15)]
    for r in range(15):
        tmx = mx + beta * r
        for c in range(8):
            offs = 64 + round2(tmx, 10)
            f = WARP_FILTER[offs]
            dot = sum(f[k] * grid[r][c + k] for k in range(8))
            mid[r][c] = round2(dot, 7 - ib)
            tmx += alpha
    out = [[0] * 8 for _ in range(8)]
    for r in range(8):
        tmy = my + delta * r
        for c in range(8):
            offs = 64 + round2(tmy, 10)
            f = WARP_FILTER[offs]
            dot = sum(f[k] * mid[r + k][c] for k in range(8))
            out[r][c] = clip1(round2(dot, 7 + ib), bd)
            tmy += gamma
    return out


def make_grid(bd, salt):
    # a deterministic 15x15 source grid, reproduced identically in the Cyrius test.
    if bd == 8:
        return [[((r * 13 + c * 7 + salt) % 251) + 3 for c in range(15)] for r in range(15)]
    return [[((r * 137 + c * 91 + salt) % 4093) + 1 for c in range(15)] for r in range(15)]


def checksum(out):
    # position-weighted checksum of the 8x8 output (matches the Cyrius mc_checksum weight i+1).
    ck = 0
    i = 0
    for r in range(8):
        for c in range(8):
            ck += (i + 1) * out[r][c]
            i += 1
    return ck


def main():
    # (name, bd, salt, alpha, beta, gamma, delta, mx, my) — shear params are multiples of 64
    # (setup_shear output); mx/my exercise zero / positive / negative fractional phases.
    cases = [
        ("K1_identity8", 8, 0, 0, 0, 0, 0, 0, 0),
        ("K2_shear8", 8, 0, 2048, 1024, 1024, 2048, 0, 0),
        ("K3_negphase8", 8, 5, 2048, 1024, 1024, 2048, 300, -300),
        ("K4_shear12", 12, 9, 1024, 512, 512, 1024, 200, -150),
        ("K5_bigneg8", 8, 3, -3072, -1024, -1024, -3072, -700, 500),
    ]
    for name, bd, salt, a, b, g, d, mx, my in cases:
        grid = make_grid(bd, salt)
        out = warp_affine_8x8(grid, a, b, g, d, mx, my, bd)
        flat = [out[r][c] for r in range(8) for c in range(8)]
        print("%-14s cs=%d  out[0][0]=%d out[3][3]=%d out[7][7]=%d"
              % (name, checksum(out), out[0][0], out[3][3], out[7][7]))


if __name__ == "__main__":
    main()
