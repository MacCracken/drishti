#!/usr/bin/env python3
# scripts/refs/inter_residual_ref.py — spec-literal reference for the NON-SKIP
# INTER RESIDUAL's NEW logic (0.7.85): the inter transform-type derivation
# (get_tx_set / transform_type inverse maps / compute_tx_type inter chroma).
#
# The pixel path (motion compensation + dequant + inverse transform + add) is
# already reference-verified in prior bites (mc_driver_ref.py + the itx/recon
# reviews) and is composed from those verified leaves in the Cyrius test; what is
# NEW here — and what this port pins with EXTERNAL known answers — is the tx-type
# derivation for inter blocks. Values transcribed from the AV1 spec §5 / §10 and
# cross-checked against libaom (av1_ext_tx_inv / av1_ext_tx_used / get_ext_tx_set)
# and dav1d (dav1d_tx_types_per_set). NEVER derived from the Cyrius.
#
# Emits a table of known answers the Cyrius test asserts against.

# TxType enum (spec).
DCT_DCT, ADST_DCT, DCT_ADST, ADST_ADST = 0, 1, 2, 3
FLIPADST_DCT, DCT_FLIPADST, FLIPADST_FLIPADST, ADST_FLIPADST, FLIPADST_ADST = 4, 5, 6, 7, 8
IDTX, V_DCT, H_DCT, V_ADST, H_ADST, V_FLIPADST, H_FLIPADST = 9, 10, 11, 12, 13, 14, 15

# Tx set enum (the value get_tx_set returns; inter uses 0/1/2/3).
TX_SET_DCTONLY, TX_SET_INTER_1, TX_SET_INTER_2, TX_SET_INTER_3 = 0, 1, 2, 3

# Tx_Size_Sqr / Tx_Size_Sqr_Up indices: TX_4X4=0, TX_8X8=1, TX_16X16=2, TX_32X32=3.
TX4, TX8, TX16, TX32 = 0, 1, 2, 3

# ---- get_tx_set (spec §5, inter branch) ----
def get_tx_set_inter(sqr, sqr_up, reduced_tx_set):
    if sqr_up > TX32:
        return TX_SET_DCTONLY
    if reduced_tx_set or sqr_up == TX32:
        return TX_SET_INTER_3
    if sqr == TX16:
        return TX_SET_INTER_2
    return TX_SET_INTER_1

# ---- inter tx-type inverse maps (symbol -> TxType), spec §10 / libaom / dav1d ----
INV_SET1 = [IDTX, V_DCT, H_DCT, V_ADST, H_ADST, V_FLIPADST, H_FLIPADST,
            DCT_DCT, ADST_DCT, DCT_ADST, FLIPADST_DCT, DCT_FLIPADST, ADST_ADST,
            FLIPADST_FLIPADST, ADST_FLIPADST, FLIPADST_ADST]
INV_SET2 = [IDTX, V_DCT, H_DCT, DCT_DCT, ADST_DCT, DCT_ADST, FLIPADST_DCT,
            DCT_FLIPADST, ADST_ADST, FLIPADST_FLIPADST, ADST_FLIPADST, FLIPADST_ADST]
INV_SET3 = [IDTX, DCT_DCT]

# ---- Tx_Type_In_Set_Inter[set][txType] membership, spec §10 ----
IN_SET = {
    TX_SET_DCTONLY: [1] + [0] * 15,
    TX_SET_INTER_1: [1] * 16,
    TX_SET_INTER_2: [1] * 12 + [0] * 4,
    TX_SET_INTER_3: [1 if t in (DCT_DCT, IDTX) else 0 for t in range(16)],
}

# ---- compute_tx_type inter chroma (spec §5): chroma tx type = co-located luma
# TxType (for a UNIFORM-tx block the block's single luma TxType), gated to DCT_DCT
# if not in the chroma block's tx set. ----
def compute_tx_type_inter_chroma(chroma_sqr, chroma_sqr_up, reduced_tx_set, luma_tx_type,
                                 lossless):
    if lossless or chroma_sqr_up > TX32:
        return DCT_DCT
    txset = get_tx_set_inter(chroma_sqr, chroma_sqr_up, reduced_tx_set)
    if IN_SET[txset][luma_tx_type] == 0:
        return DCT_DCT
    return luma_tx_type

# ---- Default_Inter_Tx_Type CDFs (spec §10, forward-cumulative; 3-source verified
# vs libaom default_inter_ext_tx_cdf + dav1d). Each row is stored as its cumulative
# freqs + {32768, 0} (the terminator + adaptation count). ----
INTER_CDF_SET1 = [
    [4458, 5560, 7695, 9709, 13330, 14789, 17537, 20266, 21504, 22848, 23934, 25474, 27727, 28915, 30631],
    [1645, 2573, 4778, 5711, 7807, 8622, 10522, 15357, 17674, 20408, 22517, 25010, 27116, 28856, 30749],
]
INTER_CDF_SET2 = [770, 2421, 5225, 12907, 15819, 18927, 21561, 24089, 26595, 28526, 30529]
INTER_CDF_SET3 = [[16384], [4167], [1998], [748]]

# The absolute offsets in drishti's av1_noncoeffcdf blob (matches the port's layout).
INTER_CDF_BASE = 1634

def inter_cdf_blob():
    """Return [(abs_offset, value)] for every inter-tx CDF entry, in layout order."""
    out = []
    off = INTER_CDF_BASE
    for row in INTER_CDF_SET1:               # 2 rows x 17 (16 sym + count)
        for v in row + [32768, 0]:
            out.append((off, v)); off += 1
    for v in INTER_CDF_SET2 + [32768, 0]:    # 1 row x 13 (12 sym + count)
        out.append((off, v)); off += 1
    for row in INTER_CDF_SET3:               # 4 rows x 3 (2 sym + count)
        for v in row + [32768, 0]:
            out.append((off, v)); off += 1
    return out

def emit():
    print("# inter tx-type derivation known answers (spec-literal)")
    blob = inter_cdf_blob()
    print(f"## Default_Inter_Tx_Type CDF blob: {len(blob)} entries @ {blob[0][0]}..{blob[-1][0]}")
    for off, v in blob:
        print(f"  [{off}] = {v}")
    # get_tx_set over the reachable (sqr, sqr_up) combos, reduced 0/1.
    print("## get_tx_set(sqr, sqr_up, reduced) -> set")
    for sqr, sqr_up in [(TX4, TX4), (TX8, TX8), (TX16, TX16), (TX32, TX32),
                        (TX4, TX8), (TX8, TX16), (TX16, TX32)]:
        for r in (0, 1):
            print(f"  sqr={sqr} sqr_up={sqr_up} reduced={r} -> {get_tx_set_inter(sqr, sqr_up, r)}")
    # inverse maps.
    print("## INV_SET1 =", INV_SET1)
    print("## INV_SET2 =", INV_SET2)
    print("## INV_SET3 =", INV_SET3)
    # membership rows.
    for s in (TX_SET_DCTONLY, TX_SET_INTER_1, TX_SET_INTER_2, TX_SET_INTER_3):
        print(f"## IN_SET[{s}] =", IN_SET[s])
    # chroma co-location for a few luma types at 4:2:0 (chroma sqr = luma sqr for
    # square blocks under 4:2:0 the co-located luma type flows through).
    print("## compute_tx_type inter chroma (sqr, luma_tx) -> chroma_tx")
    for sqr in (TX4, TX8, TX16, TX32):
        for lt in (DCT_DCT, ADST_ADST, V_DCT, IDTX, H_ADST):
            print(f"  chroma_sqr={sqr} luma_tx={lt} -> "
                  f"{compute_tx_type_inter_chroma(sqr, sqr, 0, lt, 0)}")

if __name__ == "__main__":
    emit()
