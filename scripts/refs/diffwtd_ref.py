#!/usr/bin/env python3
# diffwtd_ref.py — spec-literal reference for AV1 DIFFWTD (difference-weighted) masked compound.
#
# Ports the difference-weight mask (spec 7.11.3.12) + the mask blend (7.11.3.14) VERBATIM,
# sharing NO code with src/av1_mc.cyr. Emits known-answer (mask, blended) values the Cyrius is
# pinned against — a THIRD independent derivation, defeating any shared conceptual error between
# the impl and the test's inline oracle. Cross-checked vs libaom diffwtd_mask + dav1d w_mask.
#
# Intermediates t0/t1 are at bit_depth + ib (ib = 4 @8/10-bit, 2 @12-bit); base 38,
# DIFF_FACTOR 16, AOM_BLEND_A64_MAX_ALPHA 64, AOM_BLEND_A64_ROUND_BITS 6.

BASE = 38
DIFF_FACTOR_LOG2 = 4      # divisor 16
MAX_ALPHA = 64
BLEND_ROUND_BITS = 6      # log2(64)


def round2(x, n):
    # spec 4.7 Round2 (n >= 1). x may be signed.
    if n == 0:
        return x
    return (x + (1 << (n - 1))) >> n


def ib_for(bd):
    return 2 if bd == 12 else 4


def diffwtd_mask(t0, t1, mask_type, bd):
    # spec 7.11.3.12 — per pixel
    ib = ib_for(bd)
    d = abs(t0 - t1)
    d = round2(d, (bd - 8) + ib)          # diff-normalization
    m = BASE + (d >> DIFF_FACTOR_LOG2)     # floor divide by 16
    m = max(0, min(MAX_ALPHA, m))          # Clip3(0, 64, .)
    if mask_type != 0:
        m = MAX_ALPHA - m
    return m


def blend(t0, t1, m, bd):
    # spec 7.11.3.14 — Clip1(Round2(m*t0 + (64-m)*t1, ib+6))
    ib = ib_for(bd)
    s = m * t0 + (MAX_ALPHA - m) * t1
    v = round2(s, ib + BLEND_ROUND_BITS)
    return max(0, min((1 << bd) - 1, v))


def chroma_mask_420(mm):
    # 2x2 luma-mask average (spec 7.11.3.14 chroma subsample), plain Round2 by 2.
    return round2(mm[0] + mm[1] + mm[2] + mm[3], 2)


if __name__ == "__main__":
    # KATs pinned in tests/av1_mc_driver.tcyr. Pixel values p, intermediates t = p << ib
    # (integer-MV prep), so the whole path is reproduced from pixel pairs.
    print("== luma DIFFWTD: (p0, p1, bd, mask_type) -> mask m, blended out ==")
    cases = [
        (200, 40, 8, 0), (40, 200, 8, 0), (200, 40, 8, 1),
        (128, 128, 8, 0),                       # equal -> m=38
        (255, 0, 8, 0),                         # max 8-bit diff
        (900, 100, 10, 0), (100, 900, 10, 1),   # 10-bit
        (4000, 50, 12, 0),                      # 12-bit
    ]
    for p0, p1, bd, mt in cases:
        ib = ib_for(bd)
        t0 = p0 << ib
        t1 = p1 << ib
        m = diffwtd_mask(t0, t1, mt, bd)
        out = blend(t0, t1, m, bd)
        print(f"  p0={p0:4d} p1={p1:4d} bd={bd} mt={mt} -> m={m:2d} out={out}")

    print("== chroma 4:2:0: four luma (p0,p1) pairs (8-bit, mask_type=0) -> chroma mask ==")
    quad = [(200, 40), (40, 200), (128, 128), (255, 0)]
    mm = []
    for p0, p1 in quad:
        t0, t1 = p0 << 4, p1 << 4
        mm.append(diffwtd_mask(t0, t1, 0, 8))
    cm = chroma_mask_420(mm)
    print(f"  luma masks {mm} -> chroma m = {cm}")
    # a chroma blend with those + chroma preds (cp0,cp1)
    cp0, cp1 = 150, 90
    print(f"  chroma blend cp0={cp0} cp1={cp1} m={cm} -> {blend(cp0 << 4, cp1 << 4, cm, 8)}")
