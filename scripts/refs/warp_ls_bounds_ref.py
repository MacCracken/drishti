#!/usr/bin/env python3
"""warp_ls_bounds_ref.py -- the warp-estimation accumulators are bounded by block geometry (0.8.5).

Spec 7.11.3.8 (the warp estimation process) sums A[2][2], Bx[2] and By[2] over the CandList samples. There are at
most LEAST_SQUARES_SAMPLES_MAX = 8 of them: 7.10.4.2's add sample process exits once NumSamplesScanned reaches 8. The
three sources treat the sums differently:

  * The spec states no bound and no clamp (arbitrary-precision arithmetic).
  * libaom (av1/common/warped_motion.c, find_affine_int) keeps them in int32_t and ASSERTS each within
    [LS_MAT_MIN, LS_MAT_MAX] = [-2^22, 2^22 - 1]. That is a debug assert ("Just for debugging, and can be removed
    later"), compiled out of release builds. It is NOT a clamp: nothing in libaom ever changes a sum.
  * dav1d (src/warpmv.c, dav1d_find_affine_int) keeps them in int and checks nothing.

drishti computes in 64 bits. The only way a 32-bit decoder could part from it is a sum outside int32 (C overflow,
undefined behaviour). This script proves no stream can produce one, by enumerating what the stream can choose:

  1. GEOMETRY. A sample's source offset from the block centre (sx, sy) is fixed by block geometry alone. The script
     enumerates every block size warped motion allows (Min(Block_Width, Block_Height) >= 8), every neighbour size,
     and every aligned neighbour the 7.10.4 scan visits: the above row, the left column, the top-left, and the
     top-right only when Max(w4, h4) <= 16. Every offset is a multiple of 8, with |sx|, |sy| <= 1024.
  2. TERMS. The stream chooses the motion vectors, but the estimation keeps a sample only if |sx - dx| < LS_MV_MAX
     and |sy - dy| < LS_MV_MAX. Over sx, sy in 8Z within the bound, and dx, dy within that filter, the script finds
     the extremes of each of the seven per-sample terms. Eight samples stay inside [-2^22, 2^22 - 1], so libaom's
     asserts can never fire and int32 never overflows.
  3. DETERMINANT. A sample adds 8 * odd to A[0][0] and A[1][1] and 4 * odd to A[0][1], so det is a multiple of 16
     (0 or 48 mod 64). A non-zero |det| is >= 16, so FloorLog2(|det|) >= 4 and divShift = FloorLog2 + 14 - 16 >= 2.
     The `divShift < 0` branch, where libaom's int16_t `iDet <<=` would wrap, is unreachable in every decoder.
  4. PRODUCTS. P = A * B - A * B stays under 2^44, and P * divFactor under 2^58: int64 holds the solve in libaom and
     dav1d, as it does in drishti.

Every bound is asserted. The extremes asserted in step 2 are derived by hand in the comments, not taken from the
enumeration. With --emit it prints the known answers tests/av1_mv.tcyr pins: the term extremes and the accumulators
of fixed sample sets.
"""
import random
import sys

LS_MV_MAX = 256                          # 03.symbols
LEAST_SQUARES_SAMPLES_MAX = 8            # 03.symbols
# libaom's asserted range (warped_motion.c): LS_MAT_RANGE_BITS = (MAX_SB_SIZE_LOG2 + 4) * 2 +
# LEAST_SQUARES_SAMPLES_MAX_BITS = (7 + 4) * 2 + 3 = 25; LS_MAT_BITS = 25 - LS_MAT_DOWN_BITS (2) = 23.
LS_MAT_MIN = -(1 << 22)
LS_MAT_MAX = (1 << 22) - 1
assert (LS_MAT_MIN, LS_MAT_MAX) == (-4194304, 4194303)


def ls_product(a, b):
    """7.11.3.8 ls_product: ((a * b) >> 2) + (a + b), with >> the spec's arithmetic (flooring) shift."""
    return ((a * b) >> 2) + (a + b)


# the seven per-sample terms, in the spec's order: A[0][0] A[0][1] A[1][1] Bx[0] Bx[1] By[0] By[1]
def terms(sx, sy, dx, dy):
    return (ls_product(sx, sx) + 8, ls_product(sx, sy) + 4, ls_product(sy, sy) + 8,
            ls_product(sx, dx) + 8, ls_product(sy, dx) + 4, ls_product(sx, dy) + 4, ls_product(sy, dy) + 8)


def accumulate(samples):
    """the 7.11.3.8 loop over (sx, sy, dx, dy) offsets (already relative to the block / destination centres)"""
    acc = [0] * 7
    for sx, sy, dx, dy in samples:
        if abs(sx - dx) < LS_MV_MAX and abs(sy - dy) < LS_MV_MAX:
            for i, t in enumerate(terms(sx, sy, dx, dy)):
                acc[i] += t
    return acc


def det_of(acc):
    return acc[0] * acc[2] - acc[1] * acc[1]


# ---- 1. geometry ----
# Block sizes as (w4, h4) in 4x4 units: the 22 of Num_4x4_Blocks_Wide / High.
SIZES = [(1, 1), (1, 2), (2, 1), (2, 2), (2, 4), (4, 2), (4, 4), (4, 8), (8, 4), (8, 8), (8, 16), (16, 8),
         (16, 16), (16, 32), (32, 16), (32, 32), (1, 4), (4, 1), (2, 8), (8, 2), (4, 16), (16, 4)]


def geometry_bound():
    """max |sx|, |sy| (1/8 sample) over every warp-eligible block and every aligned, non-overlapping neighbour
    the 7.10.4.1 scan can visit; also checks every offset is a multiple of 8"""
    best = 0
    for (w4, h4) in SIZES:
        if min(w4, h4) < 2:      # LOCALWARP needs Min(Block_Width, Block_Height) >= 8
            continue
        # alignment repeats every 32 MI (the largest block), so one superblock of positions covers it; offset by
        # 32 so every neighbour exists
        for r in range(32, 64, h4):
            for c in range(32, 64, w4):
                pos = [(r - 1, c + i) for i in range(w4)] + [(r + i, c - 1) for i in range(h4)]
                pos.append((r - 1, c - 1))
                if max(w4, h4) <= 16:
                    pos.append((r - 1, c + w4))
                mid_y = r * 4 + h4 * 2 - 1
                mid_x = c * 4 + w4 * 2 - 1
                for (cw4, ch4) in SIZES:
                    for (mr, mc) in pos:
                        cr = mr & ~(ch4 - 1)
                        cc = mc & ~(cw4 - 1)
                        # a real tiling: the neighbour must not overlap the current block
                        if cr < r + h4 and cr + ch4 > r and cc < c + w4 and cc + cw4 > c:
                            continue
                        sy = (cr * 4 + ch4 * 2 - 1 - mid_y) * 8
                        sx = (cc * 4 + cw4 * 2 - 1 - mid_x) * 8
                        assert sx % 8 == 0 and sy % 8 == 0
                        best = max(best, abs(sx), abs(sy))
    return best


S = geometry_bound()
# by hand: a 128x128 block's top-left neighbour can be another 128x128 block, whose centre is 128 samples left
# and 128 up: 128 * 8 = 1024. Nothing is farther: a neighbour touches the block, so each axis is at most the sum of
# the two half-sizes, 64 + 64.
assert S == 1024, S

# ---- 2. per-sample term extremes ----
SV = list(range(-S, S + 1, 8))                       # sx / sy: multiples of 8 within the bound
DV = list(range(-S - (LS_MV_MAX - 1), S + LS_MV_MAX))   # dx / dy: |sx - dx| < 256 for some sx

lo = [None] * 7
hi = [None] * 7


def note(i, v):
    if lo[i] is None or v < lo[i]:
        lo[i] = v
    if hi[i] is None or v > hi[i]:
        hi[i] = v


for sx in SV:
    note(0, ls_product(sx, sx) + 8)                  # A[0][0] (A[1][1] is the same function of sy)
    note(2, ls_product(sx, sx) + 8)
    for sy in SV:
        note(1, ls_product(sx, sy) + 4)              # A[0][1]
    for dx in range(sx - (LS_MV_MAX - 1), sx + LS_MV_MAX):
        note(3, ls_product(sx, dx) + 8)              # Bx[0]: dx tied to sx by the filter
        note(6, ls_product(sx, dx) + 8)              # By[1]: the same function of (sy, dy)
for sy in SV:                                        # Bx[1] / By[0]: the OTHER axis's offset is free of the filter
    for dx in DV:
        note(4, ls_product(sy, dx) + 4)
        note(5, ls_product(sy, dx) + 4)

# by hand (S = 1024, dx up to 1024 + 255 = 1279):
#   A[0][0] max = (1024*1024 >> 2) + 2048 + 8 = 262144 + 2056 = 264200 (at sx = 1024); min at sx = -8 or 0:
#     ls(0, 0) + 8 = 8 and ls(-8, -8) + 8 = 16 - 16 + 8 = 8 -> 8
#   A[0][1] max = (1024*1024 >> 2) + 2048 + 4 = 264196; min at sx = 1024, sy = -1024: -262144 + 0 + 4 = -262140
#   Bx[0] max = (1024*1279 >> 2) + 1024 + 1279 + 8 = 327424 + 2311 = 329735 (sx = 1024, dx = 1279)
#   Bx[1] max = (1024*1279 >> 2) + 1024 + 1279 + 4 = 329731; min = (-1309696 >> 2) + 1024 - 1279 + 4
#     = -327424 - 251 = -327675 (sy = 1024, dx = -1279)
assert (lo[0], hi[0]) == (8, 264200), (lo[0], hi[0])
assert (lo[1], hi[1]) == (-262140, 264196), (lo[1], hi[1])
assert hi[3] == 329735, hi[3]
assert (lo[4], hi[4]) == (-327675, 329731), (lo[4], hi[4])

# a sum of up to eight terms lies in [min(0, 8 * lo), max(0, 8 * hi)]: zero samples may pass the filter
SUM_LO = [min(0, LEAST_SQUARES_SAMPLES_MAX * x) for x in lo]
SUM_HI = [max(0, LEAST_SQUARES_SAMPLES_MAX * x) for x in hi]
for i in range(7):
    assert LS_MAT_MIN <= SUM_LO[i] and SUM_HI[i] <= LS_MAT_MAX, (i, SUM_LO[i], SUM_HI[i])
# the largest magnitude, 8 * 329735 = 2637880, is 63% of libaom's asserted 2^22 - 1: the assert can never fire
assert max(max(abs(a), abs(b)) for a, b in zip(SUM_LO, SUM_HI)) == 2637880

# ---- 3. the determinant is a multiple of 16 ----
# per sample: A[0][0] = ls(8a, 8a) + 8 = 16a^2 + 16a + 8 = 8 * (2a^2 + 2a + 1), 8 times an ODD number; likewise
# A[1][1]; A[0][1] = 16ab + 8a + 8b + 4 = 4 * (4ab + 2a + 2b + 1), 4 times an odd number. Over k samples:
# A[0][0] = 8X, A[1][1] = 8Y, A[0][1] = 4T, with X, Y, T all = k mod 2. det = 64XY - 16T^2: k even -> T even ->
# det = 0 mod 64; k odd -> det = 64 * odd - 16 * odd^2 = -16 mod 128 -> 48 mod 64. Either way 16 | det.
for sx in SV:
    a00 = ls_product(sx, sx) + 8
    assert a00 % 8 == 0 and (a00 // 8) % 2 == 1
    for sy in SV:
        a01 = ls_product(sx, sy) + 4
        assert a01 % 4 == 0 and (a01 // 4) % 2 == 1
rng = random.Random(805)
mind = None
for _ in range(20000):
    k = rng.randint(1, LEAST_SQUARES_SAMPLES_MAX)
    smp = []
    for _ in range(k):
        sx = rng.choice(SV)
        sy = rng.choice(SV)
        smp.append((sx, sy, sx + rng.randint(-(LS_MV_MAX - 1), LS_MV_MAX - 1),
                    sy + rng.randint(-(LS_MV_MAX - 1), LS_MV_MAX - 1)))
    d = det_of(accumulate(smp))
    assert d % 16 == 0 and d % 64 in (0, 48), d
    if d != 0:
        mind = abs(d) if mind is None else min(mind, abs(d))
        assert abs(d).bit_length() - 1 >= 4          # FloorLog2 >= 4 -> divShift >= 2
# the smallest |det| is a single sample at the centre: A = [[8, 4], [4, 8]] -> 64 - 16 = 48
assert det_of(accumulate([(0, 0, 0, 0)])) == 48

# ---- 4. the solve's products ----
A_MAX = max(abs(SUM_LO[0]), SUM_HI[0], abs(SUM_LO[1]), SUM_HI[1], abs(SUM_LO[2]), SUM_HI[2])
B_MAX = max(max(abs(SUM_LO[i]), SUM_HI[i]) for i in range(3, 7))
P_MAX = 2 * A_MAX * B_MAX
assert P_MAX < (1 << 44), P_MAX
DIV_FACTOR_MAX = 1 << 14                             # Div_Lut[0] = 16384 is the table's largest entry
assert P_MAX * DIV_FACTOR_MAX < (1 << 58)            # no left shift of divFactor (divShift >= 2): int64 holds it

# ---- known answers for tests/av1_mv.tcyr ----
# the extreme sample (sx = sy = 1024, dx = dy = 1279) eight times, the most negative Bx[1] sample eight times, and
# three seeded mixed sets of samples
EXTREME = [(1024, 1024, 1279, 1279)] * 8
NEG = [(-1024, 1024, -1279, 1024)] * 8
SETS = [EXTREME, NEG]
rng = random.Random(8058)
for _ in range(3):
    k = rng.randint(3, 8)
    smp = []
    for _ in range(k):
        sx = rng.choice(SV)
        sy = rng.choice(SV)
        smp.append((sx, sy, sx + rng.randint(-300, 300), sy + rng.randint(-300, 300)))   # some fail the filter
    SETS.append(smp)

if '--emit' in sys.argv:
    print('# per-term extremes (lo, hi): A00 A01 A11 Bx0 Bx1 By0 By1')
    print(list(zip(lo, hi)))
    print('# sum bounds (8 samples): ', list(zip(SUM_LO, SUM_HI)))
    for n, smp in enumerate(SETS):
        acc = accumulate(smp)
        print('set %d: samples %s' % (n, smp))
        print('set %d: acc %s det %d' % (n, acc, det_of(acc)))
print('warp_ls_bounds_ref: |sx|,|sy| <= %d; sums within [%d, %d] (libaom asserts [%d, %d]); 16 | det; '
      'P < 2^44 -- OK' % (S, min(SUM_LO), max(SUM_HI), LS_MAT_MIN, LS_MAT_MAX))
