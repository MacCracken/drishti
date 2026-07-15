#!/usr/bin/env python3
"""Spec-literal reference for AV1 find_warp_samples (7.10.4) + add_sample (7.10.4.2)
and has_overlappable_candidates.

Transcribed DIRECTLY from av1-spec 08.decoding.process.md, NOT from drishti's Cyrius.

has_overlappable_candidates( ) {
  if ( AvailU ) {
    w4 = Num_4x4_Blocks_Wide[ MiSize ]
    for ( x4 = MiCol; x4 < Min( MiCols, MiCol + w4 ); x4 += 2 ) {
        if ( RefFrames[ MiRow - 1 ][ x4 | 1 ][ 0 ] > INTRA_FRAME ) return 1
    }
  }
  if ( AvailL ) {
    h4 = Num_4x4_Blocks_High[ MiSize ]
    for ( y4 = MiRow; y4 < Min( MiRows, MiRow + h4 ); y4 += 2 ) {
        if ( RefFrames[ y4 | 1 ][ MiCol - 1 ][ 0 ] > INTRA_FRAME ) return 1
    }
  }
  return 0
}

find_warp_samples (7.10.4.1):
  doTopLeft = 1 ; doTopRight = 1
  if ( AvailU ) {
    srcSize = MiSizes[MiRow-1][MiCol] ; srcW = Num_4x4_Blocks_Wide[srcSize]
    if ( w4 <= srcW ) {
      colOffset = -(MiCol & (srcW - 1))
      if ( colOffset < 0 ) doTopLeft = 0
      if ( colOffset + srcW > w4 ) doTopRight = 0
      add_sample( -1, 0 )
    } else {
      for ( i = 0; i < Min( w4, MiCols - MiCol ); i += miStep ) {
        srcSize = MiSizes[MiRow-1][MiCol+i] ; srcW = Num_4x4_Blocks_Wide[srcSize]
        miStep = Min(w4, srcW)
        add_sample( -1, i )
      }
    }
  }
  if ( AvailL ) {
    srcSize = MiSizes[MiRow][MiCol-1] ; srcH = Num_4x4_Blocks_High[srcSize]
    if ( h4 <= srcH ) {
      rowOffset = -(MiRow & (srcH - 1))
      if ( rowOffset < 0 ) doTopLeft = 0
      add_sample( 0, -1 )
    } else {
      for ( i = 0; i < Min( h4, MiRows - MiRow); i += miStep ) {
        srcSize = MiSizes[MiRow+i][MiCol-1] ; srcH = Num_4x4_Blocks_High[srcSize]
        miStep = Min(h4, srcH)
        add_sample( i, -1 )
      }
    }
  }
  if ( doTopLeft ) add_sample( -1, -1 )
  if ( doTopRight ) { if ( Max( w4, h4 ) <= 16 ) add_sample( -1, w4 ) }
  if ( NumSamples == 0 && NumSamplesScanned > 0 ) NumSamples = 1

add_sample (7.10.4.2): exits if NumSamplesScanned >= LEAST_SQUARES_SAMPLES_MAX;
  mvRow/mvCol = MiRow+deltaRow / MiCol+deltaCol; returns unless is_inside, unless
  RefFrames[..][0] written this frame, unless RefFrames[..][0] == RefFrame[0], unless
  RefFrames[..][1] == NONE. Then candRow = mvRow & ~(candH4-1), candCol likewise;
  midY = candRow*4 + candH4*2 - 1 ; midX = candCol*4 + candW4*2 - 1;
  threshold = Clip3(16, 112, Max(Block_Width[MiSize], Block_Height[MiSize]));
  valid = (Abs(Mvs[candRow][candCol][0][0] - Mv[0][0])
         + Abs(Mvs[candRow][candCol][0][1] - Mv[0][1])) <= threshold
  cand = [midY*8, midX*8, midY*8 + mv[0], midX*8 + mv[1]]
  1. NumSamplesScanned += 1
  2. if valid == 0 and NumSamplesScanned > 1: exit
  3. CandList[NumSamples][j] = cand[j]
  4. if valid: NumSamples += 1
"""

INTRA_FRAME = 0
NONE = -1
LEAST_SQUARES_SAMPLES_MAX = 8

# Num_4x4_Blocks_Wide / High (spec 10), indexed by MiSize.
NUM_4X4_W = [1, 1, 2, 2, 2, 4, 4, 4, 8, 8, 8, 16, 16, 16, 32, 32, 1, 4, 2, 8, 4, 16]
NUM_4X4_H = [1, 2, 1, 2, 4, 2, 4, 8, 4, 8, 16, 8, 16, 32, 16, 32, 4, 1, 8, 2, 16, 4]


def block_w(sz):
    return 4 * NUM_4X4_W[sz]


def block_h(sz):
    return 4 * NUM_4X4_H[sz]


def clip3(lo, hi, v):
    return lo if v < lo else (hi if v > hi else v)


class Grid:
    """A frame-sized MI grid: per cell (avail, ref0, ref1, mi_size, mv_row, mv_col)."""

    def __init__(self, rows, cols):
        self.rows, self.cols = rows, cols
        self.cell = {}

    def set(self, r, c, avail, ref0, ref1, sz, mvr, mvc):
        self.cell[(r, c)] = (avail, ref0, ref1, sz, mvr, mvc)

    def put_block(self, r, c, sz, ref0, ref1, mvr, mvc):
        """Lay a real block down: every cell of its bw4 x bh4 footprint carries its
        values, exactly as spec 5.11.4's storage loop (drishti av1_mi_store_mode) does.
        This MATTERS — add_sample reads Mvs at the candidate BLOCK's top-left
        (candRow/candCol), which is only populated if the whole footprint was written."""
        for y in range(NUM_4X4_H[sz]):
            for x in range(NUM_4X4_W[sz]):
                if r + y < self.rows and c + x < self.cols:
                    self.set(r + y, c + x, 1, ref0, ref1, sz, mvr, mvc)

    def get(self, r, c):
        return self.cell.get((r, c), (0, 0, 0, 0, 0, 0))


class Ctx:
    def __init__(self, grid, mi_row, mi_col, mi_size, ref0,
                 row_start=0, row_end=None, col_start=0, col_end=None):
        self.g = grid
        self.mi_row, self.mi_col, self.mi_size, self.ref0 = mi_row, mi_col, mi_size, ref0
        self.row_start, self.col_start = row_start, col_start
        self.row_end = grid.rows if row_end is None else row_end
        self.col_end = grid.cols if col_end is None else col_end

    def is_inside(self, r, c):
        return (self.col_start <= c < self.col_end) and (self.row_start <= r < self.row_end)


def has_overlappable_candidates(ctx):
    g = ctx.g
    if ctx.is_inside(ctx.mi_row - 1, ctx.mi_col):
        w4 = NUM_4X4_W[ctx.mi_size]
        x4 = ctx.mi_col
        while x4 < min(g.cols, ctx.mi_col + w4):
            if g.get(ctx.mi_row - 1, x4 | 1)[1] > INTRA_FRAME:
                return 1
            x4 += 2
    if ctx.is_inside(ctx.mi_row, ctx.mi_col - 1):
        h4 = NUM_4X4_H[ctx.mi_size]
        y4 = ctx.mi_row
        while y4 < min(g.rows, ctx.mi_row + h4):
            if g.get(y4 | 1, ctx.mi_col - 1)[1] > INTRA_FRAME:
                return 1
            y4 += 2
    return 0


class Samples:
    def __init__(self):
        self.num = 0
        self.scanned = 0
        self.cand = [[0, 0, 0, 0] for _ in range(8)]


def add_sample(ctx, ws, delta_row, delta_col, mv_row, mv_col):
    if ws.scanned >= LEAST_SQUARES_SAMPLES_MAX:
        return
    mv_r = ctx.mi_row + delta_row
    mv_c = ctx.mi_col + delta_col
    if not ctx.is_inside(mv_r, mv_c):
        return
    avail, ref0, ref1, _sz, _mr, _mc = ctx.g.get(mv_r, mv_c)
    if avail != 1:
        return
    if ref0 != ctx.ref0:
        return
    if ref1 != NONE:
        return
    cand_sz = ctx.g.get(mv_r, mv_c)[3]
    cand_w4 = NUM_4X4_W[cand_sz]
    cand_h4 = NUM_4X4_H[cand_sz]
    cand_row = mv_r & ~(cand_h4 - 1)
    cand_col = mv_c & ~(cand_w4 - 1)
    mid_y = cand_row * 4 + cand_h4 * 2 - 1
    mid_x = cand_col * 4 + cand_w4 * 2 - 1
    threshold = clip3(16, 112, max(block_w(ctx.mi_size), block_h(ctx.mi_size)))
    cmv_row = ctx.g.get(cand_row, cand_col)[4]
    cmv_col = ctx.g.get(cand_row, cand_col)[5]
    valid = int((abs(cmv_row - mv_row) + abs(cmv_col - mv_col)) <= threshold)
    ws.scanned += 1
    if valid == 0 and ws.scanned > 1:
        return
    ws.cand[ws.num] = [mid_y * 8, mid_x * 8, mid_y * 8 + cmv_row, mid_x * 8 + cmv_col]
    if valid:
        ws.num += 1


def find_warp_samples(ctx, mv_row, mv_col):
    ws = Samples()
    g = ctx.g
    w4 = NUM_4X4_W[ctx.mi_size]
    h4 = NUM_4X4_H[ctx.mi_size]
    do_top_left = 1
    do_top_right = 1
    if ctx.is_inside(ctx.mi_row - 1, ctx.mi_col):
        src_size = g.get(ctx.mi_row - 1, ctx.mi_col)[3]
        src_w = NUM_4X4_W[src_size]
        if w4 <= src_w:
            col_offset = -(ctx.mi_col & (src_w - 1))
            if col_offset < 0:
                do_top_left = 0
            if col_offset + src_w > w4:
                do_top_right = 0
            add_sample(ctx, ws, -1, 0, mv_row, mv_col)
        else:
            i = 0
            while i < min(w4, g.cols - ctx.mi_col):
                ss = g.get(ctx.mi_row - 1, ctx.mi_col + i)[3]
                mi_step = min(w4, NUM_4X4_W[ss])
                add_sample(ctx, ws, -1, i, mv_row, mv_col)
                i += mi_step
    if ctx.is_inside(ctx.mi_row, ctx.mi_col - 1):
        src_size = g.get(ctx.mi_row, ctx.mi_col - 1)[3]
        src_h = NUM_4X4_H[src_size]
        if h4 <= src_h:
            row_offset = -(ctx.mi_row & (src_h - 1))
            if row_offset < 0:
                do_top_left = 0
            add_sample(ctx, ws, 0, -1, mv_row, mv_col)
        else:
            i = 0
            while i < min(h4, g.rows - ctx.mi_row):
                ss = g.get(ctx.mi_row + i, ctx.mi_col - 1)[3]
                mi_step = min(h4, NUM_4X4_H[ss])
                add_sample(ctx, ws, i, -1, mv_row, mv_col)
                i += mi_step
    if do_top_left:
        add_sample(ctx, ws, -1, -1, mv_row, mv_col)
    if do_top_right:
        if max(w4, h4) <= 16:
            add_sample(ctx, ws, -1, w4, mv_row, mv_col)
    if ws.num == 0 and ws.scanned > 0:
        ws.num = 1
    return ws


if __name__ == "__main__":
    # A 16x16 grid; the block under test at (4,4). Neighbours share ref0=1, single-ref.
    def mk(sz_above, sz_left, mv=(8, 8), ref0=1, ref1=NONE):
        """Tile the rows above and the columns left of the block at (4,4) with REAL
        blocks, aligned to their own size so candRow/candCol land on a written cell."""
        g = Grid(16, 16)
        aw, ah = NUM_4X4_W[sz_above], NUM_4X4_H[sz_above]
        for c in range(0, 16, aw):
            g.put_block((4 - ah) & ~(ah - 1), c, sz_above, ref0, ref1, mv[0], mv[1])
        lw, lh = NUM_4X4_W[sz_left], NUM_4X4_H[sz_left]
        for r in range(0, 16, lh):
            g.put_block(r, (4 - lw) & ~(lw - 1), sz_left, ref0, ref1, mv[0], mv[1])
        return g

    print("case                                   num scanned  cand[0]")
    for name, sz, sza, szl, mv, bmv in [
        ("16x16 blk, 16x16 nbrs, mv match", 6, 6, 6, (8, 8), (8, 8)),
        ("16x16 blk, 16x16 nbrs, mv far",   6, 6, 6, (900, 900), (8, 8)),
        ("8x8 blk, 8x8 nbrs",               3, 3, 3, (8, 8), (8, 8)),
        ("16x16 blk, 8x8 nbrs (step path)", 6, 3, 3, (8, 8), (8, 8)),
        ("8x8 blk, 32x32 nbrs (wide path)", 3, 9, 9, (8, 8), (8, 8)),
    ]:
        g = mk(sza, szl, mv)
        ctx = Ctx(g, 4, 4, sz, 1)
        ws = find_warp_samples(ctx, bmv[0], bmv[1])
        print(f"{name:38s} {ws.num:3d} {ws.scanned:7d}  {ws.cand[0]}")
        print(f"{'':38s} overlappable={has_overlappable_candidates(ctx)}")
