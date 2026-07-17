#!/usr/bin/env python3
# dist_wtd_ref.py — spec-literal reference for AV1 distance-weighted (jnt) compound.
#
# Ports get_relative_dist (spec 5.9.4) and the Distance weights process (spec 7.11.3.15)
# VERBATIM from the AV1 Bitstream & Decoding Process Specification, sharing NO code with
# src/av1_mc.cyr / src/av1_frame.cyr. Emits known-answer FwdWeight vectors that the Cyrius
# av1_dist_wtd_fwd is pinned against (never derive the Cyrius's expectation from itself).
#
# Cross-checked value-for-value against libaom av1_dist_wtd_comp_weight_assign
# (av1/common/reconinter.c) + dav1d (src/decode.c jnt_weights). See compound_distance.md.

MAX_FRAME_DISTANCE = 31

# spec 7.11.3.15 — VERBATIM. Row-major [4][2].
Quant_Dist_Weight = [[2, 3], [2, 5], [2, 7], [1, MAX_FRAME_DISTANCE]]
Quant_Dist_Lookup = [[9, 7], [11, 5], [12, 4], [13, 3]]


def get_relative_dist(a, b, enable_order_hint, order_hint_bits):
    # spec 5.9.4
    if not enable_order_hint:
        return 0
    diff = a - b
    m = 1 << (order_hint_bits - 1)
    diff = (diff & (m - 1)) - (diff & m)
    return diff


def clip3(lo, hi, v):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def ref_dist(order_hint_ref, order_hint_cur, enable_order_hint, order_hint_bits):
    # spec 7.11.3.15 dist[]: Clip3(0, MAX_FRAME_DISTANCE, Abs(get_relative_dist(...)))
    d = get_relative_dist(order_hint_ref, order_hint_cur, enable_order_hint, order_hint_bits)
    return clip3(0, MAX_FRAME_DISTANCE, abs(d))


def dist_weights(dist0, dist1):
    # spec 7.11.3.15 — returns (FwdWeight, BckWeight). FwdWeight -> preds[0]=ref0.
    d0 = dist1  # THE SWAP: d0 is ref1's distance
    d1 = dist0
    order = 1 if d0 <= d1 else 0
    if d0 == 0 or d1 == 0:
        return (Quant_Dist_Lookup[3][order], Quant_Dist_Lookup[3][1 - order])
    i = 0
    while i < 3:
        c0 = Quant_Dist_Weight[i][order]
        c1 = Quant_Dist_Weight[i][1 - order]
        if order:
            if d0 * c0 > d1 * c1:
                break
        else:
            if d0 * c0 < d1 * c1:
                break
        i += 1
    return (Quant_Dist_Lookup[i][order], Quant_Dist_Lookup[i][1 - order])


def fwd_from_hints(oh_ref0, oh_ref1, oh_cur, enable_order_hint=1, order_hint_bits=7):
    d0 = ref_dist(oh_ref0, oh_cur, enable_order_hint, order_hint_bits)
    d1 = ref_dist(oh_ref1, oh_cur, enable_order_hint, order_hint_bits)
    fwd, bck = dist_weights(d0, d1)
    return d0, d1, fwd, bck


if __name__ == "__main__":
    # invariant: every lookup row sums to 16 = DIST_PRECISION
    for row in Quant_Dist_Lookup:
        assert row[0] + row[1] == 16, row

    print("== dist_weights(dist0, dist1) -> (Fwd->ref0, Bck->ref1) ==")
    cases = [
        (1, 1), (2, 2), (7, 7), (31, 31),      # equal nonzero -> 7/9
        (1, 4), (4, 1),                         # unequal -> 13/3 and 3/13 (the swap witness)
        (2, 10), (10, 2),
        (1, 2), (2, 1), (1, 3), (3, 1),
        (0, 5), (5, 0), (0, 0),                 # zero-distance -> Lookup[3]
        (3, 20), (20, 3), (31, 1), (1, 31),
    ]
    for d0, d1 in cases:
        fwd, bck = dist_weights(d0, d1)
        print(f"  dist0={d0:2d} dist1={d1:2d} -> Fwd={fwd:2d} Bck={bck:2d} (sum={fwd + bck})")

    print("== fwd_from_hints(oh_ref0, oh_ref1, oh_cur) [enable_order_hint=1, bits=7] ==")
    hint_cases = [
        (8, 20, 10),    # dist0=2, dist1=10 -> Fwd=13
        (20, 8, 10),    # dist0=10, dist1=2 -> Fwd=3
        (9, 11, 10),    # dist0=1, dist1=1 (equal) -> Fwd=7
        (10, 10, 10),   # dist0=0, dist1=0 -> Lookup[3], order=1 -> Fwd=3
    ]
    for a, b, cur in hint_cases:
        d0, d1, fwd, bck = fwd_from_hints(a, b, cur)
        print(f"  oh_ref0={a} oh_ref1={b} oh_cur={cur} -> dist0={d0} dist1={d1} Fwd={fwd} Bck={bck}")

    # integer-MV combine oracle: for integer MVs, DISTANCE output = (r0*Fwd + r1*Bck + 8) >> 4
    print("== integer-MV combine oracle: (r0*Fwd + r1*Bck + 8) >> 4 ==")
    for (r0, r1, fwd) in [(200, 40, 13), (40, 200, 3), (255, 0, 7), (0, 255, 9), (128, 128, 13)]:
        bck = 16 - fwd
        out = (r0 * fwd + r1 * bck + 8) >> 4
        print(f"  r0={r0} r1={r1} Fwd={fwd} Bck={bck} -> {out}")
