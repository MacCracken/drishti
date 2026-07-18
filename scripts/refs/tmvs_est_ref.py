#!/usr/bin/env python3
# tmvs_est_ref.py — spec-literal oracle for AV1 motion_field_estimation (spec 7.9.1 driver + 7.9.2
# projection + 7.9.3 get_mv_projection + 7.9.4 get_block_position/project). Independent transcription from
# the AV1 spec (re-fetched 7.9 PDF text) + dav1d refmvs.c cross-check — NOT derived from the Cyrius. Used to
# anchor tests/av1_mv.tcyr test_motion_field_estimation. Output-neutral bite (0.7.103, temporal-MV Bite 2b).
#
# drishti's saved motion field is ALREADY per-8x8 (av1_mv_save_field pre-sampled at the spec's odd 2*y8+1
# rows), so this oracle models each ref's saved field as a per-(y8,x8) {ref, (mvr,mvc)} grid and reads it at
# (y8,x8) directly — matching what av1_mv_projection consumes.

MAX_FRAME_DISTANCE = 31
LAST, LAST2, LAST3, GOLDEN, BWDREF, ALTREF2, ALTREF = 1, 2, 3, 4, 5, 6, 7
KEY_FRAME, INTER_FRAME, INTRA_ONLY_FRAME = 0, 1, 2
SENTINEL = -(1 << 15)  # -32768

DIV_MULT = [0] + [16384 // i for i in range(1, 32)]  # Div_Mult[0..31], floor(16384/i)


def clip3(lo, hi, v):
    return lo if v < lo else (hi if v > hi else v)


def round2signed(x, n):
    # Round2Signed(x,n) = (x>=0) ? (x + 2^(n-1))>>n : -((-x + 2^(n-1))>>n) — ties away from zero.
    if x >= 0:
        return (x + (1 << (n - 1))) >> n
    return -((-x + (1 << (n - 1))) >> n)


def get_relative_dist(order_hint_bits, a, b):
    diff = a - b
    m = 1 << (order_hint_bits - 1)
    diff = (diff & (m - 1)) - (diff & m)
    return diff


def get_mv_projection(mv, num, den):
    cd = min(MAX_FRAME_DISTANCE, den)
    cn = clip3(-MAX_FRAME_DISTANCE, MAX_FRAME_DISTANCE, num)
    out = []
    for i in range(2):
        out.append(clip3(-(1 << 14) + 1, (1 << 14) - 1,
                         round2signed(mv[i] * cn * DIV_MULT[cd], 14)))
    return out


def project(v8, delta, dst_sign, max8, max_off8):
    base8 = (v8 >> 3) << 3
    if delta >= 0:
        offset8 = delta >> 6
    else:
        offset8 = -((-delta) >> 6)
    nv = v8 + dst_sign * offset8
    valid = not (nv < 0 or nv >= max8 or nv < base8 - max_off8 or nv >= base8 + 8 + max_off8)
    return nv, valid


def get_block_position(x8, y8, dst_sign, proj_mv, mi_rows, mi_cols):
    pos_y8, vy = project(y8, proj_mv[0], dst_sign, mi_rows >> 1, 0)   # MAX_OFFSET_HEIGHT = 0
    pos_x8, vx = project(x8, proj_mv[1], dst_sign, mi_cols >> 1, 8)   # MAX_OFFSET_WIDTH  = 8
    return pos_y8, pos_x8, (vy and vx)


class Scene:
    """The current frame + DPB slot state the estimation reads."""
    def __init__(self, order_hint_bits, order_hint, mi_rows, mi_cols):
        self.ohb = order_hint_bits
        self.order_hint = order_hint
        self.mi_rows = mi_rows
        self.mi_cols = mi_cols
        self.order_hints = [0] * 8          # OrderHints[ref] for ref=LAST..ALTREF
        self.ref_frame_idx = [0] * 7        # ref_frame_idx[0..6] -> DPB slot
        # per DPB slot (0..7):
        self.slot_mi_rows = [0] * 8
        self.slot_mi_cols = [0] * 8
        self.slot_type = [INTER_FRAME] * 8
        self.slot_saved_order_hints = [[0] * 8 for _ in range(8)]   # SavedOrderHints[slot][ref]
        self.slot_field = [None] * 8        # dict (y8,x8) -> (ref, (mvr,mvc)), or None = no saved field

    def h8(self):
        return self.mi_rows >> 1

    def w8(self):
        return self.mi_cols >> 1


def motion_field_projection(sc, mf, src, dst_sign):
    src_idx = sc.ref_frame_idx[src - LAST]
    if sc.slot_mi_rows[src_idx] != sc.mi_rows or sc.slot_mi_cols[src_idx] != sc.mi_cols:
        return 0
    if sc.slot_type[src_idx] in (KEY_FRAME, INTRA_ONLY_FRAME):
        return 0
    field = sc.slot_field[src_idx]
    if field is None:
        return 0
    h8, w8 = sc.h8(), sc.w8()
    src_oh = sc.order_hints[src]
    ref_to_cur = get_relative_dist(sc.ohb, src_oh, sc.order_hint)   # src FIRST
    for y8 in range(h8):
        for x8 in range(w8):
            cell = field.get((y8, x8))
            if cell is None:
                continue
            src_ref, mv = cell
            if src_ref <= 0:  # > INTRA_FRAME(0)
                continue
            saved_oh = sc.slot_saved_order_hints[src_idx][src_ref]
            ref_offset = get_relative_dist(sc.ohb, src_oh, saved_oh)   # src FIRST
            if not (abs(ref_to_cur) <= MAX_FRAME_DISTANCE and
                    abs(ref_offset) <= MAX_FRAME_DISTANCE and ref_offset > 0):
                continue
            proj = get_mv_projection(mv, ref_to_cur * dst_sign, ref_offset)  # position finder, *dst_sign
            pos_y8, pos_x8, valid = get_block_position(x8, y8, dst_sign, proj, sc.mi_rows, sc.mi_cols)
            if not valid:
                continue
            for dst in range(LAST, ALTREF + 1):
                ref_to_dst = get_relative_dist(sc.ohb, sc.order_hint, sc.order_hints[dst])  # cur FIRST
                p = get_mv_projection(mv, ref_to_dst, ref_offset)   # NO *dst_sign
                mf[dst][pos_y8][pos_x8] = p
    return 1


def motion_field_estimation(sc):
    h8, w8 = sc.h8(), sc.w8()
    mf = [[[[SENTINEL, SENTINEL] for _ in range(w8)] for _ in range(h8)] for _ in range(8)]
    oh = sc.order_hint
    last_idx = sc.ref_frame_idx[0]
    use_last = sc.slot_saved_order_hints[last_idx][ALTREF] != sc.order_hints[GOLDEN]
    if use_last:
        motion_field_projection(sc, mf, LAST, -1)
    ref_stamp = 3 - 2  # MFMV_STACK_SIZE - 2 = 1
    if get_relative_dist(sc.ohb, sc.order_hints[BWDREF], oh) > 0:
        if motion_field_projection(sc, mf, BWDREF, 1) == 1:
            ref_stamp -= 1
    if get_relative_dist(sc.ohb, sc.order_hints[ALTREF2], oh) > 0:
        if motion_field_projection(sc, mf, ALTREF2, 1) == 1:
            ref_stamp -= 1
    if get_relative_dist(sc.ohb, sc.order_hints[ALTREF], oh) > 0 and ref_stamp >= 0:
        if motion_field_projection(sc, mf, ALTREF, 1) == 1:
            ref_stamp -= 1
    if ref_stamp >= 0:
        motion_field_projection(sc, mf, LAST2, -1)
    return mf


def build_witness_scene():
    """The test_motion_field_estimation scenario. 8x8 frame (h8=w8=4). LAST projects forward-ref-of-a-past
    frame (dstSign=-1) contributing a cell at (0,1); BWDREF projects (dstSign=+1) contributing a cell at
    (2,3); ALTREF2 returns 1 with an empty field (drives refStamp to -1) so ALTREF and LAST2 are SKIPPED —
    their would-contribute cells must be absent (the refStamp>=0 witness)."""
    sc = Scene(order_hint_bits=7, order_hint=16, mi_rows=8, mi_cols=8)
    sc.ref_frame_idx = [0, 1, 2, 3, 4, 5, 6]   # ref LAST..ALTREF -> slot 0..6
    sc.order_hints[LAST] = 12
    sc.order_hints[LAST2] = 8
    sc.order_hints[LAST3] = 10
    sc.order_hints[GOLDEN] = 4
    sc.order_hints[BWDREF] = 20
    sc.order_hints[ALTREF2] = 24
    sc.order_hints[ALTREF] = 32
    for s in range(8):
        sc.slot_mi_rows[s] = 8
        sc.slot_mi_cols[s] = 8
        sc.slot_type[s] = INTER_FRAME
    # slot0 = LAST: saved ALTREF hint 99 (!= GOLDEN 4) -> useLast; one contributing cell + a synthetic
    # INTRA(0) cell to witness the "> INTRA_FRAME" guard (never skipped by a real producer, but hand-built).
    sc.slot_saved_order_hints[0][ALTREF] = 99
    sc.slot_saved_order_hints[0][LAST] = 8      # refOffset = dist(12,8) = 4
    sc.slot_saved_order_hints[0][KEY_FRAME] = 8  # SavedOrderHints[0][0], read only by a >=INTRA mutant
    # (0,3) is a synthetic ref=0 (INTRA) cell with a SMALL in-window MV: a >=INTRA mutant would project it to
    # (0,3); the correct "> INTRA_FRAME" guard skips it, so (0,3) stays sentinel.
    sc.slot_field[0] = {(1, 1): (LAST, (64, 0)), (0, 3): (KEY_FRAME, (0, 16))}
    # slot4 = BWDREF: one contributing cell, dstSign=+1.
    sc.slot_saved_order_hints[4][LAST] = 16     # refOffset = dist(20,16) = 4
    sc.slot_field[4] = {(2, 2): (LAST, (0, 64))}
    # slot5 = ALTREF2: empty field -> projection returns 1, contributes nothing, drives refStamp to -1.
    sc.slot_field[5] = {}
    # slot6 = ALTREF: a would-contribute cell with a SMALL in-window MV -> if projected it lands at (1,0);
    # the correct refStamp<0 gate skips ALTREF, so (1,0) MUST stay sentinel.
    sc.slot_saved_order_hints[6][LAST] = 16     # refOffset = dist(32,16) = 16
    sc.slot_field[6] = {(1, 0): (LAST, (16, 0))}
    # slot1 = LAST2: a would-contribute cell with a SMALL in-window MV -> if projected it lands at (3,0);
    # the correct refStamp<0 gate skips LAST2, so (3,0) MUST stay sentinel.
    sc.slot_saved_order_hints[1][LAST] = 0      # refOffset = dist(8,0) = 8
    sc.slot_field[1] = {(3, 0): (LAST, (0, 16))}
    return sc


def main():
    sc = build_witness_scene()
    mf = motion_field_estimation(sc)
    h8, w8 = sc.h8(), sc.w8()
    print("# MotionFieldMvs non-sentinel cells (dst y8 x8 : row col):")
    for dst in range(LAST, ALTREF + 1):
        for y8 in range(h8):
            for x8 in range(w8):
                r, c = mf[dst][y8][x8]
                if r != SENTINEL or c != SENTINEL:
                    print(f"  dst={dst} y8={y8} x8={x8} : {r} {c}")
    # per-dst scale rows for the two contributing positions (mv magnitude 64, refOffset 4):
    print("# LAST cell -> pos (0,1); per-dst row proj (col=0):")
    print("  ", [mf[d][0][1][0] for d in range(LAST, ALTREF + 1)])
    print("# BWDREF cell -> pos (2,3); per-dst col proj (row=0):")
    print("  ", [mf[d][2][3][1] for d in range(LAST, ALTREF + 1)])


if __name__ == "__main__":
    main()
