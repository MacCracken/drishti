#!/usr/bin/env python3
# wedge_ref.py — spec-literal reference for AV1 WEDGE masked-compound mask generation.
#
# Ports spec 7.11.3.11 (wedge mask process) VERBATIM, sharing NO code with src/av1_mc.cyr:
# the three 1-D master ramps, Stage 1 (build OBLIQUE63 + VERTICAL 64x64 planes), Stage 2
# (derive OBLIQUE27/117/153 + HORIZONTAL), Stage 3 (per-block crop + flipSign), and the
# wedge_sign collapse. Emits known-answers the Cyrius av1_wedge_mask_build is pinned against.
# 3-source verified (spec + libaom + dav1d, compound_wedge.md).

MASK_MASTER_SIZE = 64
MAX_ALPHA = 64  # AOM_BLEND_A64_MAX_ALPHA = 1<<WEDGE_WEIGHT_BITS(6)

# direction enum
H, V, O27, O63, O117, O153 = 0, 1, 2, 3, 4, 5

# --- the three 1-D master ramps (0..64), hard literals (no closed form) ---
Wedge_Master_Oblique_Odd = [0] * 28 + [1, 2, 6, 18, 37, 53, 60, 63] + [64] * 28
Wedge_Master_Oblique_Even = [0] * 28 + [1, 4, 11, 27, 46, 58, 62, 63] + [64] * 28
Wedge_Master_Vertical = [0] * 29 + [2, 7, 21, 43, 57, 62, 64] + [64] * 28
assert len(Wedge_Master_Oblique_Odd) == 64
assert len(Wedge_Master_Oblique_Even) == 64
assert len(Wedge_Master_Vertical) == 64


def clip3(lo, hi, x):
    return lo if x < lo else (hi if x > hi else x)


def build_masters():
    # Master[dir] is a 64x64 grid (list of rows).
    M = [[[0] * 64 for _ in range(64)] for _ in range(6)]
    # Stage 1 — OBLIQUE63 + VERTICAL
    shift = MASK_MASTER_SIZE // 4  # 16
    for i in range(0, 64, 2):
        for j in range(64):
            M[O63][i][j] = Wedge_Master_Oblique_Even[clip3(0, 63, j - shift)]
        shift -= 1
        for j in range(64):
            M[O63][i + 1][j] = Wedge_Master_Oblique_Odd[clip3(0, 63, j - shift)]
        for j in range(64):
            M[V][i][j] = Wedge_Master_Vertical[j]
            M[V][i + 1][j] = Wedge_Master_Vertical[j]
    # Stage 2 — derive the other four planes
    for i in range(64):
        for j in range(64):
            msk = M[O63][i][j]
            M[O27][j][i] = msk               # transpose
            M[O117][i][63 - j] = 64 - msk    # hflip + complement
            M[O153][63 - j][i] = 64 - msk    # transpose + hflip + complement
            M[H][j][i] = M[V][i][j]          # transpose of vertical
    return M


MASTERS = build_masters()

# Wedge_Codebook[shape][16] = {direction, x_off, y_off}. shape 0=TALL, 1=WIDE, 2=SQUARE.
Wedge_Codebook = [
    [  # 0 TALL (hgtw)
        (O27, 4, 4), (O63, 4, 4), (O117, 4, 4), (O153, 4, 4),
        (H, 4, 2), (H, 4, 4), (H, 4, 6), (V, 4, 4),
        (O27, 4, 2), (O27, 4, 6), (O153, 4, 2), (O153, 4, 6),
        (O63, 2, 4), (O63, 6, 4), (O117, 2, 4), (O117, 6, 4),
    ],
    [  # 1 WIDE (hltw)
        (O27, 4, 4), (O63, 4, 4), (O117, 4, 4), (O153, 4, 4),
        (V, 2, 4), (V, 4, 4), (V, 6, 4), (H, 4, 4),
        (O27, 4, 2), (O27, 4, 6), (O153, 4, 2), (O153, 4, 6),
        (O63, 2, 4), (O63, 6, 4), (O117, 2, 4), (O117, 6, 4),
    ],
    [  # 2 SQUARE (heqw)
        (O27, 4, 4), (O63, 4, 4), (O117, 4, 4), (O153, 4, 4),
        (H, 4, 2), (H, 4, 6), (V, 2, 4), (V, 6, 4),
        (O27, 4, 2), (O27, 4, 6), (O153, 4, 2), (O153, 4, 6),
        (O63, 2, 4), (O63, 6, 4), (O117, 2, 4), (O117, 6, 4),
    ],
]

# eligible sizes: (mi_size, w, h)
ELIGIBLE = {
    3: (8, 8), 4: (8, 16), 5: (16, 8), 6: (16, 16), 7: (16, 32),
    8: (32, 16), 9: (32, 32), 18: (8, 32), 19: (32, 8),
}


def shape_of(w, h):
    if h > w:
        return 0  # TALL
    if h < w:
        return 1  # WIDE
    return 2      # SQUARE


def wedge_raw(w, h, wedge_index):
    # Stage 3 crop (nominal dims), returns (raw grid h x w, flipSign)
    shape = shape_of(w, h)
    dir_, xo, yo = Wedge_Codebook[shape][wedge_index]
    xoff = 32 - ((xo * w) >> 3)
    yoff = 32 - ((yo * h) >> 3)
    s = 0
    for j in range(w):
        s += MASTERS[dir_][yoff][xoff + j]
    for i in range(1, h):
        s += MASTERS[dir_][yoff + i][xoff]
    avg = (s + (w + h - 1) // 2) // (w + h - 1)
    flip = 1 if avg < 32 else 0
    raw = [[MASTERS[dir_][yoff + i][xoff + j] for j in range(w)] for i in range(h)]
    return raw, flip


def wedge_mask(w, h, wedge_index, wedge_sign):
    raw, flip = wedge_raw(w, h, wedge_index)
    inv = wedge_sign ^ flip
    return [[(64 - raw[i][j]) if inv else raw[i][j] for j in range(w)] for i in range(h)]


if __name__ == "__main__":
    # KAT-A: BLOCK_16X16 (square), wedge_index=6 = {VERTICAL,2,4}. xoff=28, row-invariant.
    raw, flip = wedge_raw(16, 16, 6)
    print("KAT-A 16x16 idx6 (VERT,2,4): flipSign =", flip, "(expect 1)")
    print("  raw row0 =", raw[0])
    m0 = wedge_mask(16, 16, 6, 0)
    m1 = wedge_mask(16, 16, 6, 1)
    print("  sign=0 row0 =", m0[0])
    print("  sign=1 row0 =", m1[0])
    assert flip == 1
    assert m0[0] == [64, 62, 57, 43, 21, 7, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0], m0[0]
    assert m1[0] == [0, 2, 7, 21, 43, 57, 62, 64, 64, 64, 64, 64, 64, 64, 64, 64], m1[0]
    # column-invariant (all rows equal for VERTICAL)
    assert all(m0[i] == m0[0] for i in range(16))

    # KAT-B: BLOCK_16X16, wedge_index=4 = {HORIZONTAL,4,2}. yoff=28, row-varying, col-invariant.
    rawB, flipB = wedge_raw(16, 16, 4)
    print("KAT-B 16x16 idx4 (HORIZ,4,2): flipSign =", flipB, "(expect 1)")
    mB0 = wedge_mask(16, 16, 4, 0)
    col0 = [mB0[i][0] for i in range(16)]
    print("  sign=0 col0 =", col0)
    assert flipB == 1
    assert col0 == [64, 62, 57, 43, 21, 7, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0], col0
    assert all(mB0[i][j] == mB0[i][0] for i in range(16) for j in range(16))  # col-invariant

    # W3: wedge_sign flips exactly (64 - m) at every pixel
    for (wi, ws) in [(0, 0), (2, 0), (9, 1), (14, 0)]:
        a = wedge_mask(16, 16, wi, 0)
        b = wedge_mask(16, 16, wi, 1)
        assert all(b[i][j] == 64 - a[i][j] for i in range(16) for j in range(16)), (wi,)
    print("W3 wedge_sign complement: OK")

    # W4: shape-class selection — idx4 differs across shapes
    sq = wedge_mask(16, 16, 4, 0)      # SQUARE {HORIZ,4,2} -> row boundary
    wide = wedge_mask(16, 8, 4, 0)     # WIDE   {VERT,2,4}  -> col boundary
    tall = wedge_mask(8, 16, 4, 0)     # TALL   {HORIZ,4,2} -> row boundary
    print("W4 shapes idx4: SQUARE col-invariant =", all(sq[i][j] == sq[i][0] for i in range(16) for j in range(16)),
          "; WIDE row-invariant =", all(wide[i][j] == wide[0][j] for i in range(8) for j in range(16)))

    # Dump a compact digest of every (size,index,sign) for the Cyrius KAT pins.
    print("== per-(size,index) flipSign + a few pinned pixels ==")
    for ms, (w, h) in sorted(ELIGIBLE.items()):
        for wi in range(16):
            raw, flip = wedge_raw(w, h, wi)
            m = wedge_mask(w, h, wi, 0)
            # digest: flipSign, mask[0][0], mask[h//2][w//2], mask[h-1][w-1]
            print(f"  ms={ms:2d} {w}x{h} idx={wi:2d} flip={flip} "
                  f"m00={m[0][0]:2d} mc={m[h//2][w//2]:2d} mll={m[h-1][w-1]:2d}")
