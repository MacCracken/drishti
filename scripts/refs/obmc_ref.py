#!/usr/bin/env python3
# obmc_ref.py — spec-literal reference for AV1 OBMC (overlapped block motion compensation, spec
# 7.11.3.9 overlapped_motion_compensation + 7.11.3.10 overlap_blending). The oracle for drishti
# av1_obmc_predict; never back-derived from the Cyrius.
#
# INTEGER MVs only (mv % 8 == 0): the 8-tap MC then reduces to a pure edge-clamped pixel shift
# (the 0.7.58 subpel filter is the identity for integer positions — pinned separately), so this ref
# isolates the OBMC-SPECIFIC logic (neighbour scan, overlap extents, mask selection, the blend
# orientation, sequential in-place) from the MC filtering. Blend = Round2(m*own + (64-m)*nb, 6),
# where m (the Obmc_Mask own-weight) weights the CURRENT in-frame pixel and (64-m) the neighbour.

# Obmc_Mask (spec 7.11.3.9 get_obmc_mask) — OWN-weights; 64 - these == dav1d_obmc_masks.
OBMC_MASK = {
    2:  [45, 64],
    4:  [39, 50, 59, 64],
    8:  [36, 42, 48, 53, 57, 61, 64, 64],
    16: [34, 37, 40, 43, 46, 49, 52, 54, 56, 58, 60, 61, 64, 64, 64, 64],
    32: [33, 35, 36, 38, 40, 41, 43, 44, 45, 47, 48, 50, 51, 52, 53, 55,
         56, 57, 58, 59, 60, 60, 61, 62, 64, 64, 64, 64, 64, 64, 64, 64],
}


def round2(x, n):
    if n == 0:
        return x
    return (x + (1 << (n - 1))) >> n


def clip(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def ref_px(W, H, x, y):
    # the gradient reference (x + 2y) & 255, edge-clamped (matches it_ref_frame / mc emu_edge).
    xc = clip(x, 0, W - 1)
    yc = clip(y, 0, H - 1)
    return (xc + 2 * yc) & 255


def mc_shift(W, H, x, y, w, h, mv_row, mv_col):
    # integer-MV translation MC: out[i][j] = ref(x+j+mvx, y+i+mvy), edge-clamped. (spec 7.11.3.3
    # adds the MV into the reference position.) mv in 1/8 luma pel, integer here.
    dx = mv_col // 8
    dy = mv_row // 8
    return [[ref_px(W, H, x + j + dx, y + i + dy) for j in range(w)] for i in range(h)]


def obmc_scenario():
    # 128x128 frame, one 64x64 OBMC block at pixel (64,64) with a 64x64 ABOVE neighbour and a 64x64
    # LEFT neighbour, all inter with DISTINCT integer MVs (so the blend + orientation are observable).
    W = H = 128
    bx, by, bw, bh = 64, 64, 64, 64
    own_mv = (16, 8)                # 2 down, 1 right  -> gradient contribution 1 + 2*2 = 5
    above_mv = (0, 24)              # 0 down, 3 right  -> contribution 3 (!= 5, so above blend is real)
    left_mv = (40, 0)              # 5 down, 0 right  -> contribution 2*5 = 10 (!= 5, left blend real)

    # the block's own prediction, committed to the frame.
    blk = mc_shift(W, H, bx, by, bw, bh, own_mv[0], own_mv[1])   # blk[i][j], i/j block-relative

    # ABOVE pass: predW = min(nom_w, step4*4) = min(64,64)=64; predH = min(nom_h>>1, 32) = 32.
    # neighbour MC at the block's top-left (bx,by), 64x32; mask len 32 indexed by ROW i.
    aw, ah = 64, 32
    anb = mc_shift(W, H, bx, by, aw, ah, above_mv[0], above_mv[1])
    for i in range(ah):
        m = OBMC_MASK[32][i]
        for j in range(aw):
            blk[i][j] = round2(m * blk[i][j] + (64 - m) * anb[i][j], 6)

    # LEFT pass: predW = min(nom_w>>1, 32) = 32; predH = min(nom_h, step4*4) = min(64,64)=64.
    # neighbour MC at (bx,by), 32x64; mask len 32 indexed by COL j; reads the ABOVE-modified blk.
    lw, lh = 32, 64
    lnb = mc_shift(W, H, bx, by, lw, lh, left_mv[0], left_mv[1])
    for i in range(lh):
        for j in range(lw):
            m = OBMC_MASK[32][j]
            blk[i][j] = round2(m * blk[i][j] + (64 - m) * lnb[i][j], 6)

    checksum = sum(sum(row) for row in blk)
    spots = {
        "corner_00": blk[0][0],      # (64,64): above then left (double blend)
        "above_only": blk[0][40],    # (104,64): col 40 >= 32 -> above only
        "left_only": blk[40][0],     # (64,104): row 40 >= 32 -> left only
        "own_only": blk[40][40],     # (104,104): neither -> unchanged own
        "top_row_edge": blk[0][63],  # (127,64): above row 0 col 63
    }
    return checksum, spots, blk


if __name__ == "__main__":
    cs, spots, _ = obmc_scenario()
    print("checksum", cs)
    for k, v in spots.items():
        print(k, v)
    # mask KAT anchor: 64 - dav1d_obmc_masks
    dav1d = {2: [19, 0], 4: [25, 14, 5, 0], 8: [28, 22, 16, 11, 7, 3, 0, 0]}
    for ln, arr in dav1d.items():
        assert OBMC_MASK[ln] == [64 - v for v in arr], ln
    print("mask-anchor OK")
