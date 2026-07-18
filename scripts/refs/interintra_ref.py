#!/usr/bin/env python3
# interintra_ref.py — spec-literal reference for AV1 SMOOTH inter-intra prediction.
#
# Ports the intra-mode variant (SMOOTH) mask (spec 7.11.3.13) + the interintra mask blend
# (7.11.3.14), sharing NO code with src/av1_mc.cyr. Emits known-answers the Cyrius
# av1_ii_smooth_mask_build + the blend are pinned against. 3-source verified (spec + libaom +
# dav1d, interintra.md). The mask value m weights the INTRA prediction; (64-m) weights inter.

MAX_SB_SIZE = 128
INTERINTRA_DC = 32

# Ii_Weights_1d[128] (spec markdown / libaom ii_weights1d, byte-identical), monotone 60..1.
Ii_Weights_1d = [
    60, 58, 56, 54, 52, 50, 48, 47, 45, 44, 42, 41, 39, 38, 37, 35,
    34, 33, 32, 31, 30, 29, 28, 27, 26, 25, 24, 23, 22, 22, 21, 20,
    19, 19, 18, 18, 17, 16, 16, 15, 15, 14, 14, 13, 13, 12, 12, 12,
    11, 11, 10, 10, 10, 9, 9, 9, 8, 8, 8, 8, 7, 7, 7, 7,
    6, 6, 6, 6, 6, 5, 5, 5, 5, 5, 4, 4, 4, 4, 4, 4,
    4, 4, 3, 3, 3, 3, 3, 3, 3, 3, 3, 2, 2, 2, 2, 2,
    2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
]
assert len(Ii_Weights_1d) == 128

# ii_mode: 0=DC, 1=V, 2=H, 3=SMOOTH  (interintra_mode enum)


def smooth_mask(w, h, ii_mode):
    scale = MAX_SB_SIZE // max(w, h)   # exact for {8,16,32}: 16/8/4
    m = [[0] * w for _ in range(h)]
    for i in range(h):
        for j in range(w):
            if ii_mode == 0:      # DC: flat
                v = INTERINTRA_DC
            elif ii_mode == 1:    # V: row-indexed
                v = Ii_Weights_1d[i * scale]
            elif ii_mode == 2:    # H: col-indexed
                v = Ii_Weights_1d[j * scale]
            else:                 # SMOOTH: min(i,j)
                v = Ii_Weights_1d[min(i, j) * scale]
            m[i][j] = v
    return m


def blend(intra, inter, m):
    # spec 7.11.3.14 interintra branch: final-precision, shift 6, no clip.
    return (m * intra + (64 - m) * inter + 32) >> 6


if __name__ == "__main__":
    # per-mode structure sanity
    for w, h in [(8, 8), (16, 16), (32, 32), (16, 8), (8, 16)]:
        for mode, name in [(0, "DC"), (1, "V"), (2, "H"), (3, "SMOOTH")]:
            m = smooth_mask(w, h, mode)
            # print corners + edge + center
            print(f"{w}x{h} {name}: m00={m[0][0]} m0last={m[0][w-1]} "
                  f"mlast0={m[h-1][0]} center={m[h//2][w//2]}")
    # V is row-constant, H col-constant, DC flat 32
    v = smooth_mask(16, 16, 1)
    assert all(v[i][j] == v[i][0] for i in range(16) for j in range(16)), "V row-constant"
    hh = smooth_mask(16, 16, 2)
    assert all(hh[i][j] == hh[0][j] for i in range(16) for j in range(16)), "H col-constant"
    dc = smooth_mask(16, 16, 0)
    assert all(dc[i][j] == 32 for i in range(16) for j in range(16)), "DC flat 32"

    print("== chroma regeneration (NOT averaging): 4:2:0 luma 32x32 V -> chroma 16x16 ==")
    cm = smooth_mask(16, 16, 1)   # chroma built at native 16x16
    print(f"  chroma V row0 weight = {cm[0][0]} (expect 60, NOT the 56 an average would give)")
    assert cm[0][0] == 60

    print("== position-weighted mask checksums (for the Cyrius KAT) ==")
    def cs(m, w, h):
        s = 0; k = 0
        for i in range(h):
            for j in range(w):
                k += 1; s += m[i][j] * k
        return s
    for w, h in [(8, 8), (16, 16), (32, 32), (16, 8), (8, 16), (32, 16), (16, 32)]:
        for mode in range(4):
            print(f"  {w}x{h} mode={mode} cs={cs(smooth_mask(w, h, mode), w, h)}")

    print("== blend KATs (m, intra, inter) -> out ==")
    for m, a, b in [(32, 200, 40), (60, 200, 40), (1, 200, 40), (32, 128, 128), (48, 900, 100)]:
        print(f"  m={m} intra={a} inter={b} -> {blend(a, b, m)}")
