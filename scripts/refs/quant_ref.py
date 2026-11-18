#!/usr/bin/env python3
"""quant_ref.py — the AV1 QUANTIZER (the encode lane's inverse of 7.12.3's dequantization), and its checks.

The spec defines only dequantization (7.12.3 step 1): Dequant = Clip3( -2^(7+BitDepth), 2^(7+BitDepth) - 1,
sign * ( |Quant * q2| & 0xFFFFFF ) / dqDenom ), with q2 = get_dc_quant( plane ) at (0, 0) and get_ac_quant( plane )
elsewhere (7.12.2: Dc_Qlookup / Ac_Qlookup at qindex + delta), Round2( q * Quantizer_Matrix[ .. ], 5 ) when a matrix
applies, and dqDenom 1 / 2 / 4 by transform size. The quantizer is the encoder's choice. drishti's is libaom's
dead-zone "B" quantizer RULE SET (av1/encoder/av1_quantize.c av1_build_quantizer + aom_dsp/quantize.c), computed in
exact integer arithmetic. For a coefficient c, the step S = q2 the decoder will use at that position, D = dqDenom:

    zbin  = Round2( Round2( fz * S, 7 ), log2 D )      fz = 64 at qindex 0, else 84 (dc_q( qindex ) < 148 / 592 / 2368
                                                        at 8 / 10 / 12 bits) or 80
    round = Round2( ( fr * S ) >> 7, log2 D )           fr = 64 at qindex 0, else 48
    |level| = 0                                  if |c| < zbin
            = floor( ( |c| + round ) * D / S )   otherwise, at most Lmax = floor( ( 2^(7+BitDepth) * D - 1 ) / S )
    level has the sign of c.

Lmax is the largest level whose dequantization the decoder does not clamp, and it keeps |level * S| < 2^24 so the
0xFFFFFF mask never wraps; the cap is symmetric, so quantize( -c ) = -quantize( c ) (the clamp's one extra negative
value, -2^(7+BitDepth), is forgone). libaom divides through a 16-bit reciprocal (invert_quant), exact only up to about 2^16 *
S / D; drishti's i64 divides exactly. At qindex 0 (S = 4, D = 1, both factors 64) a coefficient 4y quantizes to y
exactly, so a lossless block (the forward WHT's output is 4x its lifting) passes through unchanged.

Checks (asserted; exit 1 on any failure), over every qindex 0..255, every bit depth, D 1 / 2 / 4, DC and AC steps:
  1. the tables: Dc_Qlookup / Ac_Qlookup read from the spec markdown (build/spec-dl/);
  2. the properties: zero inside the dead zone, symmetric, non-decreasing, |Dequant(quantize(c)) - c| within the
     bound the definition implies, the cap (never above Lmax, never a clamped or wrapped dequantization), and lossless
     exactness at qindex 0;
  3. --libaom: libaom's own quantizer, compiled from ref/ (scripts/refs/quant_libaom.c, av1_build_quantizer +
     aom_highbd_quantize_b_helper_c), equals a Python emulation of its reciprocal arithmetic on every value sampled,
     and equals drishti's exact quantizer wherever that reciprocal divides exactly; the rest (|c| past ~2^16 S / D) is
     counted. Both reconstructions agree with the spec's dequantization of the level.
--emit prints the Cyrius known answers tests/av1_fquant.tcyr asserts.
"""

import os
import random
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SPEC = os.path.join(ROOT, "build", "spec-dl", "08.decoding.process.md")
FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
        if len(FAILS) <= 20:
            print("FAIL:", msg)


def round2(x, n):
    return x if n == 0 else (x + (1 << (n - 1))) >> n


def load_tables():
    if not os.path.exists(SPEC):
        sys.exit("quant_ref.py needs the spec markdown in build/spec-dl/ (see docs/sources.md)")
    txt = open(SPEC).read()
    out = []
    for name in ("Dc_Qlookup", "Ac_Qlookup"):
        m = re.search(name + r"\[ 3 \]\[ 256 \] = \{(.*?)\n\}", txt, re.S)
        check(m is not None, f"{name} found in the spec markdown")
        vals = [int(v) for v in re.findall(r"-?\d+", m.group(1)) if True]
        vals = [v for v in vals if v not in (3, 256)] if len(vals) != 768 else vals
        check(len(vals) == 768, f"{name} has 3 x 256 entries ({len(vals)})")
        out.append([vals[k * 256:(k + 1) * 256] for k in range(3)])
    return out


DC_Q, AC_Q = load_tables()


def dc_q(bd, b):
    return DC_Q[(bd - 8) >> 1][min(max(b, 0), 255)]


def ac_q(bd, b):
    return AC_Q[(bd - 8) >> 1][min(max(b, 0), 255)]


# --- 7.12.3 step 1, transcribed ----------------------------------------------------------------------------------
def dequant(level, q2, dq_denom, bd):
    dq = level * q2
    sign = -1 if dq < 0 else 1
    dq2 = sign * ((abs(dq) & 0xFFFFFF) // dq_denom)        # / truncates toward zero: on the magnitude, then the sign
    lo, hi = -(1 << (7 + bd)), (1 << (7 + bd)) - 1
    return min(max(dq2, lo), hi)


# --- the quantizer --------------------------------------------------------------------------------------------------
ZBIN_THRESH = {8: 148, 10: 592, 12: 2368}


def factors(qindex, bd):
    """libaom av1_build_quantizer / get_qzbin_factor: (zbin factor, rounding factor), in 1/128 of a step."""
    if qindex == 0:
        return 64, 64
    return (84 if dc_q(bd, qindex) < ZBIN_THRESH[bd] else 80), 48


def log2d(d):
    return {1: 0, 2: 1, 4: 2}[d]


def zbin_round(s, d, fz, fr):
    ls = log2d(d)
    return round2(round2(fz * s, 7), ls), round2((fr * s) >> 7, ls)


def lmax(s, d, bd):
    return ((1 << (7 + bd)) * d - 1) // s


def quantize(c, s, d, bd, fz, fr):
    zb, rd = zbin_round(s, d, fz, fr)
    a = abs(c)
    if a < zb:
        return 0
    lev = min(((a + rd) * d) // s, lmax(s, d, bd))
    return -lev if c < 0 else lev


def libaom_emulate(c, s, d, fz, fr):
    """aom_highbd_quantize_b_helper_c with av1_build_quantizer's tables, no matrix, in Python integers."""
    ls = log2d(d)
    zbin = round2(fz * s, 7)
    rnd = (fr * s) >> 7
    l = s.bit_length() - 1                                    # get_msb
    m = 1 + (1 << (16 + l)) // s
    quant = m - (1 << 16)                                      # stored as int16: in range for every table step
    shift = 1 << (16 - l)
    zb = round2(zbin, ls)
    a = abs(c)
    if not (c >= zb or c <= -zb):
        return 0, 0
    tmp1 = a + round2(rnd, ls)
    tmpw = tmp1 * 32
    tmp2 = ((tmpw * quant) >> 16) + tmpw
    lev = (tmp2 * shift) >> (16 - ls + 5)
    dqv = (lev * s) >> ls
    return (-lev if c < 0 else lev), (-dqv if c < 0 else dqv)


# ---------------------------------------------------------------------------------------------------------------
def steps():
    """every (bd, qindex, DC/AC step) with every D, the DC zbin threshold taken at the same qindex"""
    for bd in (8, 10, 12):
        for qi in range(256):
            for s, kind in ((dc_q(bd, qi), "dc"), (ac_q(bd, qi), "ac")):
                for d in (1, 2, 4):
                    yield bd, qi, s, kind, d


def check_properties():
    rng = random.Random(1118)
    n = 0
    for bd, qi, s, kind, d in steps():
        fz, fr = factors(qi, bd)
        zb, rd = zbin_round(s, d, fz, fr)
        top = lmax(s, d, bd)
        clamp = (1 << (7 + bd)) - 1
        # 5. the cap
        check(dequant(top, s, d, bd) <= clamp and top * s < (1 << 24),
              f"bd {bd} q {qi} {kind} D {d}: Lmax {top} dequantizes inside the clamp, no mask wrap")
        check(dequant(top + 1, s, d, bd) == clamp or ((top + 1) * s) // d > clamp,
              f"bd {bd} q {qi} {kind} D {d}: Lmax + 1 would be clamped")
        # the reconstruction bound the definition implies: level 0 errs by |c| < max(zb, S/D - rd + 1); a level L >= 1
        # covers c in [ ceil(L S / D) - rd, ... ), dequantized as floor( L S / D )
        bound = max(zb, -(-s // d) - rd + 1, rd + 1)
        xs = list(range(0, 3 * s // d + 3)) + [rng.randint(0, clamp) for _ in range(40)] + [clamp]
        prev = 0
        for x in sorted(xs):
            lv = quantize(x, s, d, bd, fz, fr)
            check(quantize(-x, s, d, bd, fz, fr) == -lv, f"bd {bd} q {qi} D {d}: symmetric at {x}")
            check(lv >= prev, f"bd {bd} q {qi} D {d}: non-decreasing at {x}")
            # inside the dead zone the level is 0; above it the level is floor( (x + round) D / S ), itself 0 while
            # x + round < S / D (the zbin and rounding factors leave such a sliver at a few steps)
            check(x >= zb or lv == 0, f"bd {bd} q {qi} D {d}: zero inside the dead zone at {x} (zbin {zb})")
            check(lv == 0 or x >= zb, f"bd {bd} q {qi} D {d}: nonzero only from zbin {zb}, at {x}")
            check((lv == 0) == (x < zb or (x + rd) * d < s), f"bd {bd} q {qi} D {d}: exactly the zero set at {x}")
            if lv < top:
                check(abs(dequant(lv, s, d, bd) - x) <= bound, f"bd {bd} q {qi} {kind} D {d}: |err| <= {bound} at {x}")
            prev = lv
            n += 1
    # 4. lossless: qindex 0, no delta, the 4x4 transform (D = 1): a coefficient 4y comes back as y
    for bd in (8, 10, 12):
        s = dc_q(bd, 0)
        check(s == 4 and ac_q(bd, 0) == 4, f"bd {bd}: qindex 0 steps are 4")
        fz, fr = factors(0, bd)
        # the cap is symmetric (|level| <= Lmax), so quantize( -c ) = -quantize( c ); the decoder's clamp admits one
        # more negative value, -2^(7+BitDepth), which the quantizer forgoes. A lossless block never comes near it: the
        # forward WHT's outputs are at most 4 * 4 * ( 2^BitDepth - 1 ) in magnitude
        for y in list(range(-3000, 3001)) + [-((1 << (bd + 5)) - 1), (1 << (bd + 5)) - 1]:
            lv = quantize(4 * y, 4, 1, bd, fz, fr)
            check(lv == y and dequant(lv, 4, 1, bd) == 4 * y, f"bd {bd}: lossless 4 * {y} -> {y}")
    print(f"properties: {n} values over every step, D and bit depth")


def harness():
    exe = os.path.join(ROOT, "build", "quant_libaom")
    src = os.path.join(ROOT, "scripts", "refs", "quant_libaom.c")
    lib = os.path.join(ROOT, "ref", "aom-build", "libaom.a")
    if not os.path.exists(lib):
        print("SKIP --libaom: ref/aom-build/libaom.a not built (ref/README.md)")
        return None
    if (not os.path.exists(exe)) or os.path.getmtime(exe) < os.path.getmtime(src):
        subprocess.run(["cc", "-O1", "-I", os.path.join(ROOT, "ref", "aom"), "-I", os.path.join(ROOT, "ref", "aom-build"),
                        src, lib, "-lm", "-lpthread", "-o", exe], check=True)
    return exe


def check_libaom():
    exe = harness()
    if exe is None:
        return
    rng = random.Random(42)
    reqs, meta = [], []
    for bd in (8, 10, 12):
        for qi in list(range(0, 256, 5)) + [255]:
            for plane in (0, 1):
                for ls in (0, 1, 2):
                    d = 1 << ls
                    s_dc, s_ac = dc_q(bd, qi), ac_q(bd, qi)
                    clamp = (1 << (7 + bd)) - 1
                    cs = [rng.randint(-clamp * d // 2, clamp * d // 2) for _ in range(48)]
                    cs += [rng.randint(-3 * s_ac, 3 * s_ac) for _ in range(48)]
                    cs[0] = rng.randint(-4 * s_dc, 4 * s_dc)
                    reqs.append(f"q {bd} {qi} 0 0 0 0 0 {plane} {ls} {len(cs)} " + " ".join(map(str, cs)))
                    meta.append((bd, qi, d, s_dc, s_ac, cs))
    out = subprocess.run([exe], input="\n".join(reqs) + "\n", capture_output=True, text=True, check=True).stdout
    lines = out.strip().split("\n")
    check(len(lines) == len(reqs), f"libaom answered every request ({len(lines)} of {len(reqs)})")
    agree = inexact = 0
    worst_c = 0
    least = None
    by_d = {}
    for line, (bd, qi, d, s_dc, s_ac, cs) in zip(lines, meta):
        got = [int(v) for v in line.split()]
        n = len(cs)
        fz, fr = factors(qi, bd)
        for k, c in enumerate(cs):
            s = s_dc if k == 0 else s_ac
            em_l, em_dq = libaom_emulate(c, s, d, fz, fr)
            check(got[k] == em_l and got[n + k] == em_dq, f"libaom == its emulation at bd {bd} q {qi} D {d} c {c}")
            mine = quantize(c, s, d, bd, fz, fr)
            zb, rd = zbin_round(s, d, fz, fr)
            exact = 0 if abs(c) < zb else ((abs(c) + rd) * d) // s
            exact = -exact if c < 0 else exact
            if em_l == exact:
                # wherever libaom's reciprocal divides exactly, drishti's level is libaom's (the cap aside)
                check(mine == em_l or abs(mine) == lmax(s, d, bd), f"drishti == libaom at bd {bd} q {qi} D {d} c {c}")
                agree += 1
            else:
                inexact += 1
                worst_c = max(worst_c, abs(abs(em_l) - abs(exact)))
                num = (abs(c) + rd) * d
                least = num if least is None else min(least, num)
                by_d[d] = by_d.get(d, 0) + 1
                # m = 1 + floor( 2^(16+l) / S ) overestimates 2^(16+l) / S by at most 1, so libaom's level can only
                # be ABOVE the exact one, by at most floor( t * D / 2^(16+l) ) + 1 with t = |c| + round
                l = s.bit_length() - 1
                dev = abs(em_l) - abs(exact)
                check(0 < dev <= (num >> (16 + l)) + 1, f"libaom rounds up, within its bound (bd {bd} q {qi} c {c} dev {dev})")
            # libaom's encoder reconstruction (lev * S) >> log_scale is the spec's dequantization of its level
            check(em_dq == dequant(em_l, s, d, bd) or abs(em_dq) > (1 << (7 + bd)) - 1,
                  f"libaom's dqcoeff = 7.12.3 Dequant at bd {bd} q {qi} c {c}")
    print(f"libaom: {agree} coefficients equal to drishti's exact quantizer; {inexact} where libaom's 16-bit reciprocal "
          f"rounds a level UP (by D: {dict(sorted(by_d.items()))}; the least numerator (|c| + round) * D {least}, "
          f"the largest excess {worst_c} level(s))")


def lcg_block(seed, count, maxv):
    x = seed
    out = []
    for _ in range(count):
        x = (x * 1103515245 + 12345) & 0x7fffffff
        out.append(((x >> 8) % (2 * maxv + 1)) - maxv)
    return out


def emit():
    print("# generated by scripts/refs/quant_ref.py --emit")
    print("# fq_kat(bd, qindex, D, dc_level_digest, ac_level_digest): over lcg_block(seed, 64, 2^(6+bd)),"
          " seed = 1 + qindex + 1000 * D + 7 * bd; c[0] with the DC step, the rest AC")
    for bd in (8, 10, 12):
        for qi in (0, 1, 17, 60, 100, 140, 200, 255):
            for d in (1, 2, 4):
                fz, fr = factors(qi, bd)
                cs = lcg_block(1 + qi + 1000 * d + 7 * bd, 64, 1 << (6 + bd))
                lv = [quantize(c, dc_q(bd, qi) if k == 0 else ac_q(bd, qi), d, bd, fz, fr) for k, c in enumerate(cs)]
                d1 = sum((k + 1) * v for k, v in enumerate(lv))
                d2 = sum(v * v for v in lv)
                print("    fq_kat(%d, %d, %d, %d, %d);" % (bd, qi, d, d1, d2))


def emit_blocks():
    """Block known answers: a seeded residual through the forward transform (fwd_txfm_ref.fwd_2d) and the
    quantizer, every size at DCT_DCT, Quant[] laid out tw x th (stride tw), the DC step at (0, 0)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import fwd_txfm_ref as F
    print("# fq_blk(txsz, bd, qindex, d1, d2, nz): lcg_block(3 + txsz, w * h, 2^bd - 1) -> fwd_2d DCT_DCT -> Quant[]")
    for t in range(19):
        lw, lh = F.TX_W_LOG2[t], F.TX_H_LOG2[t]
        w, h = 1 << lw, 1 << lh
        tw, th = min(32, w), min(32, h)
        d = {0: 1, 1: 2, 2: 4}[(w * h > 256) + (w * h > 1024)]          # dqDenom (7.12.3), by pixel count
        for bd, qi in ((8, 60), (10, 180), (12, 7)):
            res = lcg_block(3 + t, w * h, (1 << bd) - 1)
            coef = F.fwd_2d(res, t, 0)
            fz, fr = factors(qi, bd)
            lv = []
            for i in range(th):
                for j in range(tw):
                    st = dc_q(bd, qi) if (i == 0 and j == 0) else ac_q(bd, qi)
                    lv.append(quantize(coef[i * w + j], st, d, bd, fz, fr))
            d1 = sum((k + 1) * v for k, v in enumerate(lv))
            d2 = sum(v * v for v in lv)
            print("    fq_blk(%d, %d, %d, %d, %d, %d);" % (t, bd, qi, d1, d2, sum(1 for v in lv if v)))


def main():
    check_properties()
    if "--libaom" in sys.argv:
        check_libaom()
    if "--emit" in sys.argv:
        emit()
        emit_blocks()
    if FAILS:
        print(f"{len(FAILS)} FAILED")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
