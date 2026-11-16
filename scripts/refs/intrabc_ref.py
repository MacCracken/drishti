#!/usr/bin/env python3
# intrabc_ref.py — spec-literal reference for the INTRA BLOCK COPY rules drishti implements in src/av1_intertile.cyr
# (av1_intrabc_dv_valid, av1_intrabc_default_pred). Shares NO code with it. Transcribed verbatim from the AV1 spec:
#
# is_mv_valid( isCompound ) (07.bitstream.semantics.md, "Assign mv semantics"), with use_intrabc = 1, isCompound = 0:
#     for comp: if Abs( Mv[ 0 ][ comp ] ) >= ( 1 << 14 ) return 0
#     bw = Block_Width[ MiSize ]; bh = Block_Height[ MiSize ]
#     if ( (Mv[ 0 ][ 0 ] & 7) || (Mv[ 0 ][ 1 ] & 7) ) return 0
#     deltaRow = Mv[ 0 ][ 0 ] >> 3; deltaCol = Mv[ 0 ][ 1 ] >> 3
#     srcTopEdge = MiRow * MI_SIZE + deltaRow; srcLeftEdge = MiCol * MI_SIZE + deltaCol
#     srcBottomEdge = srcTopEdge + bh; srcRightEdge = srcLeftEdge + bw
#     if ( HasChroma ) { if ( bw < 8 && subsampling_x ) srcLeftEdge -= 4
#                        if ( bh < 8 && subsampling_y ) srcTopEdge -= 4 }
#     if ( srcTopEdge < MiRowStart * MI_SIZE || srcLeftEdge < MiColStart * MI_SIZE ||
#          srcBottomEdge > MiRowEnd * MI_SIZE || srcRightEdge > MiColEnd * MI_SIZE ) return 0
#     sbSize = use_128x128_superblock ? BLOCK_128X128 : BLOCK_64X64; sbH = Block_Height[ sbSize ]
#     activeSbRow = (MiRow * MI_SIZE) / sbH; activeSb64Col = (MiCol * MI_SIZE) >> 6
#     srcSbRow = (srcBottomEdge - 1) / sbH; srcSb64Col = (srcRightEdge - 1) >> 6
#     totalSb64PerRow = ((MiColEnd - MiColStart - 1) >> 4) + 1
#     activeSb64 = activeSbRow * totalSb64PerRow + activeSb64Col
#     srcSb64 = srcSbRow * totalSb64PerRow + srcSb64Col
#     if ( srcSb64 >= activeSb64 - INTRABC_DELAY_SB64 ) return 0
#     gradient = 1 + INTRABC_DELAY_SB64 + use_128x128_superblock
#     wfOffset = gradient * (activeSbRow - srcSbRow)
#     if ( srcSbRow > activeSbRow || srcSb64Col >= activeSb64Col - INTRABC_DELAY_SB64 + wfOffset ) return 0
#     return 1
#
# assign_mv( 0 )'s intrabc fallback (06.bitstream.syntax.md, "Assign MV syntax"), when RefStackMv[ 0 ] and [ 1 ] are 0:
#     sbSize4 = Num_4x4_Blocks_High[ sbSize ]
#     if ( MiRow - sbSize4 < MiRowStart ) { PredMv[ 0 ][ 0 ] = 0
#                                           PredMv[ 0 ][ 1 ] = -(sbSize4 * MI_SIZE + INTRABC_DELAY_PIXELS) * 8 }
#     else { PredMv[ 0 ][ 0 ] = -(sbSize4 * MI_SIZE * 8); PredMv[ 0 ][ 1 ] = 0 }
#
# The spec's "/" truncates toward zero; every division here has non-negative operands, so // is exact. ">>" on a
# negative Mv is arithmetic in both the spec and Python; "&" is two's-complement in both.
#
# One clause is REDUNDANT for every legal tile: "srcSbRow > activeSbRow" can never be the first rule to fail. Tiles
# start on superblock boundaries, so a row of superblocks is worth at least the tile's whole 64-column count, and a
# source in a later row already fails "srcSb64 >= activeSb64 - INTRABC_DELAY_SB64". Removing it from drishti is an
# equivalent mutant; the clause stays, as the spec writes it.

MI_SIZE = 4
INTRABC_DELAY_SB64 = 4
INTRABC_DELAY_PIXELS = 256
# Block_Width / Block_Height in BLOCK_SIZES order (BLOCK_4X4 .. BLOCK_128X128, 22 sizes)
BW = [4, 4, 8, 8, 8, 16, 16, 16, 32, 32, 32, 64, 64, 64, 128, 128, 4, 16, 8, 32, 16, 64]
BH = [4, 8, 4, 8, 16, 8, 16, 32, 16, 32, 64, 32, 64, 128, 64, 128, 16, 4, 32, 8, 64, 16]


def is_mv_valid(mv_row, mv_col, mi_row, mi_col, mi_size, has_chroma, subx, suby, row_start, row_end, col_start,
                col_end, sb128):
    for comp in (mv_row, mv_col):
        if abs(comp) >= (1 << 14):
            return 0
    bw, bh = BW[mi_size], BH[mi_size]
    if (mv_row & 7) or (mv_col & 7):
        return 0
    dr, dc = mv_row >> 3, mv_col >> 3
    top = mi_row * MI_SIZE + dr
    left = mi_col * MI_SIZE + dc
    bottom = top + bh
    right = left + bw
    if has_chroma:
        if bw < 8 and subx:
            left -= 4
        if bh < 8 and suby:
            top -= 4
    if (top < row_start * MI_SIZE or left < col_start * MI_SIZE or bottom > row_end * MI_SIZE
            or right > col_end * MI_SIZE):
        return 0
    sbh = 128 if sb128 else 64
    active_sb_row = (mi_row * MI_SIZE) // sbh
    active_sb64_col = (mi_col * MI_SIZE) >> 6
    src_sb_row = (bottom - 1) // sbh
    src_sb64_col = (right - 1) >> 6
    total = ((col_end - col_start - 1) >> 4) + 1
    active_sb64 = active_sb_row * total + active_sb64_col
    src_sb64 = src_sb_row * total + src_sb64_col
    if src_sb64 >= active_sb64 - INTRABC_DELAY_SB64:
        return 0
    gradient = 1 + INTRABC_DELAY_SB64 + sb128
    wf = gradient * (active_sb_row - src_sb_row)
    if src_sb_row > active_sb_row or src_sb64_col >= active_sb64_col - INTRABC_DELAY_SB64 + wf:
        return 0
    return 1


def default_pred(mi_row, row_start, sb128):
    sb4 = 32 if sb128 else 16
    if mi_row - sb4 < row_start:
        return 0, -(sb4 * MI_SIZE + INTRABC_DELAY_PIXELS) * 8
    return -(sb4 * MI_SIZE * 8), 0


def lcg(seed):
    x = seed
    while True:
        x = (x * 1103515245 + 12345) % 2147483648
        yield x >> 16


def random_cases(n, seed):
    """The sweep tests/av1_intrabc.tcyr replays: a tile window, a block inside it, a whole-sample-biased DV."""
    r = lcg(seed)
    out = []
    for _ in range(n):
        sb128 = next(r) % 2
        col_start = (next(r) % 4) * 16
        row_start = (next(r) % 4) * 16
        col_end = col_start + 16 + next(r) % 160
        row_end = row_start + 16 + next(r) % 120
        mi_size = next(r) % 22
        mi_row = row_start + next(r) % (row_end - row_start)
        mi_col = col_start + next(r) % (col_end - col_start)
        has_chroma = next(r) % 2
        subx = next(r) % 2
        suby = subx & (next(r) % 2)
        # mostly whole-sample vectors pointing up / left, some fractional, some far
        mv_row = -((next(r) % 400) * 8)
        mv_col = ((next(r) % 700) - 500) * 8
        if next(r) % 16 == 0:
            mv_col += 1 + next(r) % 7          # fractional
        if next(r) % 32 == 0:
            mv_row = -(16384 + next(r) % 64)   # beyond the magnitude bound
        out.append((mv_row, mv_col, mi_row, mi_col, mi_size, has_chroma, subx, suby, row_start, row_end, col_start,
                    col_end, sb128))
    return out


def digest(values):
    h = 0
    for v in values:
        h = (h * 131 + (v & 0xFFFFFFFF)) % 2147483647
    return h


# Hand-picked boundary cases: (label, EXPECTED, mv_row, mv_col, MiRow, MiCol, MiSize, HasChroma, subx, suby,
# MiRowStart, MiRowEnd, MiColStart, MiColEnd, sb128). main() asserts every expectation, so a label cannot lie.
# Unless noted: a 0..80 x 0..120 MI tile (totalSb64PerRow 8), 64x64 superblocks, BLOCK_16X16 (6) at MiRow 32 / MiCol 96
# = pixel (128, 384): activeSbRow 2, activeSb64Col 6, activeSb64 22; a same-row source needs Sb64Col <= 1.
BOUNDARY = [
    ('same SB row, source Sb64Col 1 (right edge 127)', 1, 0, -272 * 8, 32, 96, 6, 1, 1, 1, 0, 80, 0, 120, 0),
    ('same SB row, source Sb64Col 2: inside the delay', 0, 0, -264 * 8, 32, 96, 6, 1, 1, 1, 0, 80, 0, 120, 0),
    ('fractional row', 0, -64 * 8 - 4, -272 * 8, 32, 96, 6, 1, 1, 1, 0, 80, 0, 120, 0),
    ('fractional col', 0, 0, -272 * 8 + 3, 32, 96, 6, 1, 1, 1, 0, 80, 0, 120, 0),
    ('previous SB row, source Sb64Col 6: inside the wavefront', 1, -64 * 8, 48 * 8, 32, 96, 6, 1, 1, 1, 0, 80, 0,
     120, 0),
    ('previous SB row, source Sb64Col 7: past the wavefront', 0, -64 * 8, 56 * 8, 32, 96, 6, 1, 1, 1, 0, 80, 0,
     120, 0),
    ('a later SB row', 0, 64 * 8, -272 * 8, 32, 96, 6, 1, 1, 1, 0, 80, 0, 120, 0),
    ('exactly the tile top-left', 1, -128 * 8, -384 * 8, 32, 96, 6, 1, 1, 1, 0, 80, 0, 120, 0),
    ('one row above the tile', 0, -129 * 8, -384 * 8, 32, 96, 6, 1, 1, 1, 0, 80, 0, 120, 0),
    ('one column left of the tile', 0, -128 * 8, -385 * 8, 32, 96, 6, 1, 1, 1, 0, 80, 0, 120, 0),
    ('4x4 at the tile top, no chroma', 1, -128 * 8, -320 * 8, 32, 96, 0, 0, 1, 1, 0, 80, 0, 120, 0),
    ('4x4 at the tile top, 4:2:0 chroma pulls top 4 above it', 0, -128 * 8, -320 * 8, 32, 96, 0, 1, 1, 1, 0, 80, 0,
     120, 0),
    ('4x4 at the tile top, 4:4:4 chroma: no pull', 1, -128 * 8, -320 * 8, 32, 96, 0, 1, 0, 0, 0, 80, 0, 120, 0),
    ('bottom edge past the tile end (BLOCK_64X64 at MiRow 72)', 0, 0, -384 * 8, 72, 96, 12, 1, 1, 1, 0, 80, 0, 120,
     0),
    # magnitude: a 0..700-row tile, block at MiRow 600 (pixel 2400); 2047 samples up is legal, 2048 is not
    ('|mv_row| = (1 << 14) - 8', 1, -16376, 0, 600, 96, 6, 1, 1, 1, 0, 700, 0, 120, 0),
    ('|mv_row| = 1 << 14', 0, -16384, 0, 600, 96, 6, 1, 1, 1, 0, 700, 0, 120, 0),
    # 128x128 superblocks, a 0..80 x 0..200 MI tile (totalSb64PerRow 13): block at MiRow 64 (pixel 256, sb row 2),
    # MiCol 96; gradient 6 -> a source one SB row up may reach Sb64Col 7 (right edge 511) but not 8
    ('128-SB, one row up, source Sb64Col 7', 1, -128 * 8, 112 * 8, 64, 96, 6, 1, 1, 1, 0, 80, 0, 200, 1),
    ('128-SB, one row up, source Sb64Col 8', 0, -128 * 8, 120 * 8, 64, 96, 6, 1, 1, 1, 0, 80, 0, 200, 1),
    # a second tile starting at MiCol 64 (pixel 256): a block at MiCol 80 may not reach left of 256
    ('second tile, left of its start', 0, -64 * 8, -68 * 8, 32, 80, 6, 1, 1, 1, 0, 80, 64, 120, 0),
    # a 300-row frame (MiRowEnd 75, not superblock-aligned): BLOCK_64X64 (12) at MiRow 64 / MiCol 96, in the LAST SB
    # row. Only the bottom-edge rule separates these two: 16 up leaves the source at 240..303 (past 300), 48 up
    # at 208..271; both stay in the active SB row at Sb64Col 1, clear of the delay and the wavefront.
    ('last SB row, source bottom past the frame end', 0, -16 * 8, -320 * 8, 64, 96, 12, 1, 1, 1, 0, 75, 0, 120, 0),
    ('last SB row, source inside the frame', 1, -48 * 8, -320 * 8, 64, 96, 12, 1, 1, 1, 0, 75, 0, 120, 0),
    # the chroma pulls are per axis: BLOCK_4X8 (1) pulls only LEFT, BLOCK_8X4 (2) only UP (4:2:0, HasChroma)
    ('4x8 at the tile left edge: the left pull goes past it', 0, 0, -384 * 8, 32, 96, 1, 1, 1, 1, 0, 80, 0, 120, 0),
    ('4x8 one sample in: the left pull stays inside', 1, 0, -380 * 8, 32, 96, 1, 1, 1, 1, 0, 80, 0, 120, 0),
    ('8x4 at the tile top: the top pull goes past it', 0, -128 * 8, -320 * 8, 32, 96, 2, 1, 1, 1, 0, 80, 0, 120, 0),
    ('8x4 at the tile left edge: no left pull', 1, 0, -384 * 8, 32, 96, 2, 1, 1, 1, 0, 80, 0, 120, 0),
]


def main():
    print('default_pred: (MiRow, MiRowStart, sb128) -> (row, col)')
    for mr, rs, s in [(0, 0, 0), (15, 0, 0), (16, 0, 0), (40, 32, 0), (48, 32, 0), (31, 0, 1), (32, 0, 1),
                      (63, 32, 1), (64, 32, 1)]:
        print('  ', (mr, rs, s), default_pred(mr, rs, s))
    print('boundary cases (each asserted against its expectation):')
    for c in BOUNDARY:
        got = is_mv_valid(*c[2:])
        assert got == c[1], 'boundary case mislabelled: %s (spec says %d)' % (c[0], got)
        print('  %d  %s' % (got, c[0]))
    cases = random_cases(4000, 2024)
    res = [is_mv_valid(*c) for c in cases]
    print('random sweep: 4000 cases, %d valid, digest %d' % (sum(res), digest(res)))
    # the reasons, so the sweep is known to reach every branch
    print('sweep first-30 results:', res[:30])


if __name__ == '__main__':
    main()
