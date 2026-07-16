#!/usr/bin/env python3
"""Spec-literal reference port: the inter_block_mode_info (5.11.23) SYMBOL SCHEDULE.

Transcribed from 06.bitstream.syntax.md, "Inter block mode info syntax". The per-symbol
VALUES and CDFs belong to prior ports/bites (0.7.66-0.7.81); what the ORCHESTRATOR owns —
and what this port pins — is WHICH symbol groups a block codes, in WHICH order, under
WHICH state:

    read_ref_frames( )                          -- 5.11.25 (ref_frames_ref.py)
    isCompound = RefFrame[1] > INTRA_FRAME
    find_mv_stack( isCompound )                 -- no symbols
    YMode:  skip_mode            -> NEAREST_NEARESTMV, no symbol
            seg SKIP || GLOBALMV -> GLOBALMV, no symbol
            isCompound           -> @@compound_mode
            else                 -> @@new_mv [@@zero_mv [@@ref_mv]]
    DRL:    NEWMV/NEW_NEWMV      -> idx 0..1: drl_mode while NumMvFound > idx+1 (stop on 0)
            has_nearmv           -> RefMvIdx=1; idx 1..2: same loop
    assign_mv                    -> one read_mv per list whose get_mode(list) == NEWMV
    read_interintra_mode         -- 5.11.28 gate (may set RefFrame[1] = INTRA_FRAME)
    read_motion_mode             -- 5.11.27 gate (motion_mode_ref.py; sees post-ii ref1)
    read_compound_type           -- 5.11.29 (compound blocks only code symbols)
    interp filter tail:          -- SWITCHABLE: (dual ? 2 : 1) x needs_interp_filter
                                    else: nothing (both dirs take the frame filter)

Shares no code with src/*.cyr — asserted by tests/av1_intermode.tcyr (test_inter_block_*).
"""

NEARESTMV, NEARMV, GLOBALMV, NEWMV = 14, 15, 16, 17
NEAREST_NEARESTMV, NEAR_NEARMV = 18, 19
NEAREST_NEWMV, NEW_NEARESTMV, NEAR_NEWMV, NEW_NEARMV = 20, 21, 22, 23
GLOBAL_GLOBALMV, NEW_NEWMV = 24, 25
SWITCHABLE = 4


def get_mode(y_mode, ref_list):
    if ref_list == 0:
        if y_mode < NEAREST_NEARESTMV:
            return y_mode
        if y_mode in (NEW_NEWMV, NEW_NEARESTMV, NEW_NEARMV):
            return NEWMV
        if y_mode in (NEAREST_NEARESTMV, NEAREST_NEWMV):
            return NEARESTMV
        if y_mode in (NEAR_NEARMV, NEAR_NEWMV):
            return NEARMV
        return GLOBALMV
    if y_mode in (NEW_NEWMV, NEAREST_NEWMV, NEAR_NEWMV):
        return NEWMV
    if y_mode in (NEAREST_NEARESTMV, NEW_NEARESTMV):
        return NEARESTMV
    if y_mode in (NEAR_NEARMV, NEW_NEARMV):
        return NEARMV
    return GLOBALMV


def has_nearmv(y_mode):
    return y_mode in (NEARMV, NEAR_NEARMV, NEAR_NEWMV, NEW_NEARMV)


def drl_reads(y_mode, num_mv_found, ref_mv_idx):
    """How many @@drl_mode symbols 5.11.23's loops read for a target RefMvIdx."""
    reads = 0
    if y_mode in (NEWMV, NEW_NEWMV):
        for idx in (0, 1):
            if num_mv_found > idx + 1:
                reads += 1
                if ref_mv_idx == idx:          # drl_mode = 0 -> stop
                    break
    elif has_nearmv(y_mode):
        for idx in (1, 2):
            if num_mv_found > idx + 1:
                reads += 1
                if ref_mv_idx == idx:
                    break
    return reads


def schedule(skip_mode, seg_fixed, is_compound, y_mode, num_mv_found, ref_mv_idx,
             ii_coded, mm_branch, interp_switchable, dual, needs_interp):
    """The ordered symbol-group list for one block. seg_fixed = SKIP||GLOBALMV active;
    ii_coded = the 5.11.28 gate open; mm_branch in {'none','use_obmc','motion_mode'}
    (from motion_mode_ref.py); needs_interp per 5.11.23's needs_interp_filter."""
    out = ['ref_frames']
    if skip_mode:
        pass                                    # NEAREST_NEARESTMV, no mode symbol
    elif seg_fixed:
        pass                                    # GLOBALMV, no mode symbol
    elif is_compound:
        out.append('compound_mode')
    else:
        chain = {NEWMV: 1, GLOBALMV: 2}.get(y_mode, 3)
        out.append(f'inter_mode({chain})')
    n = drl_reads(y_mode, num_mv_found, ref_mv_idx)
    if n:
        out.append(f'drl_mode(x{n})')
    newmv_lists = sum(1 for l in range(1 + (1 if is_compound else 0))
                      if get_mode(y_mode, l) == NEWMV)
    if newmv_lists:
        out.append(f'read_mv(x{newmv_lists})')
    if ii_coded:
        out.append('interintra-group')
    if mm_branch != 'none':
        out.append(mm_branch)
    if is_compound and not skip_mode:
        out.append('compound-type-group')
    if interp_switchable:
        out.append(f'interp_filter(x{(2 if dual else 1) if needs_interp else 0})')
    return out


def main():
    # needs_interp (last column) per 5.11.23's needs_interp_filter: 0 for skip_mode /
    # LOCALWARP / a large GLOBALMV(-family) block whose model is not TRANSLATION.
    # The 0.7.82 adversarial review caught THREE wrong rows here (4, 8, 10) — the
    # port's inputs must be derived per-case, never copied across rows.
    cases = [
        ("1  single NEWMV, 16x16",       0, 0, 0, NEWMV, 2, 0, 0, 'motion_mode', 1, 0, 1),
        ("2  single NEARESTMV",          0, 0, 0, NEARESTMV, 1, 0, 0, 'motion_mode', 1, 0, 1),
        ("3  single NEARMV + DRL",       0, 0, 0, NEARMV, 3, 1, 0, 'motion_mode', 1, 0, 1),
        # 4: IDENTITY model -> needs_interp_filter = 0 (large GLOBALMV, gm != TRANSLATION)
        ("4  single GLOBALMV (IDENT)",   0, 0, 0, GLOBALMV, 1, 0, 0, 'motion_mode', 1, 0, 0),
        ("5  comp NEAREST_NEARESTMV",    0, 0, 1, NEAREST_NEARESTMV, 2, 0, 0, 'none', 1, 0, 1),
        ("6  comp NEW_NEWMV + DRL",      0, 0, 1, NEW_NEWMV, 3, 1, 0, 'none', 1, 0, 1),
        ("7  skip_mode",                 1, 0, 1, NEAREST_NEARESTMV, 2, 0, 0, 'none', 1, 0, 0),
        # 8: the seg path fixes YMode = GLOBALMV but 5.11.27 still runs — an IDENTITY
        # model is NOT gated (only > TRANSLATION is), so the warp branch codes
        # @@motion_mode; and needs_interp_filter = 0 (GLOBALMV + !TRANSLATION).
        ("8  seg GLOBALMV",              0, 1, 0, GLOBALMV, 1, 0, 0, 'motion_mode', 1, 0, 0),
        ("9  interintra (ref1->INTRA)",  0, 0, 0, NEWMV, 2, 0, 1, 'none', 1, 0, 1),
        # 10: motion_mode == LOCALWARP -> needs_interp_filter = 0
        ("10 warp-branch NEWMV (WARP)",  0, 0, 0, NEWMV, 2, 0, 0, 'motion_mode', 1, 0, 0),
        ("11 fixed-filter NEWMV",        0, 0, 0, NEWMV, 2, 0, 0, 'motion_mode', 0, 0, 1),
    ]
    print("== inter_block_mode_info symbol schedules ==")
    for (tag, sk, sf, ic, ym, n, r, ii, mm, sw, du, ni) in cases:
        s = schedule(sk, sf, ic, ym, n, r, ii, mm, sw, du, ni)
        print(f"  {tag:30s} -> {' | '.join(s)}")


if __name__ == "__main__":
    main()
