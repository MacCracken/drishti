#!/usr/bin/env python3
# warp_driver_ref.py — spec-literal reference for the AV1 warp prediction DRIVER (spec 7.11.3.5
# setup / dav1d recon_tmpl.c warp_affine). Ports the per-8x8 mx/my/dx/dy derivation + gather +
# crop, reusing the 0.7.96 kernel ref (warp_affine_ref.warp_affine_8x8). The oracle for
# drishti av1_warp_pred_block; never back-derived from the Cyrius.
#
# The model (wmmat + shear) is ASYMMETRIC (alpha!=beta AND gamma!=delta) so the KATs witness the
# -4*alpha-7*beta / -4*gamma-4*delta seed fold (a symmetric model cannot; 0.7.93 lesson).

import sys
sys.path.insert(0, "scripts/refs")
from warp_affine_ref import warp_affine_8x8


def clip(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def warp_pred_block(plane, pw, ph, x, y, w, h, subx, suby, m, alpha, beta, gamma, delta, bd):
    # plane: 2D list [ph][pw]; m = [m0..m5]. Returns the predicted w x h block (list[h][w]).
    out = [[0] * w for _ in range(h)]
    irow = y
    while irow < y + h:
        jcol = x
        while jcol < x + w:
            src_x = (jcol + 4) << subx
            src_y = (irow + 4) << suby
            dst_x = m[2] * src_x + m[3] * src_y + m[0]
            dst_y = m[4] * src_x + m[5] * src_y + m[1]
            x4 = dst_x >> subx          # arithmetic (Python >> floors negatives)
            y4 = dst_y >> suby
            ix4 = x4 >> 16
            sx4 = x4 & 0xFFFF
            iy4 = y4 >> 16
            sy4 = y4 & 0xFFFF
            mx = ((sx4 - 4 * alpha) - 7 * beta) & (-64)     # ~0x3f = -64 (two's complement)
            my = ((sy4 - 4 * gamma) - 4 * delta) & (-64)
            gx = ix4 - 7
            gy = iy4 - 7
            grid = [[plane[clip(gy + gr, 0, ph - 1)][clip(gx + gc, 0, pw - 1)]
                     for gc in range(15)] for gr in range(15)]
            o8 = warp_affine_8x8(grid, alpha, beta, gamma, delta, mx, my, bd)
            r2 = 0
            while r2 < 8 and irow + r2 < y + h:
                c2 = 0
                while c2 < 8 and jcol + c2 < x + w:
                    out[irow + r2 - y][jcol + c2 - x] = o8[r2][c2]
                    c2 += 1
                r2 += 1
            jcol += 8
        irow += 8
    return out


def make_plane(pw, ph, bd, salt):
    # a deterministic ref plane; reproduced identically in the Cyrius test.
    mask = 251 if bd == 8 else 4093
    add = 3 if bd == 8 else 1
    return [[((r * 29 + c * 17 + salt) % mask) + add for c in range(pw)] for r in range(ph)]


# an ASYMMETRIC near-identity warp: 2x2 = [1+1024/2^16, 512/2^16; -512/2^16, 1+1536/2^16],
# zero translation; shear alpha=256 beta=64 gamma=128 delta=320 (all != their pair, mult of 64).
WM = [0, 0, 65536 + 1024, 512, -512, 65536 + 1536]
# a NEGATIVE-translation variant (same 2x2 + shear): projects a low block off the top-left,
# so dst_x/dst_y go negative -> witnesses the arithmetic >>>16 / >>>subx (a logical shift there
# would produce a huge positive ix4/iy4 and read the wrong / OOB source).
WM_NEG = [-598000, -598000, 65536 + 1024, 512, -512, 65536 + 1536]
ALPHA, BETA, GAMMA, DELTA = 256, 64, 128, 320


def checksum(out, w, h):
    ck = 0
    i = 0
    for r in range(h):
        for c in range(w):
            ck += (i + 1) * out[r][c]
            i += 1
    return ck


def main():
    # (name, bd, subx, suby, pw, ph, x, y, w, h, salt)
    cases = [
        ("L_8x8", 8, 0, 0, 40, 40, 8, 8, 8, 8, 0, WM),
        ("L_16x16", 8, 0, 0, 40, 40, 8, 8, 16, 16, 0, WM),
        ("L_edge", 8, 0, 0, 40, 40, 0, 0, 8, 8, 7, WM),        # top-left -> emu_edge padding
        ("C_8x8_420", 8, 1, 1, 24, 24, 4, 4, 8, 8, 5, WM),     # chroma 4:2:0, 8x8 block
        ("C_4x4_crop", 8, 1, 1, 24, 24, 4, 4, 4, 4, 5, WM),    # 4x4 chroma -> 8x8 kernel, cropped
        ("L_16x16_12", 12, 0, 0, 40, 40, 8, 8, 16, 16, 9, WM),
        ("L_neg", 8, 0, 0, 40, 40, 0, 0, 8, 8, 3, WM_NEG),     # neg projection -> arith >>>16
        ("C_neg_420", 8, 1, 1, 24, 24, 0, 0, 8, 8, 3, WM_NEG),  # neg chroma -> arith >>>subx
    ]
    for name, bd, sx, sy, pw, ph, x, y, w, h, salt, wm in cases:
        pl = make_plane(pw, ph, bd, salt)
        out = warp_pred_block(pl, pw, ph, x, y, w, h, sx, sy, wm, ALPHA, BETA, GAMMA, DELTA, bd)
        print("%-12s cs=%d out[0][0]=%d out[%d][%d]=%d"
              % (name, checksum(out, w, h), out[0][0], h - 1, w - 1, out[h - 1][w - 1]))


if __name__ == "__main__":
    main()
