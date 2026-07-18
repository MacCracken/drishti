#!/usr/bin/env python3
# mv_projection_ref.py — spec-literal reference for the AV1 motion-field projection leaves (spec 7.9.3
# get_mv_projection + 7.9.4 get_block_position / project). Oracle for drishti av1_get_mv_projection /
# av1_mv_project_pos / av1_get_block_position; never back-derived from Cyrius.

DIV_MULT = [0] + [16384 // i for i in range(1, 32)]   # floor(16384/i), Div_Mult[0]=0


def clip3(lo, hi, v):
    return lo if v < lo else (hi if v > hi else v)


def round2(x, n):
    return (x + (1 << (n - 1))) >> n if n else x


def round2_signed(x, n):
    return round2(x, n) if x >= 0 else -round2(-x, n)


def get_mv_projection(mv_row, mv_col, num, den):
    cd = min(31, den)
    cn = clip3(-31, 31, num)
    dm = DIV_MULT[cd]
    pr = clip3(-16383, 16383, round2_signed(mv_row * cn * dm, 14))
    pc = clip3(-16383, 16383, round2_signed(mv_col * cn * dm, 14))
    return pr, pc


def project(v8, delta, dst_sign, max8, max_off8):
    base8 = (v8 >> 3) << 3
    offset8 = delta >> 6 if delta >= 0 else -((-delta) >> 6)
    nv = v8 + dst_sign * offset8
    if nv < 0 or nv >= max8 or nv < base8 - max_off8 or nv >= base8 + 8 + max_off8:
        return -1
    return nv


def get_block_position(x8, y8, dst_sign, proj_row, proj_col, mi_rows, mi_cols):
    pos_y = project(y8, proj_row, dst_sign, mi_rows >> 1, 0)
    pos_x = project(x8, proj_col, dst_sign, mi_cols >> 1, 8)
    if pos_y < 0 or pos_x < 0:
        return 0, 0, 0
    return 1, pos_y, pos_x


if __name__ == "__main__":
    print("# Div_Mult spot:", DIV_MULT[1], DIV_MULT[3], DIV_MULT[5], DIV_MULT[16], DIV_MULT[31])
    print("# get_mv_projection cases (mv_row, mv_col, num, den) -> (projRow, projCol)")
    proj_cases = [
        (100, -200, 2, 4),      # basic + negative-round on col
        (-100, 100, 3, 7),      # negative row -> the round2_signed negative branch
        (1, 1, -31, 2),         # HALF-BOUNDARY: round2_signed=-16 vs plain round2=-15 (ties-away witness)
        (100, 100, 50, 4),      # num > 31 -> clippedNum 31
        (100, 100, -50, 4),     # num < -31 -> clippedNum -31
        (100, 100, 2, 40),      # den > 31 -> clippedDenom 31
        (16383, 0, 31, 1),      # huge product -> clip to 16383
        (-16383, 0, 31, 1),     # -> clip to -16383
    ]
    for (r, c, n, d) in proj_cases:
        print(f"proj({r},{c},{n},{d}) = {get_mv_projection(r, c, n, d)}")
    print("# project(v8, delta, dstSign, max8, maxOff8) -> newpos or -1")
    pp_cases = [
        (10, 0, 1, 34, 0),      # delta 0 -> stays 10 (base 8, window [8,16) with maxOff 0)
        (10, 128, 1, 34, 0),    # +2 -> 12 (in window)
        (10, -128, 1, 34, 0),   # negate-shift-negate: -2 -> 8 (base8, in window)
        (10, -200, 1, 34, 8),   # NON-multiple: -(200>>6)=-3 -> 7; arithmetic -200>>>6=-4 -> 6 (trap witness)
        (10, -256, 1, 34, 0),   # -4 -> 6 (< base8=8 -> reject, maxOff8=0)
        (10, 0, -1, 34, 0),     # dstSign -1, delta 0 -> 10
        (2, -256, 1, 34, 0),    # -4 -> -2 -> reject (nv<0)
        (30, 512, 1, 34, 0),    # +8 -> 38 -> reject (>=max8=34)
        (10, 512, 1, 34, 8),    # +8 -> 18, base8=8 window [0,24) maxOff8=8 -> valid
    ]
    for (v, dl, s, mx, mo) in pp_cases:
        print(f"project({v},{dl},{s},{mx},{mo}) = {project(v, dl, s, mx, mo)}")
    print("# get_block_position(x8,y8,dstSign,projRow,projCol,MiRows,MiCols)")
    bp_cases = [
        (5, 5, 1, 128, 128, 20, 20),    # +2 both -> (7,7) valid
        (5, 5, 1, -256, 0, 20, 20),     # row -4 -> 1 < base8=0? base8=0, [0,8) maxOff0 -> 1 valid; col 0 -> 5; valid
        (5, 5, 1, 0, 4096, 20, 20),     # col +64 -> way out -> invalid (0)
    ]
    for (x, y, s, pr, pc, mr, mc) in bp_cases:
        print(f"blockpos({x},{y},{s},{pr},{pc},{mr},{mc}) = {get_block_position(x, y, s, pr, pc, mr, mc)}")
