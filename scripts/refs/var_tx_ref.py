#!/usr/bin/env python3
# scripts/refs/var_tx_ref.py — spec-literal reference for the AV1 var-tx (inter
# transform-split) machinery: the txfm_split CONTEXT (spec 9.3) and the
# read_var_tx_size recursion shape (spec 5.11.37). The txfm_split CDF *values* are
# pinned separately (3-source verified). This port produces EXTERNAL known answers
# for the ctx formula — the #1 risk of the var-tx bite — and the leaf layout a
# split pattern produces. Transcribed from the AV1 spec §5.11.36/37 + §9.3,
# cross-checked against libaom txfm_partition_context / read_tx_size_vartx. NEVER
# derived from the Cyrius.

# TX enum order (TX_SIZES_ALL = 19).
TX_4X4, TX_8X8, TX_16X16, TX_32X32, TX_64X64 = 0, 1, 2, 3, 4
TX_W = [4, 8, 16, 32, 64, 4, 8, 8, 16, 16, 32, 32, 64, 4, 16, 8, 32, 16, 64]
TX_H = [4, 8, 16, 32, 64, 8, 4, 16, 8, 32, 16, 64, 32, 16, 4, 32, 8, 64, 16]
TX_SQR_UP = [0, 1, 2, 3, 4, 1, 1, 2, 2, 3, 3, 4, 4, 2, 2, 3, 3, 4, 4]
SPLIT_TX = [0, 0, 1, 2, 3, 0, 0, 1, 1, 2, 2, 3, 3, 5, 6, 7, 8, 9, 10]
TX_SIZES = 5
MAX_VARTX_DEPTH = 2

def find_tx_size(w, h):
    for t in range(19):
        if TX_W[t] == w and TX_H[t] == h:
            return t
    return TX_4X4

# ---- txfm_split ctx (spec 9.3) ----
def txfm_split_ctx(tx_sz, block_w, block_h, above_txw, left_txh):
    above = 1 if above_txw < TX_W[tx_sz] else 0
    left = 1 if left_txh < TX_H[tx_sz] else 0
    size = min(64, max(block_w, block_h))
    max_tx = find_tx_size(size, size)            # the largest square tx <= block
    c = 3 if TX_SQR_UP[tx_sz] != max_tx else 0
    return c + (TX_SIZES - 1 - max_tx) * 6 + above + left

# ---- read_var_tx_size leaf layout (spec 5.11.37) ----
# Given a split-decision oracle f(tx_sz, depth)->0/1, return the list of
# (row, col, tx_sz) leaves that InterTxSizes gets filled with, over a maxTx unit
# starting at (0,0). Positions are in 4x4 (MI) units.
def var_tx_leaves(root_tx, split_fn):
    leaves = []
    def rec(row, col, tx_sz, depth):
        w4, h4 = TX_W[tx_sz] // 4, TX_H[tx_sz] // 4
        split = 0
        if tx_sz != TX_4X4 and depth != MAX_VARTX_DEPTH:
            split = split_fn(tx_sz, depth, row, col)
        if split:
            sub = SPLIT_TX[tx_sz]
            sw, sh = TX_W[sub] // 4, TX_H[sub] // 4
            for i in range(0, h4, sh):
                for j in range(0, w4, sw):
                    rec(row + i, col + j, sub, depth + 1)
        else:
            for i in range(h4):
                for j in range(w4):
                    leaves.append((row + i, col + j, tx_sz))
    rec(0, 0, root_tx, 0)
    return leaves

def emit():
    print("# txfm_split ctx known answers (spec 9.3, spec-literal)")
    # a spread of cases: block size, current tx, above/left neighbour tx dims.
    cases = [
        # (tx_sz, block_w, block_h, above_txw, left_txh)
        (TX_16X16, 16, 16, 16, 16),   # root at a 16x16 block, neighbours equal
        (TX_16X16, 16, 16, 8, 16),    # above smaller -> above=1
        (TX_16X16, 16, 16, 16, 8),    # left smaller -> left=1
        (TX_16X16, 16, 16, 8, 8),     # both smaller
        (TX_8X8, 16, 16, 8, 8),       # a sub-split tx (sqrup 8 != max 16) -> +3
        (TX_32X32, 32, 32, 32, 32),   # 32-block root
        (TX_16X16, 32, 32, 16, 16),   # 16 tx in a 32 block (sub-split) -> +3
        (TX_8X8, 8, 8, 8, 8),         # 8-block root (max_tx=8 group, ctx 18..20)
        (TX_64X64, 64, 64, 64, 64),   # 64-block root (ctx 0..5)
        (TX_32X32, 64, 64, 32, 32),   # 32 tx in a 64 block (sub-split)
    ]
    for c in cases:
        print(f"  tx={c[0]} bw={c[1]} bh={c[2]} atxw={c[3]} lth={c[4]} -> ctx {txfm_split_ctx(*c)}")
    # a leaf layout: a 16x16 root split once into 4x TX_8X8 (split only at depth 0).
    def split_once(tx, depth, r, c):
        return 1 if depth == 0 else 0
    print("# 16x16 root split once -> 4x TX_8X8 leaves:")
    print("  ", var_tx_leaves(TX_16X16, split_once))
    # a mixed-depth layout: 16x16 -> 4x 8x8, and the top-left 8x8 further -> 4x 4x4.
    def split_tl(tx, depth, r, c):
        if depth == 0:
            return 1
        if depth == 1 and r == 0 and c == 0:
            return 1
        return 0
    print("# 16x16 root, top-left 8x8 further split to 4x4:")
    print("  ", var_tx_leaves(TX_16X16, split_tl))

if __name__ == "__main__":
    emit()
