#!/usr/bin/env python3
"""rd_ref.py — RATE and DISTORTION for the encode lane (0.8.7 bite 1): the symbol cost table, the estimator's model of
the symbol coder, libaom's key-frame RD multiplier, and RDCOST. Every known answer tests/av1_rd.tcyr asserts.

The spec defines no encoder decision, so what is defined here is drishti's choice, each part checked against what it
claims to approximate:

  1. THE COST TABLE. Cost[ p ] = round( 512 * log2( 32768 / p ) ) for p in 1..32767 — the cost in 1/512 bits
     (libaom's AV1_PROB_COST_SHIFT 9, av1/encoder/cost.h) of a symbol whose share of the coder's range is p / 2^15.
     drishti computes it in integers: log2 p = floor_log2( p ) + the fraction from 24 squarings of the Q30 mantissa,
     truncated, then rounded to Q9. ASSERTED: that integer algorithm (transcribed here, operation for operation) is the
     CORRECTLY ROUNDED value for every p, against 60-digit Decimal logarithms. (With 16 or 20 fraction bits it is not:
     272 and 15 entries round the wrong way; this script shows it.)

  2. THE SYMBOL COST av1_sym_cost( cdf, N, sym ): the share of the range the coder actually gives sym. The coder
     (8.2.6's inverse — drishti's av1_sym_encode, rav1e's WriterBase::store) codes sym in [ v, u ) of the range R:
         u = R                                                   for sym = 0
           = ( ( R >> 8 ) * ( fu >> EC_PROB_SHIFT ) >> 1 ) + EC_MIN_PROB * ( N - sym )    otherwise
         v = ( ( R >> 8 ) * ( fv >> EC_PROB_SHIFT ) >> 1 ) + EC_MIN_PROB * ( N - sym - 1 )
     with fu = 32768 - cdf[ sym - 1 ], fv = 32768 - cdf[ sym ] (EC_PROB_SHIFT 6, EC_MIN_PROB 4). As a share of R,
     u - v is about D / 512 + 4 / R for sym > 0, where D = ( fu >> 6 ) - ( fv >> 6 ), and for sym = 0 about
     ( 512 - ( fv >> 6 ) ) / 512 - 4 ( N - 1 ) / R. R is normalised to [ 2^15, 2^16 ); at its geometric midpoint 2^15.5
     the 4 / R term is 2 sqrt 2 / 2^15. So, in 1/2^15 units:
         p = 64 D + 3                                            (sym > 0; 2 sqrt 2 = 2.83 rounds to 3)
           = 64 ( 512 - ( fv >> 6 ) ) - ( ( N - 1 ) * 2896 + 512 ) >> 10      (sym = 0; 2896 / 1024 = 2 sqrt 2)
     clamped to [ 1, 32767 ], and the cost is Cost[ p ]. It reads the CDF the way the coder does (its top 9 bits) —
     libaom's av1_cost_symbol reads all 15 and ignores the minimum-probability term; on the streams below that model is
     ~2x further from the coder's real output.
     ASSERTED: on seeded streams (fixed CDFs of 2..16 symbols, symbols drawn from each CDF, the real coder ported here
     operation for operation from rav1e / drishti's encoder, flush included), the estimate is within 0.5% of the coded
     length. The exact totals are known answers for the Cyrius (both its estimator and its real encoder).

  3. THE RD MULTIPLIER, libaom's for a key frame (av1/encoder/rd.c av1_compute_rd_mult_based_on_qindex, KF_UPDATE,
     no tuning): q = dc_q( qindex ) (Dc_Qlookup, delta 0), rdmult = (int64)( (double)( q * q ) * ( 3.3 + 0.0015 * q ) ),
     then ROUND_POWER_OF_TWO( rdmult, 4 ) at 10 bits and ( , 8 ) at 12, at least 1. drishti's integer form is
     q * q * ( 33000 + 15 q ) / 10000, truncated. ASSERTED equal to libaom's double arithmetic (Python floats are IEEE
     doubles, the same two operations) at every qindex and bit depth but four: 8-bit qindex 16, 63, 165 and 190,
     where the exact product is an integer and libaom's double, 3.3 having no exact double, falls one short of it.
     drishti keeps the exact value.

  4. RDCOST (av1/encoder/rd.h): Round2( R * rdmult, 9 ) + D * 2^7, with D libaom's normalised distortion, the pixel SSE
     Round2'd by 2 ( BitDepth - 8 ) and times 16 (tx_search.c's `dist << 4`). Known answers only.

--emit prints the Cyrius known answers.
"""

import sys
from decimal import Decimal, getcontext

getcontext().prec = 60
FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
        if len(FAILS) <= 20:
            print("FAIL:", msg)


def round2(x, n):
    return x if n == 0 else (x + (1 << (n - 1))) >> n


# ---- 1. the cost table ----
def cost_exact(p):
    v = Decimal(512) * (Decimal(32768) / Decimal(p)).ln() / Decimal(2).ln()
    return int((v + Decimal("0.5")).to_integral_value(rounding="ROUND_FLOOR"))


def cost_int(p, fbits=24):
    """drishti's av1_sym_cost_table entry, operation for operation."""
    n = p.bit_length() - 1
    m = p << (30 - n)
    frac = 0
    for _ in range(fbits):
        m = (m * m) >> 30
        frac <<= 1
        if m >= (1 << 31):
            m >>= 1
            frac |= 1
    c = (15 << fbits) - ((n << fbits) | frac)
    if fbits == 24:
        return ((c * 512) + (1 << 23)) >> 24
    return ((c * 512) + (1 << (fbits - 1))) >> fbits


COST = [0] * 32768
for _p in range(1, 32768):
    COST[_p] = cost_int(_p)


def check_table():
    for fb in (16, 20):
        wrong = sum(1 for p in range(1, 32768) if cost_int(p, fb) != cost_exact(p))
        print(f"  with {fb} fraction bits: {wrong} entries round the wrong way")
    wrong = [p for p in range(1, 32768) if COST[p] != cost_exact(p)]
    check(not wrong, f"cost table: 24 fraction bits round every entry correctly ({len(wrong)} wrong: {wrong[:5]})")
    check(COST[1] == 7680 and COST[16384] == 512 and COST[32767] == 0, "cost table: the end points")


def table_digests():
    s1 = sum(COST[p] for p in range(1, 32768))
    s2 = sum(p * COST[p] for p in range(1, 32768))
    return s1, s2


# ---- 2. the symbol cost and the coder ----
def sym_cost(cdf, n, sym):
    fv = 32768 - cdf[sym]
    if sym > 0:
        fu = 32768 - cdf[sym - 1]
        p = (((fu >> 6) - (fv >> 6)) << 6) + 3
    else:
        p = ((512 - (fv >> 6)) << 6) - ((((n - 1) * 2896) + 512) >> 10)
    p = max(1, min(p, 32767))
    return COST[p]


class Coder:
    """The real symbol coder (drishti av1_sym_encode / av1_sym_enc_finish; rav1e WriterBase), no adaptation."""

    def __init__(self):
        self.low, self.rng, self.cnt, self.words = 0, 32768, -9, 0

    def encode(self, cdf, n, sym):
        r = self.rng
        fv = 32768 - cdf[sym]
        v = (((r >> 8) * (fv >> 6)) >> 1) + 4 * (n - sym - 1)
        u = r
        if sym > 0:
            fu = 32768 - cdf[sym - 1]
            u = (((r >> 8) * (fu >> 6)) >> 1) + 4 * (n - sym)
        low = self.low + (r - u)
        nr = u - v
        c = self.cnt
        d = 15 - (nr.bit_length() - 1)
        s = c + d
        if s >= 0:
            c += 16
            m = (1 << c) - 1
            if s >= 8:
                self.words += 1
                low &= m
                c -= 8
                m >>= 8
            self.words += 1
            s = c + d - 24
            low &= m
        self.cnt, self.low, self.rng = s, low << d, nr << d

    def finish(self):
        c = self.cnt
        s = 10 + c
        if s > 0:
            while True:
                self.words += 1
                s -= 8
                c -= 8
                if s <= 0:
                    break
        return self.words           # one output byte per pre-carry word


def lcg(x):
    return ((x * 1103515245) + 12345) & 2147483647


# The seeded stream (tests/av1_rd.tcyr rd_stream builds the same): K CDFs, CDF k has n = Ns[ k % 6 ] symbols with
# weights 1 + ( ( ( x >> 8 ) & 1023 ) ^ e ) >> s for the skew (e, s), cumulated as floor( 32768 cum / W ), each entry
# at least one more than the last, the last 32768. Then COUNT symbols: CDF k = ( x >> 8 ) % K, a uniform draw
# t = ( x >> 8 ) & 32767 picks the first sym with cdf[ sym ] > t.
NS = (2, 3, 4, 8, 13, 16)


def build_cdfs(seed, k, e, s):
    x = seed
    cdfs = []
    for i in range(k):
        n = NS[i % 6]
        w = []
        for _ in range(n):
            x = lcg(x)
            w.append(1 + ((((x >> 8) & 1023) ** e) >> s))
        tot = sum(w)
        cdf = []
        cum = 0
        for j in range(n):
            cum += w[j]
            c = (32768 * cum) // tot
            if j > 0 and c <= cdf[-1]:
                c = cdf[-1] + 1
            cdf.append(c)
        cdf[-1] = 32768
        cdfs.append(cdf)
    return cdfs, x


def run_stream(seed, k, e, s, count):
    cdfs, x = build_cdfs(seed, k, e, s)
    coder = Coder()
    est = 0
    for _ in range(count):
        x = lcg(x)
        cdf = cdfs[(x >> 8) % k]
        n = len(cdf)
        x = lcg(x)
        t = (x >> 8) & 32767
        sym = 0
        while cdf[sym] <= t:
            sym += 1
        coder.encode(cdf, n, sym)
        est += sym_cost(cdf, n, sym)
    return est, coder.finish()


STREAMS = [  # (seed, K, e, s, count)
    (1, 24, 1, 0, 20000),
    (2, 24, 2, 10, 20000),
    (3, 24, 3, 20, 20000),
]


def check_streams():
    out = []
    for st in STREAMS:
        est, nbytes = run_stream(*st)
        rel = (est / 512 - 8 * nbytes) / (8 * nbytes)
        print(f"  stream {st}: estimate {est / 512:.1f} bits, coded {8 * nbytes} bits ({100 * rel:+.3f}%)")
        check(abs(rel) < 0.005, f"stream {st}: the estimate is within 0.5% of the coded length")
        out.append((st, est, nbytes))
    return out


SYM_CASES = [  # (cdf, sym): every branch of the model, and both clamps
    ([16384, 32768], 0), ([16384, 32768], 1),
    ([100, 32768], 0), ([100, 32768], 1),
    ([32700, 32768], 0), ([32700, 32768], 1),
    ([0, 32768], 0),                                   # D = 0 at sym 0: the share clamps to 1
    ([0, 32768], 1),                                   # D = 512: 64 D + 3 clamps to 32767
    ([1, 2, 3, 32768], 1),                             # equal top 9 bits: p = 3
    ([4000, 9000, 20000, 30000, 32768], 0), ([4000, 9000, 20000, 30000, 32768], 2),
    ([4000, 9000, 20000, 30000, 32768], 4),
    ([2048 * (i + 1) for i in range(16)], 0), ([2048 * (i + 1) for i in range(16)], 15),
]


# ---- 3. the RD multiplier ----
def load_dc_q():
    import os
    import re
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    spec = os.path.join(root, "build", "spec-dl", "08.decoding.process.md")
    if not os.path.exists(spec):
        sys.exit("rd_ref.py needs the spec markdown in build/spec-dl/ (see docs/sources.md)")
    m = re.search(r"Dc_Qlookup\[ 3 \]\[ 256 \] = \{(.*?)\n\}", open(spec).read(), re.S)
    vals = [int(v) for v in re.findall(r"-?\d+", m.group(1))]
    check(len(vals) == 768, f"Dc_Qlookup has 3 x 256 entries ({len(vals)})")
    return [vals[i * 256:(i + 1) * 256] for i in range(3)]


DC_Q = load_dc_q()


def rdmult_libaom(bd, qindex):
    q = DC_Q[(bd - 8) >> 1][qindex]
    rdmult = q * q
    rdmult = int(float(rdmult) * (3.3 + (0.0015 * float(q))))    # (int64_t) truncates toward zero
    if bd == 10:
        rdmult = round2(rdmult, 4)
    if bd == 12:
        rdmult = round2(rdmult, 8)
    return max(rdmult, 1)


def rdmult_int(bd, qindex):
    q = DC_Q[(bd - 8) >> 1][qindex]
    r = (q * q * (33000 + 15 * q)) // 10000
    if bd == 10:
        r = round2(r, 4)
    if bd == 12:
        r = round2(r, 8)
    return max(r, 1)


def check_rdmult():
    from fractions import Fraction
    bad = [(bd, qi) for bd in (8, 10, 12) for qi in range(256) if rdmult_int(bd, qi) != rdmult_libaom(bd, qi)]
    # where they differ, the exact product is an INTEGER and libaom's double falls one short of it (3.3 has no exact
    # double): drishti keeps the exact value
    for bd, qi in bad:
        q = DC_Q[(bd - 8) >> 1][qi]
        ex = Fraction(q * q * (33000 + 15 * q), 10000)
        check(bd == 8 and ex.denominator == 1 and rdmult_libaom(bd, qi) == ex - 1 and rdmult_int(bd, qi) == ex,
              f"rdmult {bd}-bit qindex {qi}: differs from libaom other than by its double falling short of an integer")
    check(len(bad) == 4, f"rdmult: equal to libaom's double arithmetic at all but 4 of 768 (bd, qindex) ({bad})")
    print(f"  equal to libaom's double arithmetic at {768 - len(bad)} of 768; at {[b[1] for b in bad]} (8-bit) the "
          "exact product is an integer the double falls one short of")


def rd_dist(sse, bd):
    return round2(sse, 2 * (bd - 8)) << 4


def rd_cost(rdmult, rate, dist):
    return round2(rate * rdmult, 9) + (dist << 7)


RDMULT_PINS = [(8, 0), (8, 1), (8, 60), (8, 128), (8, 255), (10, 0), (10, 60), (10, 255), (12, 0), (12, 60),
               (12, 255)]
COST_PINS = [(7, 1000, 0), (100000, 3000, 12345), (52, 1, 1), (5000000, 777777, 0)]   # (rdmult, rate, dist)
DIST_PINS = [(0, 8), (12345, 8), (12345, 10), (12352, 10), (12344, 10), (1000000, 12), (128, 12), (127, 12)]


def main():
    print("1. the cost table")
    check_table()
    print("2. the symbol cost against the real coder")
    streams = check_streams()
    print("3. the RD multiplier")
    check_rdmult()
    if "--emit" in sys.argv:
        s1, s2 = table_digests()
        print("// cost table")
        for p in (1, 2, 3, 4, 3609, 3925, 6169, 16384, 16385, 24000, 32766, 32767):
            print(f"    assert_eq(rd_tbl({p}), {COST[p]}, \"Cost[ {p} ]\");")
        print(f"    // digests: sum {s1}, sum p * Cost[ p ] {s2}")
        print("// symbol costs")
        for cdf, sym in SYM_CASES:
            print(f"    // {cdf} sym {sym}: {sym_cost(cdf, len(cdf), sym)}")
        print("// streams (seed, K, e, s, count): estimate, coded bytes")
        for st, est, nb in streams:
            print(f"    // {st}: {est} {nb}")
        print("// rdmult")
        for bd, qi in RDMULT_PINS:
            print(f"    assert_eq(av1_rd_mult({bd}, {qi}), {rdmult_int(bd, qi)}, \"rdmult {bd}-bit qindex {qi}\");")
        print("// rd_dist")
        for sse, bd in DIST_PINS:
            print(f"    assert_eq(av1_rd_dist({sse}, {bd}), {rd_dist(sse, bd)}, \"dist {sse} at {bd} bits\");")
        print("// rd_cost")
        for rm, r, d in COST_PINS:
            print(f"    assert_eq(av1_rd_cost({rm}, {r}, {d}), {rd_cost(rm, r, d)}, \"rdcost\");")
    if FAILS:
        print(f"{len(FAILS)} FAILED")
        sys.exit(1)
    print("rd_ref.py: all checks hold")


if __name__ == "__main__":
    main()
