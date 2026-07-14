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


def setup(avail_u, avail_l, cell_a, cell_l):
    """cell_* = (ref0, ref1) of the above/left MI cell (ignored when unavailable)."""
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
