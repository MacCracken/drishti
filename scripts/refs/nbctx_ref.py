#!/usr/bin/env python3
"""Spec-literal reference for the AV1 neighbour CDF contexts.

Transcribed DIRECTLY from the av1-spec text, NOT from drishti's Cyrius:

  06.bitstream.syntax.md, inter_frame_mode_info:
    LeftRefFrame[ 0 ] = AvailL ? RefFrames[ MiRow ][ MiCol-1 ][ 0 ] : INTRA_FRAME
    AboveRefFrame[ 0 ] = AvailU ? RefFrames[ MiRow-1 ][ MiCol ][ 0 ] : INTRA_FRAME
    LeftRefFrame[ 1 ] = AvailL ? RefFrames[ MiRow ][ MiCol-1 ][ 1 ] : NONE
    AboveRefFrame[ 1 ] = AvailU ? RefFrames[ MiRow-1 ][ MiCol ][ 1 ] : NONE
    LeftIntra = LeftRefFrame[ 0 ] <= INTRA_FRAME
    AboveIntra = AboveRefFrame[ 0 ] <= INTRA_FRAME
    LeftSingle = LeftRefFrame[ 1 ] <= INTRA_FRAME
    AboveSingle = AboveRefFrame[ 1 ] <= INTRA_FRAME

  09.parsing.process.md, is_inter:
    if ( AvailU && AvailL )
        ctx = (LeftIntra && AboveIntra) ? 3 : LeftIntra || AboveIntra
    else if ( AvailU || AvailL )
        ctx = 2 * (AvailU ? AboveIntra : LeftIntra)
    else
        ctx = 0

  09.parsing.process.md, comp_mode:
    if ( AvailU && AvailL ) {
        if ( AboveSingle && LeftSingle )
            ctx = check_backward( AboveRefFrame[ 0 ] ) ^ check_backward( LeftRefFrame[ 0 ] )
        else if ( AboveSingle )
            ctx = 2 + ( check_backward( AboveRefFrame[ 0 ] ) || AboveIntra)
        else if ( LeftSingle )
            ctx = 2 + ( check_backward( LeftRefFrame[ 0 ] ) || LeftIntra)
        else
            ctx = 4
    } else if ( AvailU ) {
        if ( AboveSingle ) ctx = check_backward( AboveRefFrame[ 0 ] )
        else               ctx = 3
    } else if ( AvailL ) {
        if ( LeftSingle )  ctx = check_backward( LeftRefFrame[ 0 ] )
        else               ctx = 3
    } else {
        ctx = 1
    }

    check_backward(refFrame) {
      return ( ( refFrame >= BWDREF_FRAME ) && ( refFrame <= ALTREF_FRAME ) )
    }
"""

INTRA_FRAME = 0
NONE = -1
BWDREF_FRAME = 5
ALTREF_FRAME = 7


def setup(avail_u, avail_l, cell_a, cell_l, grid_a=None, grid_l=None):
    """cell_* = (ref0, ref1) of the above/left MI cell (ignored when unavailable).

    grid_* = the extra per-cell grid values the 0.7.77 contexts read, as
    (CompGroupIdxs, CompoundIdxs, InterpFilters[0], InterpFilters[1]). Cells start
    memset-0, so the default models an untouched cell.
    """
    if grid_a is None:
        grid_a = (0, 0, 0, 0)
    if grid_l is None:
        grid_l = (0, 0, 0, 0)
    a_ref0 = cell_a[0] if avail_u else INTRA_FRAME
    a_ref1 = cell_a[1] if avail_u else NONE
    l_ref0 = cell_l[0] if avail_l else INTRA_FRAME
    l_ref1 = cell_l[1] if avail_l else NONE
    return {
        "AvailU": int(bool(avail_u)),
        "AvailL": int(bool(avail_l)),
        "AboveRefFrame": [a_ref0, a_ref1],
        "LeftRefFrame": [l_ref0, l_ref1],
        "AboveIntra": int(a_ref0 <= INTRA_FRAME),
        "LeftIntra": int(l_ref0 <= INTRA_FRAME),
        "AboveSingle": int(a_ref1 <= INTRA_FRAME),
        "LeftSingle": int(l_ref1 <= INTRA_FRAME),
        # unavailable neighbours' cached grid values are never consulted (every read is
        # Avail-guarded), so 0 is as good as anything there.
        "AboveCompGroupIdx": grid_a[0] if avail_u else 0,
        "AboveCompoundIdx": grid_a[1] if avail_u else 0,
        "AboveInterp": [grid_a[2], grid_a[3]] if avail_u else [0, 0],
        "LeftCompGroupIdx": grid_l[0] if avail_l else 0,
        "LeftCompoundIdx": grid_l[1] if avail_l else 0,
        "LeftInterp": [grid_l[2], grid_l[3]] if avail_l else [0, 0],
    }


def check_backward(ref_frame):
    return int(BWDREF_FRAME <= ref_frame <= ALTREF_FRAME)


def is_inter_ctx(n):
    if n["AvailU"] and n["AvailL"]:
        return 3 if (n["LeftIntra"] and n["AboveIntra"]) else int(bool(n["LeftIntra"] or n["AboveIntra"]))
    elif n["AvailU"] or n["AvailL"]:
        return 2 * (n["AboveIntra"] if n["AvailU"] else n["LeftIntra"])
    else:
        return 0


def comp_mode_ctx(n):
    if n["AvailU"] and n["AvailL"]:
        if n["AboveSingle"] and n["LeftSingle"]:
            return check_backward(n["AboveRefFrame"][0]) ^ check_backward(n["LeftRefFrame"][0])
        elif n["AboveSingle"]:
            return 2 + int(bool(check_backward(n["AboveRefFrame"][0]) or n["AboveIntra"]))
        elif n["LeftSingle"]:
            return 2 + int(bool(check_backward(n["LeftRefFrame"][0]) or n["LeftIntra"]))
        else:
            return 4
    elif n["AvailU"]:
        return check_backward(n["AboveRefFrame"][0]) if n["AboveSingle"] else 3
    elif n["AvailL"]:
        return check_backward(n["LeftRefFrame"][0]) if n["LeftSingle"] else 3
    else:
        return 1


def count_refs(n, frame_type):
    c = 0
    if n["AvailU"]:
        if n["AboveRefFrame"][0] == frame_type:
            c += 1
        if n["AboveRefFrame"][1] == frame_type:
            c += 1
    if n["AvailL"]:
        if n["LeftRefFrame"][0] == frame_type:
            c += 1
        if n["LeftRefFrame"][1] == frame_type:
            c += 1
    return c


def ref_count_ctx(counts0, counts1):
    if counts0 < counts1:
        return 0
    elif counts0 == counts1:
        return 1
    else:
        return 2


# --- the reference-context family (09.parsing.process.md), verbatim ---------------
# comp_ref:        last12Count = count_refs(LAST) + count_refs(LAST2)
#                  last3GoldCount = count_refs(LAST3) + count_refs(GOLDEN)
#                  ctx = ref_count_ctx(last12Count, last3GoldCount)
# comp_ref_p1:     ctx = ref_count_ctx(count_refs(LAST), count_refs(LAST2))
# comp_ref_p2:     ctx = ref_count_ctx(count_refs(LAST3), count_refs(GOLDEN))
# comp_bwdref:     brfarf2Count = count_refs(BWDREF) + count_refs(ALTREF2)
#                  ctx = ref_count_ctx(brfarf2Count, count_refs(ALTREF))
# comp_bwdref_p1:  ctx = ref_count_ctx(count_refs(BWDREF), count_refs(ALTREF2))
# single_ref_p1:   fwdCount = LAST + LAST2 + LAST3 + GOLDEN
#                  bwdCount = BWDREF + ALTREF2 + ALTREF
#                  ctx = ref_count_ctx(fwdCount, bwdCount)
# uni_comp_ref_p1: ctx = ref_count_ctx(count_refs(LAST2),
#                                      count_refs(LAST3) + count_refs(GOLDEN))
# ALIASES (the spec says "computed as in the CDF selection process for X"):
#   single_ref_p2 = comp_bwdref     single_ref_p3 = comp_ref
#   single_ref_p4 = comp_ref_p1     single_ref_p5 = comp_ref_p2
#   single_ref_p6 = comp_bwdref_p1  uni_comp_ref  = single_ref_p1
#   uni_comp_ref_p2 = comp_ref_p2
LAST_FRAME, LAST2_FRAME, LAST3_FRAME, GOLDEN_FRAME = 1, 2, 3, 4
ALTREF2_FRAME = 6


def comp_ref_ctx(n):
    return ref_count_ctx(count_refs(n, LAST_FRAME) + count_refs(n, LAST2_FRAME),
                         count_refs(n, LAST3_FRAME) + count_refs(n, GOLDEN_FRAME))


def comp_ref_p1_ctx(n):
    return ref_count_ctx(count_refs(n, LAST_FRAME), count_refs(n, LAST2_FRAME))


def comp_ref_p2_ctx(n):
    return ref_count_ctx(count_refs(n, LAST3_FRAME), count_refs(n, GOLDEN_FRAME))


def comp_bwdref_ctx(n):
    return ref_count_ctx(count_refs(n, BWDREF_FRAME) + count_refs(n, ALTREF2_FRAME),
                         count_refs(n, ALTREF_FRAME))


def comp_bwdref_p1_ctx(n):
    return ref_count_ctx(count_refs(n, BWDREF_FRAME), count_refs(n, ALTREF2_FRAME))


def single_ref_p1_ctx(n):
    fwd = (count_refs(n, LAST_FRAME) + count_refs(n, LAST2_FRAME)
           + count_refs(n, LAST3_FRAME) + count_refs(n, GOLDEN_FRAME))
    bwd = (count_refs(n, BWDREF_FRAME) + count_refs(n, ALTREF2_FRAME)
           + count_refs(n, ALTREF_FRAME))
    return ref_count_ctx(fwd, bwd)


def uni_comp_ref_p1_ctx(n):
    return ref_count_ctx(count_refs(n, LAST2_FRAME),
                         count_refs(n, LAST3_FRAME) + count_refs(n, GOLDEN_FRAME))


def is_samedir_ref_pair(ref0, ref1):
    return int((ref0 >= BWDREF_FRAME) == (ref1 >= BWDREF_FRAME))


def comp_ref_type_ctx(n):
    above0 = n["AboveRefFrame"][0]
    above1 = n["AboveRefFrame"][1]
    left0 = n["LeftRefFrame"][0]
    left1 = n["LeftRefFrame"][1]
    aboveCompInter = n["AvailU"] and not n["AboveIntra"] and not n["AboveSingle"]
    leftCompInter = n["AvailL"] and not n["LeftIntra"] and not n["LeftSingle"]
    aboveUniComp = aboveCompInter and is_samedir_ref_pair(above0, above1)
    leftUniComp = leftCompInter and is_samedir_ref_pair(left0, left1)

    if n["AvailU"] and not n["AboveIntra"] and n["AvailL"] and not n["LeftIntra"]:
        samedir = is_samedir_ref_pair(above0, left0)
        if not aboveCompInter and not leftCompInter:
            return 1 + 2 * samedir
        elif not aboveCompInter:
            return 1 if not leftUniComp else 3 + samedir
        elif not leftCompInter:
            return 1 if not aboveUniComp else 3 + samedir
        else:
            if not aboveUniComp and not leftUniComp:
                return 0
            elif not aboveUniComp or not leftUniComp:
                return 2
            else:
                return 3 + int((above0 == BWDREF_FRAME) == (left0 == BWDREF_FRAME))
    elif n["AvailU"] and n["AvailL"]:
        if aboveCompInter:
            return 1 + 2 * int(bool(aboveUniComp))
        elif leftCompInter:
            return 1 + 2 * int(bool(leftUniComp))
        else:
            return 2
    elif aboveCompInter:
        return 4 * int(bool(aboveUniComp))
    elif leftCompInter:
        return 4 * int(bool(leftUniComp))
    else:
        return 2


# --- the last three contexts (09.parsing.process.md), verbatim --------------------
# comp_group_idx:
#   ctx = 0
#   if ( AvailU ) { if ( !AboveSingle ) ctx += CompGroupIdxs[MiRow-1][MiCol]
#                   else if ( AboveRefFrame[0] == ALTREF_FRAME ) ctx += 3 }
#   if ( AvailL ) { if ( !LeftSingle )  ctx += CompGroupIdxs[MiRow][MiCol-1]
#                   else if ( LeftRefFrame[0] == ALTREF_FRAME ) ctx += 3 }
#   ctx = Min( 5, ctx )
# compound_idx:  same shape, ALTREF bump is 1 not 3, base is (fwd == bck) ? 3 : 0, NO clamp.
# interp_filter:
#   ctx = ( ( dir & 1 ) * 2 + ( RefFrame[1] > INTRA_FRAME ) ) * 4
#   leftType = 3; aboveType = 3
#   if ( AvailL ) { if ( RefFrames[MiRow][MiCol-1][0] == RefFrame[0] ||
#                        RefFrames[MiRow][MiCol-1][1] == RefFrame[0] )
#                       leftType = InterpFilters[MiRow][MiCol-1][dir] }
#   if ( AvailU ) { ... aboveType = InterpFilters[MiRow-1][MiCol][dir] }
#   if ( leftType == aboveType ) ctx += leftType
#   else if ( leftType == 3 )    ctx += aboveType
#   else if ( aboveType == 3 )   ctx += leftType
#   else                         ctx += 3
ALTREF_FRAME_ = 7


def comp_group_idx_ctx(n):
    ctx = 0
    if n["AvailU"]:
        if not n["AboveSingle"]:
            ctx += n["AboveCompGroupIdx"]
        elif n["AboveRefFrame"][0] == ALTREF_FRAME_:
            ctx += 3
    if n["AvailL"]:
        if not n["LeftSingle"]:
            ctx += n["LeftCompGroupIdx"]
        elif n["LeftRefFrame"][0] == ALTREF_FRAME_:
            ctx += 3
    return min(5, ctx)


def compound_idx_ctx(n, fwd_eq_bck):
    ctx = 3 if fwd_eq_bck else 0
    if n["AvailU"]:
        if not n["AboveSingle"]:
            ctx += n["AboveCompoundIdx"]
        elif n["AboveRefFrame"][0] == ALTREF_FRAME_:
            ctx += 1
    if n["AvailL"]:
        if not n["LeftSingle"]:
            ctx += n["LeftCompoundIdx"]
        elif n["LeftRefFrame"][0] == ALTREF_FRAME_:
            ctx += 1
    return ctx


def interp_filter_ctx(n, dir_, ref0, ref1):
    ctx = ((dir_ & 1) * 2 + int(ref1 > INTRA_FRAME)) * 4
    left_type = 3
    above_type = 3
    if n["AvailL"]:
        if n["LeftRefFrame"][0] == ref0 or n["LeftRefFrame"][1] == ref0:
            left_type = n["LeftInterp"][dir_ & 1]
    if n["AvailU"]:
        if n["AboveRefFrame"][0] == ref0 or n["AboveRefFrame"][1] == ref0:
            above_type = n["AboveInterp"][dir_ & 1]
    if left_type == above_type:
        return ctx + left_type
    elif left_type == 3:
        return ctx + above_type
    elif above_type == 3:
        return ctx + left_type
    else:
        return ctx + 3


if __name__ == "__main__":
    # Full enumeration over EVERY ref value: NONE(-1), INTRA(0), and all 7 references.
    # The earlier subset {-1,0,1,4,5,7} was inadequate: it omitted LAST2(2), LAST3(3) and
    # ALTREF2(6), which are exactly the frames comp_ref_p1 / comp_ref_p2 / comp_bwdref_p1 /
    # uni_comp_ref_p1 discriminate — their histograms had unreachable contexts as a result.
    REFS = [NONE, INTRA_FRAME, 1, 2, 3, 4, 5, 6, 7]
    rows = []
    for au in (0, 1):
        for al in (0, 1):
            for a0 in REFS:
                for a1 in REFS:
                    for l0 in REFS:
                        for l1 in REFS:
                            n = setup(au, al, (a0, a1), (l0, l1))
                            rows.append((au, al, a0, a1, l0, l1,
                                         is_inter_ctx(n), comp_mode_ctx(n)))
    print(f"total combos: {len(rows)}")
    ii = sorted({r[6] for r in rows})
    cm = sorted({r[7] for r in rows})
    print(f"is_inter_ctx range:  {ii}")
    print(f"comp_mode_ctx range: {cm}")
    # A compact digest the Cyrius test can check against: sum + per-value counts.
    print(f"is_inter_ctx  sum={sum(r[6] for r in rows)}")
    print(f"comp_mode_ctx sum={sum(r[7] for r in rows)}")
    for v in cm:
        print(f"  comp_mode_ctx=={v}: {sum(1 for r in rows if r[7]==v)}")
    for v in ii:
        print(f"  is_inter_ctx=={v}: {sum(1 for r in rows if r[6]==v)}")

    # --- the reference-context family, same exhaustive enumeration ----------------
    FAMILY = [
        ("comp_ref", comp_ref_ctx, 3),
        ("comp_ref_p1", comp_ref_p1_ctx, 3),
        ("comp_ref_p2", comp_ref_p2_ctx, 3),
        ("comp_bwdref", comp_bwdref_ctx, 3),
        ("comp_bwdref_p1", comp_bwdref_p1_ctx, 3),
        ("single_ref_p1", single_ref_p1_ctx, 3),
        ("uni_comp_ref_p1", uni_comp_ref_p1_ctx, 3),
        ("comp_ref_type", comp_ref_type_ctx, 5),
    ]
    print("\n--- reference-context family (same 5184 combos) ---")
    for (name, fn, nctx) in FAMILY:
        vals = []
        for au in (0, 1):
            for al in (0, 1):
                for a0 in REFS:
                    for a1 in REFS:
                        for l0 in REFS:
                            for l1 in REFS:
                                vals.append(fn(setup(au, al, (a0, a1), (l0, l1))))
        hist = [sum(1 for v in vals if v == k) for k in range(nctx)]
        assert all(0 <= v < nctx for v in vals), f"{name} out of range"
        print(f"{name:16s} sum={sum(vals):6d}  hist={hist}")

    # --- the last three contexts -------------------------------------------------
    # Their input space adds the neighbour GRID values, so they get their own sweep.
    # comp_group_idx / compound_idx read CompGroupIdxs / CompoundIdxs (0/1 each);
    # interp_filter reads InterpFilters[dir] (0..2) and the current block's RefFrame[0..1].
    print("\n--- the last three contexts ---")
    cg, ci3 = [], []
    for au in (0, 1):
        for al in (0, 1):
            for a0 in REFS:
                for a1 in REFS:
                    for l0 in REFS:
                        for l1 in REFS:
                            for ag in (0, 1):
                                for lg in (0, 1):
                                    # DE-ALIASED (CompoundIdxs = 1-ag): comp_group_idx
                                    # and compound_idx are independent syntax elements,
                                    # and equal values would make a context reading the
                                    # WRONG plane invisible to the digests.
                                    n = setup(au, al, (a0, a1), (l0, l1),
                                              (ag, 1 - ag, 0, 0), (lg, 1 - lg, 0, 0))
                                    cg.append(comp_group_idx_ctx(n))
                                    for fe in (0, 1):
                                        ci3.append(compound_idx_ctx(n, fe))
    assert all(0 <= v <= 5 for v in cg), "comp_group_idx out of range"
    assert all(0 <= v <= 5 for v in ci3), "compound_idx out of range"
    print(f"comp_group_idx   n={len(cg):6d} sum={sum(cg):7d} "
          f"hist={[sum(1 for v in cg if v == k) for k in range(6)]}")
    print(f"compound_idx     n={len(ci3):6d} sum={sum(ci3):7d} "
          f"hist={[sum(1 for v in ci3 if v == k) for k in range(6)]}")

    itp = []
    for au in (0, 1):
        for al in (0, 1):
            for a0 in REFS:
                for l0 in REFS:
                    for ai in (0, 1, 2):
                        for li in (0, 1, 2):
                            for d in (0, 1):
                                for r0 in REFS:
                                    for r1 in (NONE, INTRA_FRAME, 5):
                                        n = setup(au, al, (a0, NONE), (l0, NONE),
                                                  (0, 0, ai, ai), (0, 0, li, li))
                                        itp.append(interp_filter_ctx(n, d, r0, r1))
    assert all(0 <= v < 16 for v in itp), "interp_filter out of range"
    print(f"interp_filter    n={len(itp):6d} sum={sum(itp):7d} "
          f"hist={[sum(1 for v in itp if v == k) for k in range(16)]}")
