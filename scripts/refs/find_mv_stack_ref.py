#!/usr/bin/env python3
"""find_mv_stack_ref.py -- the spatial MV candidate list (7.10.2), spec-literal: the scans, the stack, the driver.

tests/av1_mv.tcyr pins drishti's find_mv_stack with neighbour-scan cases (S1..S17: scan_row / scan_col /
scan_point, add_ref_mv_candidate, search_stack, compound_search_stack) and driver cases (D1..D12: the find MV
stack process, the sorting, extra search and context and clamping processes, clamp_mv_row / clamp_mv_col). The
generators of S1..S16 and D1..D10, two scratchpad ports (mvscan_ref.py, 0.7.64, and mvdriver_ref.py, 0.7.65), were
lost. Restoring them found three things those cases never witnessed — the column parity term of scan_row(-3), both
parity terms of scan_col(-3) (S14 and S15 laid one MV over the cell a wrong probe would hit), and both branches of
compound extra search's combine that D7 does not take — so S14 and S15 now carry decoy cells and S17, D11 and D12
are new. This replaces both ports, transcribed from 08.decoding.process.md (7.10.2, 7.10.2.2-4 and 7.10.2.7-14)
and 06.bitstream.syntax.md (is_inside, clamp_mv_row, clamp_mv_col); lower_mv_precision comes from mv_ref.py.

The port takes what drishti's context takes. drishti's caller supplies GlobalMvs[0..1] (the spec's steps 3-4 call
setup_global_mv, which mv_ref.py covers) and GmType per LIST (GmType[RefFrame[list]]); the temporal scan (step 5,
use_ref_frame_mvs) is left out, as every case here has it off (tmvs_scan_ref.py covers it). Grid cells default to
all-zero (an undecoded, intra, BLOCK_4X4 cell), as drishti's memset grid does, and "RefFrames[mvRow][mvCol][0] has
been written for this frame" is the cell's avail flag.

ONE SOURCE, deliberately. libaom's setup_ref_mv_list (av1/common/mvref_common.c, in ref/aom) and dav1d's refmvs.c
do not follow the spec call for call: libaom weights a row scan by `processed_rows`, folds rows -3 and -5 into one
loop, and decides the top-right probe from partition geometry (has_top_right) instead of a decoded flag; dav1d
keeps its own candidate grid. A random-grid differential against either would mostly test a model of their state.
The composed process is checked externally instead: drishti's decode of every published libaom test vector is
bit-exact (`make conformance`), and those streams exercise find_mv_stack on every inter block. Here, each case is
the spec's answer, and the ones that are arithmetic are derived by hand below and asserted.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mv_ref import lower_mv_precision, NUM_4X4_W, NUM_4X4_H   # noqa: E402

INTRA_FRAME = 0
TRANSLATION = 1
MI_SIZE = 4
REF_CAT_LEVEL = 640
MV_BORDER = 128
MAX_REF_MV_STACK_SIZE = 8
NEARESTMV, NEARMV, GLOBALMV, NEWMV = 14, 15, 16, 17
NEAREST_NEARESTMV, NEAR_NEARMV, NEAREST_NEWMV, NEW_NEARESTMV = 18, 19, 20, 21
NEAR_NEWMV, NEW_NEARMV, GLOBAL_GLOBALMV, NEW_NEWMV = 22, 23, 24, 25


def has_newmv(mode):
    return mode in (NEWMV, NEW_NEWMV, NEAR_NEWMV, NEW_NEARMV, NEAREST_NEWMV, NEW_NEARESTMV)


def clip3(lo, hi, v):
    return lo if v < lo else (hi if v > hi else v)


class Cell:
    """one MI cell: avail ("RefFrames has been written"), IsInters, MiSizes, YModes, RefFrames[2], Mvs[2]"""
    def __init__(self, avail=0, is_inter=0, mi_size=0, ymode=0, ref0=0, ref1=0, mv0=(0, 0), mv1=(0, 0)):
        self.avail, self.is_inter, self.mi_size, self.ymode = avail, is_inter, mi_size, ymode
        self.ref = [ref0, ref1]
        self.mv = [list(mv0), list(mv1)]


class Ctx:
    def __init__(self, dim, mi_size, mi_row, mi_col):
        self.MiRows = self.MiCols = dim
        self.cells = {}
        self.MiRowStart, self.MiRowEnd, self.MiColStart, self.MiColEnd = 0, dim, 0, dim
        self.MiRow, self.MiCol, self.MiSize = mi_row, mi_col, mi_size
        self.RefFrame = [1, 2]
        self.allow_hp, self.force_int = 1, 0
        self.GlobalMvs = [[0, 0], [0, 0]]
        self.GmTypeList = [0, 0]                      # GmType[RefFrame[0]], GmType[RefFrame[1]]
        self.sign_bias = {}
        self.RefStackMv = [[None, None] for _ in range(MAX_REF_MV_STACK_SIZE)]
        self.WeightStack = [0] * MAX_REF_MV_STACK_SIZE
        self.NumMvFound = self.NewMvCount = self.FoundMatch = 0
        self.CloseMatches = self.TotalMatches = None
        self.NewMvContext = self.RefMvContext = self.ZeroMvContext = None
        self.DrlCtxStack = [None] * MAX_REF_MV_STACK_SIZE

    def cell(self, r, c):
        return self.cells.get((r, c), Cell())

    def set_cell(self, r, c, *a):
        self.cells[(r, c)] = Cell(*a)

    def is_inside(self, r, c):
        return self.MiColStart <= c < self.MiColEnd and self.MiRowStart <= r < self.MiRowEnd

    def lower(self, mv):
        return lower_mv_precision(mv, self.allow_hp, self.force_int)

    def signbias(self, ref):
        return self.sign_bias.get(ref, 0)


# ---- 7.10.2.2 / 7.10.2.3 / 7.10.2.4 ------------------------------------------------------------------------------
def scan_row(ctx, deltaRow, isCompound):
    bw4 = NUM_4X4_W[ctx.MiSize]
    end4 = min(min(bw4, ctx.MiCols - ctx.MiCol), 16)
    deltaCol = 0
    useStep16 = bw4 >= 16
    if abs(deltaRow) > 1:
        deltaRow += ctx.MiRow & 1
        deltaCol = 1 - (ctx.MiCol & 1)
    i = 0
    while i < end4:
        mvRow = ctx.MiRow + deltaRow
        mvCol = ctx.MiCol + deltaCol + i
        if not ctx.is_inside(mvRow, mvCol):
            break
        ln = min(bw4, NUM_4X4_W[ctx.cell(mvRow, mvCol).mi_size])
        if abs(deltaRow) > 1:
            ln = max(2, ln)
        if useStep16:
            ln = max(4, ln)
        add_ref_mv_candidate(ctx, mvRow, mvCol, isCompound, ln * 2)
        i += ln


def scan_col(ctx, deltaCol, isCompound):
    bh4 = NUM_4X4_H[ctx.MiSize]
    end4 = min(min(bh4, ctx.MiRows - ctx.MiRow), 16)
    deltaRow = 0
    useStep16 = bh4 >= 16
    if abs(deltaCol) > 1:
        deltaRow = 1 - (ctx.MiRow & 1)
        deltaCol += ctx.MiCol & 1
    i = 0
    while i < end4:
        mvRow = ctx.MiRow + deltaRow + i
        mvCol = ctx.MiCol + deltaCol
        if not ctx.is_inside(mvRow, mvCol):
            break
        ln = min(bh4, NUM_4X4_H[ctx.cell(mvRow, mvCol).mi_size])
        if abs(deltaCol) > 1:
            ln = max(2, ln)
        if useStep16:
            ln = max(4, ln)
        add_ref_mv_candidate(ctx, mvRow, mvCol, isCompound, ln * 2)
        i += ln


def scan_point(ctx, deltaRow, deltaCol, isCompound):
    mvRow = ctx.MiRow + deltaRow
    mvCol = ctx.MiCol + deltaCol
    if ctx.is_inside(mvRow, mvCol) and ctx.cell(mvRow, mvCol).avail:
        add_ref_mv_candidate(ctx, mvRow, mvCol, isCompound, 4)


# ---- 7.10.2.7 / 7.10.2.8 / 7.10.2.9 ------------------------------------------------------------------------------
def add_ref_mv_candidate(ctx, mvRow, mvCol, isCompound, weight):
    c = ctx.cell(mvRow, mvCol)
    if not c.is_inter:
        return
    if not isCompound:
        for candList in range(2):
            if c.ref[candList] == ctx.RefFrame[0]:
                search_stack(ctx, mvRow, mvCol, candList, weight)
    elif c.ref[0] == ctx.RefFrame[0] and c.ref[1] == ctx.RefFrame[1]:
        compound_search_stack(ctx, mvRow, mvCol, weight)


def search_stack(ctx, mvRow, mvCol, candList, weight):
    c = ctx.cell(mvRow, mvCol)
    candMode, candSize = c.ymode, c.mi_size
    large = min(4 * NUM_4X4_W[candSize], 4 * NUM_4X4_H[candSize]) >= 8
    if candMode in (GLOBALMV, GLOBAL_GLOBALMV) and ctx.GmTypeList[0] > TRANSLATION and large:
        candMv = list(ctx.GlobalMvs[0])
    else:
        candMv = list(c.mv[candList])
    candMv = ctx.lower(candMv)
    if has_newmv(candMode):
        ctx.NewMvCount += 1
    ctx.FoundMatch = 1
    for idx in range(ctx.NumMvFound):
        if candMv == ctx.RefStackMv[idx][0]:
            ctx.WeightStack[idx] += weight
            return
    if ctx.NumMvFound < MAX_REF_MV_STACK_SIZE:
        ctx.RefStackMv[ctx.NumMvFound][0] = candMv
        ctx.WeightStack[ctx.NumMvFound] = weight
        ctx.NumMvFound += 1


def compound_search_stack(ctx, mvRow, mvCol, weight):
    c = ctx.cell(mvRow, mvCol)
    candMvs = [list(c.mv[0]), list(c.mv[1])]
    candMode = c.ymode
    if candMode == GLOBAL_GLOBALMV:
        for refList in range(2):
            if ctx.GmTypeList[refList] > TRANSLATION:
                candMvs[refList] = list(ctx.GlobalMvs[refList])
    candMvs = [ctx.lower(candMvs[0]), ctx.lower(candMvs[1])]
    ctx.FoundMatch = 1
    hit = False
    for idx in range(ctx.NumMvFound):
        if candMvs[0] == ctx.RefStackMv[idx][0] and candMvs[1] == ctx.RefStackMv[idx][1]:
            ctx.WeightStack[idx] += weight
            hit = True
            break
    if not hit and ctx.NumMvFound < MAX_REF_MV_STACK_SIZE:
        ctx.RefStackMv[ctx.NumMvFound] = [candMvs[0], candMvs[1]]
        ctx.WeightStack[ctx.NumMvFound] = weight
        ctx.NumMvFound += 1
    if has_newmv(candMode):
        ctx.NewMvCount += 1


# ---- 7.10.2.11 / 7.10.2.12 / 7.10.2.13 / 7.10.2.14 ---------------------------------------------------------------
def sort_stack(ctx, start, end, isCompound):
    while end > start:
        newEnd = start
        for idx in range(start + 1, end):
            if ctx.WeightStack[idx - 1] < ctx.WeightStack[idx]:
                ctx.WeightStack[idx - 1], ctx.WeightStack[idx] = ctx.WeightStack[idx], ctx.WeightStack[idx - 1]
                for lst in range(1 + isCompound):
                    a, b = ctx.RefStackMv[idx - 1], ctx.RefStackMv[idx]
                    a[lst], b[lst] = b[lst], a[lst]
                newEnd = idx
        end = newEnd


def add_extra_mv_candidate(ctx, mvRow, mvCol, isCompound, ex):
    c = ctx.cell(mvRow, mvCol)
    if isCompound:
        for candList in range(2):
            candRef = c.ref[candList]
            if candRef > INTRA_FRAME:
                for lst in range(2):
                    candMv = list(c.mv[candList])
                    if candRef == ctx.RefFrame[lst] and ex['RefIdCount'][lst] < 2:
                        ex['RefIdMvs'][lst].append(candMv)
                        ex['RefIdCount'][lst] += 1
                    elif ex['RefDiffCount'][lst] < 2:
                        if ctx.signbias(candRef) != ctx.signbias(ctx.RefFrame[lst]):
                            candMv = [-candMv[0], -candMv[1]]
                        ex['RefDiffMvs'][lst].append(candMv)
                        ex['RefDiffCount'][lst] += 1
    else:
        for candList in range(2):
            candRef = c.ref[candList]
            if candRef > INTRA_FRAME:
                candMv = list(c.mv[candList])
                if ctx.signbias(candRef) != ctx.signbias(ctx.RefFrame[0]):
                    candMv = [-candMv[0], -candMv[1]]
                idx = 0
                while idx < ctx.NumMvFound:
                    if candMv == ctx.RefStackMv[idx][0]:
                        break
                    idx += 1
                if idx == ctx.NumMvFound:
                    ctx.RefStackMv[idx][0] = candMv
                    ctx.WeightStack[idx] = 2
                    ctx.NumMvFound += 1


def extra_search(ctx, isCompound):
    ex = {'RefIdCount': [0, 0], 'RefDiffCount': [0, 0], 'RefIdMvs': [[], []], 'RefDiffMvs': [[], []]}
    w4 = min(16, NUM_4X4_W[ctx.MiSize])
    h4 = min(16, NUM_4X4_H[ctx.MiSize])
    w4 = min(w4, ctx.MiCols - ctx.MiCol)
    h4 = min(h4, ctx.MiRows - ctx.MiRow)
    num4x4 = min(w4, h4)
    for pss in range(2):
        idx = 0
        while idx < num4x4 and ctx.NumMvFound < 2:
            if pss == 0:
                mvRow, mvCol = ctx.MiRow - 1, ctx.MiCol + idx
            else:
                mvRow, mvCol = ctx.MiRow + idx, ctx.MiCol - 1
            if not ctx.is_inside(mvRow, mvCol):
                break
            add_extra_mv_candidate(ctx, mvRow, mvCol, isCompound, ex)
            sz = ctx.cell(mvRow, mvCol).mi_size
            idx += NUM_4X4_W[sz] if pss == 0 else NUM_4X4_H[sz]
    if isCompound:
        combined = [[None, None], [None, None]]
        for lst in range(2):
            compCount = 0
            for idx in range(ex['RefIdCount'][lst]):
                combined[compCount][lst] = ex['RefIdMvs'][lst][idx]
                compCount += 1
            idx = 0
            while idx < ex['RefDiffCount'][lst] and compCount < 2:
                combined[compCount][lst] = ex['RefDiffMvs'][lst][idx]
                compCount += 1
                idx += 1
            while compCount < 2:
                combined[compCount][lst] = list(ctx.GlobalMvs[lst])
                compCount += 1
        if ctx.NumMvFound == 1:
            if combined[0][0] == ctx.RefStackMv[0][0] and combined[0][1] == ctx.RefStackMv[0][1]:
                ctx.RefStackMv[ctx.NumMvFound] = [combined[1][0], combined[1][1]]
            else:
                ctx.RefStackMv[ctx.NumMvFound] = [combined[0][0], combined[0][1]]
            ctx.WeightStack[ctx.NumMvFound] = 2
            ctx.NumMvFound += 1
        else:
            for idx in range(2):
                ctx.RefStackMv[ctx.NumMvFound] = [combined[idx][0], combined[idx][1]]
                ctx.WeightStack[ctx.NumMvFound] = 2
                ctx.NumMvFound += 1
    else:
        for idx in range(ctx.NumMvFound, 2):
            ctx.RefStackMv[idx][0] = list(ctx.GlobalMvs[0])


def clamp_mv_row(ctx, mvec, border):
    bh4 = NUM_4X4_H[ctx.MiSize]
    mbToTopEdge = -((ctx.MiRow * MI_SIZE) * 8)
    mbToBottomEdge = ((ctx.MiRows - bh4 - ctx.MiRow) * MI_SIZE) * 8
    return clip3(mbToTopEdge - border, mbToBottomEdge + border, mvec)


def clamp_mv_col(ctx, mvec, border):
    bw4 = NUM_4X4_W[ctx.MiSize]
    mbToLeftEdge = -((ctx.MiCol * MI_SIZE) * 8)
    mbToRightEdge = ((ctx.MiCols - bw4 - ctx.MiCol) * MI_SIZE) * 8
    return clip3(mbToLeftEdge - border, mbToRightEdge + border, mvec)


def context_and_clamping(ctx, isCompound, numNew):
    bw, bh = 4 * NUM_4X4_W[ctx.MiSize], 4 * NUM_4X4_H[ctx.MiSize]
    numLists = 2 if isCompound else 1
    for idx in range(ctx.NumMvFound):
        z = 0
        if idx + 1 < ctx.NumMvFound:
            w0, w1 = ctx.WeightStack[idx], ctx.WeightStack[idx + 1]
            if w0 >= REF_CAT_LEVEL:
                if w1 < REF_CAT_LEVEL:
                    z = 1
            else:
                z = 2
        ctx.DrlCtxStack[idx] = z
    for lst in range(numLists):
        for idx in range(ctx.NumMvFound):
            refMv = ctx.RefStackMv[idx][lst]
            ctx.RefStackMv[idx][lst] = [clamp_mv_row(ctx, refMv[0], MV_BORDER + bh * 8),
                                        clamp_mv_col(ctx, refMv[1], MV_BORDER + bw * 8)]
    if ctx.CloseMatches == 0:
        ctx.NewMvContext = min(ctx.TotalMatches, 1)
        ctx.RefMvContext = ctx.TotalMatches
    elif ctx.CloseMatches == 1:
        ctx.NewMvContext = 3 - min(numNew, 1)
        ctx.RefMvContext = 2 + ctx.TotalMatches
    else:
        ctx.NewMvContext = 5 - min(numNew, 1)
        ctx.RefMvContext = 5


# ---- 7.10.2, the find MV stack process (without the temporal scan) ---------------------------------------------
def find_mv_stack(ctx, isCompound):
    bw4, bh4 = NUM_4X4_W[ctx.MiSize], NUM_4X4_H[ctx.MiSize]
    ctx.NumMvFound = 0
    ctx.NewMvCount = 0
    ctx.FoundMatch = 0
    scan_row(ctx, -1, isCompound)
    foundAboveMatch = ctx.FoundMatch
    ctx.FoundMatch = 0
    scan_col(ctx, -1, isCompound)
    foundLeftMatch = ctx.FoundMatch
    ctx.FoundMatch = 0
    if max(bw4, bh4) <= 16:
        scan_point(ctx, -1, bw4, isCompound)
    if ctx.FoundMatch == 1:
        foundAboveMatch = 1
    ctx.CloseMatches = foundAboveMatch + foundLeftMatch
    numNearest = ctx.NumMvFound
    numNew = ctx.NewMvCount
    for idx in range(numNearest):
        ctx.WeightStack[idx] += REF_CAT_LEVEL
    ctx.ZeroMvContext = 0
    scan_point(ctx, -1, -1, isCompound)
    if ctx.FoundMatch == 1:
        foundAboveMatch = 1
    ctx.FoundMatch = 0
    scan_row(ctx, -3, isCompound)
    if ctx.FoundMatch == 1:
        foundAboveMatch = 1
    ctx.FoundMatch = 0
    scan_col(ctx, -3, isCompound)
    if ctx.FoundMatch == 1:
        foundLeftMatch = 1
    ctx.FoundMatch = 0
    if bh4 > 1:
        scan_row(ctx, -5, isCompound)
    if ctx.FoundMatch == 1:
        foundAboveMatch = 1
    ctx.FoundMatch = 0
    if bw4 > 1:
        scan_col(ctx, -5, isCompound)
    if ctx.FoundMatch == 1:
        foundLeftMatch = 1
    ctx.TotalMatches = foundAboveMatch + foundLeftMatch
    sort_stack(ctx, 0, numNearest, isCompound)
    sort_stack(ctx, numNearest, ctx.NumMvFound, isCompound)
    if ctx.NumMvFound < 2:
        extra_search(ctx, isCompound)
    context_and_clamping(ctx, isCompound, numNew)


# ---- the test's cases -------------------------------------------------------------------------------------------
def mk(mi_size, mi_row, mi_col, dim=16, cells=(), glob=None, tile=None, signbias=None):
    """mvs_ctx_dim: dim x dim grid and tile, refs (1, 2), allow_hp 1. cells: (r, c, avail, is_inter, mi_size,
    ymode, ref0, ref1, mv0r, mv0c, mv1r, mv1c), as mvs_cell takes them. glob: av1_mvctx_set_global's (g0r, g0c,
    g1r, g1c, gt0, gt1). tile: (row_start, row_end, col_start, col_end)."""
    ctx = Ctx(dim, mi_size, mi_row, mi_col)
    for (r, c, av, ii, sz, ym, r0, r1, a, b, d, e) in cells:
        ctx.set_cell(r, c, av, ii, sz, ym, r0, r1, (a, b), (d, e))
    if glob:
        ctx.GlobalMvs = [[glob[0], glob[1]], [glob[2], glob[3]]]
        ctx.GmTypeList = [glob[4], glob[5]]
    if tile:
        ctx.MiRowStart, ctx.MiRowEnd, ctx.MiColStart, ctx.MiColEnd = tile
    if signbias:
        ctx.sign_bias = dict(signbias)
    return ctx


def pair(r, c, *a):
    """the two horizontally adjacent cells the scan cases lay down"""
    return [(r, c) + a, (r, c + 1) + a]


def vpair(r, c, *a):
    return [(r, c) + a, (r + 1, c) + a]


def row_of(r, c0, c1, *a):
    return [(r, c) + a for c in range(c0, c1)]


def col_of(c, r0, r1, *a):
    return [(r, c) + a for r in range(r0, r1)]


def check(ctx, name, want):
    got = {
        'num': ctx.NumMvFound, 'nmv': ctx.NewMvCount, 'found': ctx.FoundMatch, 'close': ctx.CloseMatches,
        'total': ctx.TotalMatches, 'newctx': ctx.NewMvContext, 'refctx': ctx.RefMvContext,
        'zeroctx': ctx.ZeroMvContext,
    }
    for k, v in want.items():
        if k in got:
            assert got[k] == v, (name, k, got[k], v)
        elif k[0] == 'row':
            assert ctx.RefStackMv[k[1]][k[2]][0] == v, (name, k, ctx.RefStackMv[k[1]][k[2]], v)
        elif k[0] == 'col':
            assert ctx.RefStackMv[k[1]][k[2]][1] == v, (name, k, ctx.RefStackMv[k[1]][k[2]], v)
        elif k[0] == 'wt':
            assert ctx.WeightStack[k[1]] == v, (name, k, ctx.WeightStack[k[1]], v)
        elif k[0] == 'drl':
            assert ctx.DrlCtxStack[k[1]] == v, (name, k, ctx.DrlCtxStack[k[1]], v)
        else:
            raise KeyError(k)


def R(i, lst=0):
    return ('row', i, lst)


def C(i, lst=0):
    return ('col', i, lst)


def W(i):
    return ('wt', i)


def DRL(i):
    return ('drl', i)


NB = (1, 1, 3, 14, 1, 0)          # an avail inter 8x8 NEARESTMV neighbour on LAST_FRAME, single
NB16 = (1, 1, 6, 14, 1, 0)        # ...16x16


def scan_cases():
    """(name, ctx, [(call, args)], expectations) for S1..S16 and the is_inside basics"""
    out = []
    out.append(("S1 scan_row(-1) 8x8 nbr", mk(3, 4, 4, cells=pair(3, 4, *NB, 12, -8, 0, 0)),
                [(scan_row, (-1, 0))], {'num': 1, R(0): 12, C(0): -8, W(0): 4, 'found': 1}))
    out.append(("S2 different ref", mk(3, 4, 4, cells=pair(3, 4, 1, 1, 3, 14, 5, 0, 1, 2, 0, 0)),
                [(scan_row, (-1, 0))], {'num': 0, 'found': 0}))
    out.append(("S3 len-step", mk(9, 4, 4, cells=row_of(3, 4, 12, *NB16, 4, 4, 0, 0)),
                [(scan_row, (-1, 0))], {'num': 1, W(0): 16}))
    out.append(("S4 col outside tile", mk(3, 4, 4, cells=[(4, 3) + NB + (9, 9, 0, 0)], tile=(0, 16, 4, 16)),
                [(scan_col, (-1, 0))], {'num': 0}))
    out.append(("S5a avail=0", mk(3, 4, 4, cells=[(3, 6, 0, 1, 3, 14, 1, 0, 7, 7, 0, 0)]),
                [(scan_point, (-1, 2, 0))], {'num': 0}))
    out.append(("S5b avail=1", mk(3, 4, 4, cells=[(3, 6, 1, 1, 3, 14, 1, 0, 7, 7, 0, 0)]),
                [(scan_point, (-1, 2, 0))], {'num': 1, W(0): 4, R(0): 7}))
    out.append(("S6 GLOBALMV substitution", mk(3, 4, 4, cells=pair(3, 4, 1, 1, 3, GLOBALMV, 1, 0, 1, 1, 0, 0),
                                                glob=(100, -50, 0, 0, 2, 0)),
                [(scan_row, (-1, 0))], {'num': 1, R(0): 100, C(0): -50}))
    out.append(("S7 NEWMV count", mk(3, 4, 4, cells=pair(3, 4, 1, 1, 3, NEWMV, 1, 0, 2, 3, 0, 0)),
                [(scan_row, (-1, 0))], {'num': 1, 'nmv': 1}))
    out.append(("S8 compound", mk(3, 4, 4, cells=pair(3, 4, 1, 1, 3, NEW_NEWMV, 1, 2, 5, 6, 7, 8)),
                [(scan_row, (-1, 1))], {'num': 1, R(0): 5, C(0): 6, R(0, 1): 7, C(0, 1): 8, 'nmv': 1}))
    out.append(("S9 both lists match", mk(3, 4, 4, cells=pair(3, 4, 1, 1, 3, 14, 1, 1, 3, 3, 9, 9)),
                [(scan_row, (-1, 0))], {'num': 2, R(0): 3, R(1): 9}))
    out.append(("S10 deltaRow -3 parity", mk(3, 4, 4, cells=pair(1, 5, *NB, 21, -13, 0, 0)),
                [(scan_row, (-3, 0))], {'num': 1, R(0): 21, C(0): -13, W(0): 4}))
    out.append(("S11 scan_col len-step", mk(9, 4, 4, cells=col_of(3, 4, 12, *NB16, 4, 4, 0, 0)),
                [(scan_col, (-1, 0))], {'num': 1, W(0): 16}))
    out.append(("S12 top-left point", mk(3, 4, 4, cells=[(3, 3) + NB + (15, 25, 0, 0)]),
                [(scan_point, (-1, -1, 0))], {'num': 1, R(0): 15, C(0): 25}))
    out.append(("S13 useStep16", mk(12, 4, 0, dim=32, cells=[(3, cc) + NB + (cc, cc, 0, 0) for cc in range(16)]),
                [(scan_row, (-1, 0))], {'num': 4, R(0): 0, R(1): 4, R(2): 8, R(3): 12, W(0): 8}))
    # S14 / S15 / S17 carry DECOYS (0.8.5): a cell where a probe that dropped a parity term would land, with an MV
    # unlike the target's (see main)
    out.append(("S14 odd parity row", mk(3, 5, 5, cells=[(3, 5, 1, 1, 0, 14, 1, 0, 31, -17, 0, 0),
                                                         (3, 6, 1, 1, 0, 14, 1, 0, 99, 99, 0, 0),
                                                         (2, 5, 1, 1, 0, 14, 1, 0, 77, 77, 0, 0)]),
                [(scan_row, (-3, 0))], {'num': 1, R(0): 31, C(0): -17}))
    out.append(("S15 odd parity col", mk(9, 5, 8, cells=[(5, 5) + NB16 + (40, -20, 0, 0),
                                                         (6, 5) + NB16 + (88, 88, 0, 0)]),
                [(scan_col, (-3, 0))], {'num': 1, R(0): 40, W(0): 8}))
    out.append(("S17 odd MiCol col", mk(3, 4, 5, cells=[(5, 3, 1, 1, 0, 14, 1, 0, 12, 34, 0, 0),
                                                        (5, 2, 1, 1, 0, 14, 1, 0, 56, 56, 0, 0),
                                                        (4, 3, 1, 1, 0, 14, 1, 0, 78, 78, 0, 0)]),
                [(scan_col, (-3, 0))], {'num': 1, R(0): 12, C(0): 34, W(0): 4}))
    out.append(("S16 compound GLOBAL_GLOBALMV per list",
                mk(3, 4, 4, cells=pair(3, 4, 1, 1, 3, GLOBAL_GLOBALMV, 1, 2, 1, 1, 9, 9),
                   glob=(200, 100, 111, 222, 2, 1)),
                [(scan_row, (-1, 1))], {'num': 1, R(0): 200, C(0): 100, R(0, 1): 9, C(0, 1): 9}))
    return out


def driver_cases():
    """(name, ctx, isCompound, expectations) for D1..D10"""
    out = []
    out.append(("D1 above + left NEWMV",
                mk(3, 4, 4, cells=pair(3, 4, *NB, 10, 10, 0, 0) + vpair(4, 3, 1, 1, 3, NEWMV, 1, 0, 20, -20, 0, 0)),
                0, {'num': 2, R(0): 10, W(0): 644, R(1): 20, W(1): 644, 'close': 2, 'total': 2, 'newctx': 4,
                    'refctx': 5, 'zeroctx': 0, DRL(0): 0}))
    out.append(("D2 empty -> global fill", mk(3, 4, 4, glob=(64, -32, 0, 0, 0, 0)), 0,
                {'num': 0, R(0): 64, C(0): -32, R(1): 64, 'close': 0, 'newctx': 0, 'refctx': 0}))
    out.append(("D3 one spatial + global", mk(3, 4, 4, cells=pair(3, 4, *NB, 5, 5, 0, 0), glob=(6, 8, 0, 0, 0, 0)), 0,
                {'num': 1, R(0): 5, W(0): 644, R(1): 6, C(1): 8, 'close': 1, 'newctx': 3, 'refctx': 3}))
    out.append(("D4 clamp positive", mk(3, 2, 2, cells=pair(1, 2, *NB, 100000, 100000, 0, 0)), 0,
                {'num': 1, R(0): 576, C(0): 576}))
    out.append(("D5 DrlCtxStack",
                mk(9, 4, 4, cells=row_of(3, 4, 12, *NB16, 1, 1, 0, 0) + col_of(3, 4, 12, *NB16, 2, 2, 0, 0)
                   + [(3, 3) + NB16 + (3, 3, 0, 0)]), 0,
                {'num': 3, W(0): 656, W(2): 4, DRL(0): 0, DRL(1): 1, DRL(2): 0}))
    out.append(("D6 close 1 + NEWMV", mk(3, 4, 4, cells=pair(3, 4, 1, 1, 3, NEWMV, 1, 0, 5, 5, 0, 0)), 0,
                {'close': 1, 'newctx': 2, 'refctx': 3}))
    out.append(("D7 compound extra", mk(3, 4, 4, cells=pair(3, 4, 1, 1, 3, NEW_NEWMV, 1, 2, 5, 6, 7, 8)), 1,
                {'num': 2, R(0): 5, R(0, 1): 7, W(0): 644, R(1): 7, R(1, 1): 5, W(1): 2, 'newctx': 2, DRL(0): 1}))
    out.append(("D8 two far candidates",
                mk(3, 4, 4, cells=[(3, 3) + NB + (30, 30, 0, 0), (1, 5) + NB + (40, 40, 0, 0)]), 0,
                {'num': 2, W(0): 4, 'close': 0, DRL(0): 2, DRL(1): 0}))
    out.append(("D9 sign-bias extra append",
                mk(3, 4, 4, cells=pair(3, 4, *NB, 5, 5, 0, 0) + [(4, 3, 1, 1, 3, 14, 3, 0, 10, 20, 0, 0)],
                   signbias={3: 1}), 0,
                {'num': 2, R(0): 5, R(1): -10, C(1): -20, W(1): 2}))
    out.append(("D10 clamp negative", mk(3, 2, 2, cells=pair(1, 2, *NB, -100000, -100000, 0, 0)), 0,
                {'num': 1, R(0): -256, C(0): -256}))
    # D11 / D12 (0.8.5): compound extra search with one stack entry that the combined pair does NOT repeat, and
    # with none (D7 only ever took the "repeats" branch)
    single_above = pair(3, 4, 1, 1, 3, NEARESTMV, 1, -1, 20, 21, 0, 0)
    out.append(("D11 compound extra, miss",
                mk(3, 4, 4, cells=single_above + pair(1, 5, 1, 1, 3, NEW_NEWMV, 1, 2, 5, 6, 7, 8),
                   glob=(30, 40, 50, 60, 0, 0)), 1,
                {'num': 2, R(0): 5, R(0, 1): 7, W(0): 4, R(1): 20, C(1): 21, R(1, 1): 20, C(1, 1): 21, W(1): 2,
                 'close': 0, 'total': 1, 'newctx': 1, 'refctx': 1, DRL(0): 2}))
    out.append(("D12 compound extra, empty", mk(3, 4, 4, cells=single_above, glob=(30, 40, 50, 60, 0, 0)), 1,
                {'num': 2, R(0): 20, R(0, 1): 20, R(1): 30, C(1): 40, R(1, 1): 50, C(1, 1): 60, W(0): 2,
                 'total': 0}))
    return out


def main():
    # 0. is_inside on the tile window (test_mvctx_basics): rows [2, 10), cols [3, 12)
    t = mk(3, 4, 4, tile=(2, 10, 3, 12))
    assert [t.is_inside(*p) for p in ((4, 4), (1, 4), (4, 2), (10, 4), (4, 12))] == [True, False, False, False, False]
    # 1. by hand.
    #  * S1 / D1's 644: an 8x8 block (bw4 2) under an 8x8 neighbour: end4 = min(2, 16 - 4, 16) = 2, len = min(2, 2)
    #    = 2, one add of weight len * 2 = 4, then i = 2 ends the scan; the driver adds REF_CAT_LEVEL: 4 + 640 = 644.
    #  * S3 / D5's 16 and 656: a 32x32 block (bw4 8) over 16x16 neighbours: len = min(8, 4) = 4, two adds of 8 at
    #    i = 0 and 4 dedup to 16; + 640 = 656.
    #  * S13's probes: a 64x64 block (bw4 16, useStep16) over 8x8 neighbours: len = max(4, min(16, 2)) = 4, so i =
    #    0, 4, 8, 12 and weight 8 each.
    #  * D4 / D10's clamp: an 8x8 block at MI (2, 2) in a 16 x 16 grid: mbToTopEdge = -(2 * 4 * 8) = -64,
    #    mbToBottomEdge = (16 - 2 - 2) * 4 * 8 = 384, border = MV_BORDER + 8 * 8 = 192, so rows clamp to
    #    [-256, 576]; the columns are the same by symmetry.
    assert 2 * min(2, 2) + REF_CAT_LEVEL == 644 and 2 * (2 * min(8, 4)) + REF_CAT_LEVEL == 656
    assert (-64 - 192, 384 + 192) == (-256, 576)
    #  * the parity decoys. S14, 8x8 at (5, 5), scan_row(-3): deltaRow = -3 + (5 & 1) = -2, deltaCol = 1 - (5 & 1) =
    #    0, so the probe is (3, 5); dropping either term lands on (2, 5) or (3, 6). S17, 8x8 at (4, 5),
    #    scan_col(-3): deltaRow = 1 - (4 & 1) = 1, deltaCol = -3 + (5 & 1) = -2, probe (5, 3); dropped terms land
    #    on (4, 3) or (5, 2). S15's odd MiRow (5) puts its probe at row 5, not the decoy's 6.
    #  * D11's combined pairs. The above row's LAST-only neighbour (RefFrames (1, NONE), MV (20, 21)) is visited
    #    once (an 8x8 cell, idx += 2 = num4x4): list 0 matches RefFrame[0] = 1 -> RefIdMvs[0] = (20, 21); list 1
    #    does not match RefFrame[1] = 2 -> RefDiffMvs[1] = (20, 21), unnegated (both biases 0). The left column is
    #    empty. So combined[0] = ((20, 21), (20, 21)) and combined[1] = the GlobalMvs ((30, 40), (50, 60)); the far
    #    compound candidate ((5, 6), (7, 8)) differs from combined[0], so combined[0] is appended.
    combined0 = ([20, 21], [20, 21])
    assert combined0 != ([5, 6], [7, 8])
    n = 0
    for (name, ctx, calls, want) in scan_cases():
        for (fn, args) in calls:
            fn(ctx, *args)
        check(ctx, name, want)
        n += 1
    for (name, ctx, comp, want) in driver_cases():
        find_mv_stack(ctx, comp)
        check(ctx, name, want)
        n += 1
    print('find_mv_stack_ref: all %d scan and driver cases of tests/av1_mv.tcyr (S1..S17, D1..D12) reproduced '
          'from the spec -- OK' % n)
    return 0


if __name__ == '__main__':
    sys.exit(main())
