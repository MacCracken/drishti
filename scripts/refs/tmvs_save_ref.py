#!/usr/bin/env python3
# tmvs_save_ref.py — spec-literal reference for the AV1 temporal-MV PRODUCER (spec 7.19 MV storage +
# 7.20 reference frame MV save). The oracle for drishti av1_mv_save_field; never back-derived from Cyrius.
#
# Reduces a decoded inter frame's MI grid to a compact per-8x8 motion field: cell (y8,x8) samples the MI
# grid at (2*y8+1, 2*x8+1). For list 0 THEN list 1 with NO break (a qualifying list-1 OVERWRITES list-0),
# a reference qualifies iff ref > INTRA_FRAME(0), get_relative_dist(OrderHints[ref], OrderHint) < 0
# (strictly display-past), and both MV components are within +-4095 (REFMVS_LIMIT = (1<<12)-1). Else the
# cell stores NONE(-1) + MfMv (0,0).

INTRA_FRAME = 0
REFMVS_LIMIT = (1 << 12) - 1   # 4095
ORDER_HINT_BITS = 7


def get_relative_dist(a, b):
    # spec 5.9.3 / get_relative_dist with enable_order_hint on.
    diff = a - b
    m = 1 << (ORDER_HINT_BITS - 1)
    diff = (diff & (m - 1)) - (diff & m)
    return diff


def save_field(h8, w8, cells, order_hints, order_hint):
    # cells: dict (mi_row, mi_col) -> {ref0, ref1, mv0:(r,c), mv1:(r,c)}; a missing cell is all-intra/zero.
    # order_hints: dict ref -> OrderHints[ref]. order_hint: the current frame's OrderHint.
    out = {}
    for y8 in range(h8):
        for x8 in range(w8):
            row, col = 2 * y8 + 1, 2 * x8 + 1
            c = cells.get((row, col), {})
            mfref, mvr, mvc = -1, 0, 0
            for lst in (0, 1):
                r = c.get("ref0" if lst == 0 else "ref1", INTRA_FRAME)
                if r > INTRA_FRAME:
                    if get_relative_dist(order_hints[r], order_hint) < 0:
                        mv = c.get("mv0" if lst == 0 else "mv1", (0, 0))
                        if abs(mv[0]) <= REFMVS_LIMIT and abs(mv[1]) <= REFMVS_LIMIT:
                            mfref, mvr, mvc = r, mv[0], mv[1]   # NO break: list-1 overwrites
            out[(y8, x8)] = (mfref, mvr, mvc)
    return out


# The witness grid the KAT builds (2x4 8x8 cells; fmi 4x8). LAST=1, LAST2=2, GOLDEN=4, BWDREF=5.
# OrderHint (current) = 8; LAST/LAST2/GOLDEN are display-PAST (hint < 8), BWDREF display-FUTURE (hint > 8).
if __name__ == "__main__":
    order_hint = 8
    order_hints = {1: 4, 2: 5, 4: 6, 5: 12}   # LAST=4 LAST2=5 GOLDEN=6 (past); BWDREF=12 (future)
    cells = {
        (1, 1): {"ref0": 1, "mv0": (10, 20), "ref1": 4, "mv1": (30, 40)},   # both past -> list1 (GOLDEN,(30,40))
        (1, 3): {"ref0": 1, "mv0": (50, 60), "ref1": 5, "mv1": (70, 80)},   # list1 future -> list0 (LAST,(50,60))
        (1, 5): {"ref0": 5, "mv0": (1, 2)},                                 # future -> NONE
        (1, 7): {"ref0": 0},                                                # intra -> NONE
        (3, 1): {"ref0": 1, "mv0": (4095, -4095)},                          # |mv|=4095 -> kept
        (3, 3): {"ref0": 1, "mv0": (4096, 0)},                              # row 4096 -> reject NONE
        (3, 5): {"ref0": 1, "mv0": (0, 4096)},                              # col 4096 -> reject NONE
        # 8x8 sampling: the ODD cell (3,7) is read; a decoy at even (2,6) must NOT be.
        (3, 7): {"ref0": 2, "mv0": (7, 8)},                                 # LAST2 past -> {2,(7,8)}
        (2, 6): {"ref0": 1, "mv0": (999, 999)},                             # decoy at EVEN cell (must be ignored)
    }
    field = save_field(2, 4, cells, order_hints, order_hint)
    for y8 in range(2):
        for x8 in range(4):
            print(f"cell[{y8}][{x8}] = {field[(y8, x8)]}")
