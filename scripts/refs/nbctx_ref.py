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


if __name__ == "__main__":
    # Full enumeration over a ref-frame set spanning every semantic class:
    #   NONE(-1), INTRA(0), forward(1=LAST, 4=GOLDEN), backward(5=BWDREF, 7=ALTREF)
    REFS = [NONE, INTRA_FRAME, 1, 4, 5, 7]
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
