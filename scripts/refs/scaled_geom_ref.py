#!/usr/bin/env python3
# scaled_geom_ref.py — spec-literal reference for the AV1 MOTION VECTOR SCALING process
# (spec 7.11.3.3) plus the two 7.11.3.4 geometry quantities that depend on it (lastX/lastY
# and intermediateHeight). The oracle for drishti's av1_mc_scale_valid / av1_scale_factor /
# av1_mc_scaled_step / av1_mc_scaled_start / av1_mc_scaled_last / av1_mc_scaled_mid_h.
# Never back-derived from the Cyrius.
#
# TRANSCRIBED VERBATIM from AOMediaCodec/av1-spec master 08.decoding.process.md,
# md5 51249ad97e9fd97dc3b0dc0e14de83b0 (fetched 2026-07-19), section 7.11.3.3:
#
#   xScale = ( ( RefUpscaledWidth[ refIdx ] << REF_SCALE_SHIFT ) + ( FrameWidth / 2 ) ) / FrameWidth
#   yScale = ( ( RefFrameHeight[ refIdx ] << REF_SCALE_SHIFT ) + ( FrameHeight / 2 ) ) / FrameHeight
#   halfSample = ( 1 << ( SUBPEL_BITS - 1 ) )
#   origX  = ( (x << SUBPEL_BITS) + ( ( 2 * mv[1] ) >> subX ) + halfSample )
#   origY  = ( (y << SUBPEL_BITS) + ( ( 2 * mv[0] ) >> subY ) + halfSample )
#   baseX  = ( origX * xScale - ( halfSample << REF_SCALE_SHIFT ) )
#   baseY  = ( origY * yScale - ( halfSample << REF_SCALE_SHIFT ) )
#   off    = ( ( 1 << (SCALE_SUBPEL_BITS - SUBPEL_BITS) ) / 2 )
#   startX = (Round2Signed( baseX, REF_SCALE_SHIFT + SUBPEL_BITS - SCALE_SUBPEL_BITS) + off)
#   startY = (Round2Signed( baseY, REF_SCALE_SHIFT + SUBPEL_BITS - SCALE_SUBPEL_BITS) + off)
#   stepX  = Round2Signed( xScale, REF_SCALE_SHIFT - SCALE_SUBPEL_BITS)
#   stepY  = Round2Signed( yScale, REF_SCALE_SHIFT - SCALE_SUBPEL_BITS)
#
# and from 7.11.3.4:
#   lastX = ( (RefUpscaledWidth[ refIdx ] + subX) >> subX) - 1
#   lastY = ( (RefFrameHeight[ refIdx ] + subY) >> subY) - 1
#   intermediateHeight = (((h - 1) * yStep + (1 << SCALE_SUBPEL_BITS) - 1) >> SCALE_SUBPEL_BITS) + 8
#
# Conformance requirement (7.11.3.3), quoted:
#   2 * FrameWidth  >= RefUpscaledWidth[ refIdx ]
#   2 * FrameHeight >= RefFrameHeight[ refIdx ]
#   FrameWidth  <= 16 * RefUpscaledWidth[ refIdx ]
#   FrameHeight <= 16 * RefFrameHeight[ refIdx ]
#
# CROSS-CHECK: check_libaom_form() re-derives startX by libaom's DIFFERENT formulation
# (av1_scaled_x / SCALE_EXTRA_OFF: the halfSample pair folded into a single additive offset
# (scale - (1 << 14)) * 8) and asserts the two agree over a sweep. Two independent algebraic
# forms agreeing is a real second source, not a restatement of the first.

SPEC_MD5 = "51249ad97e9fd97dc3b0dc0e14de83b0"

REF_SCALE_SHIFT = 14
SCALE_SUBPEL_BITS = 10
SUBPEL_BITS = 4
HALF_SAMPLE = 1 << (SUBPEL_BITS - 1)                       # 8
OFF = (1 << (SCALE_SUBPEL_BITS - SUBPEL_BITS)) // 2        # 32
START_SHIFT = REF_SCALE_SHIFT + SUBPEL_BITS - SCALE_SUBPEL_BITS   # 8
STEP_SHIFT = REF_SCALE_SHIFT - SCALE_SUBPEL_BITS                  # 4


def round2(x, n):
    if n == 0:
        return x
    return (x + (1 << (n - 1))) >> n


def round2signed(x, n):
    """Spec Round2Signed — round half AWAY FROM ZERO."""
    return round2(x, n) if x >= 0 else -round2(-x, n)


def scale_valid(ruw, rfh, fw, fht):
    if min(ruw, rfh, fw, fht) < 1:
        return 0
    if 2 * fw < ruw:
        return 0
    if 2 * fht < rfh:
        return 0
    if fw > 16 * ruw:
        return 0
    if fht > 16 * rfh:
        return 0
    return 1


def scale_factor(ref_dim, cur_dim):
    if cur_dim < 1:
        return 0
    return ((ref_dim << REF_SCALE_SHIFT) + (cur_dim // 2)) // cur_dim


def pos16(x, mv, sub):
    """(x << SUBPEL_BITS) + ((2 * mv) >> sub) — origX/origY minus halfSample."""
    return (x << SUBPEL_BITS) + ((2 * mv) >> sub)


def scaled_step(scale):
    return round2signed(scale, STEP_SHIFT)


def scaled_start(x, mv, sub, scale):
    orig = pos16(x, mv, sub) + HALF_SAMPLE
    base = orig * scale - (HALF_SAMPLE << REF_SCALE_SHIFT)
    return round2signed(base, START_SHIFT) + OFF


def scaled_last(ref_dim, sub):
    return ((ref_dim + sub) >> sub) - 1


def scaled_mid_h(h, step_y):
    return (((h - 1) * step_y + (1 << SCALE_SUBPEL_BITS) - 1) >> SCALE_SUBPEL_BITS) + 8


def check_libaom_form(trials=4000):
    """Second algebraic form of startX, from libaom's av1_scaled_x + SCALE_EXTRA_OFF.

    libaom folds the halfSample shift-in/shift-out pair into one additive offset:
        off = (scale - (1 << REF_SCALE_SHIFT)) * 8
        startX = ROUND_POWER_OF_TWO_SIGNED_64(pos16 * scale + off, 8) + 32
    Expanding the spec form gives (pos16 + 8) * scale - 8 * (1 << 14)
                                = pos16 * scale + 8 * scale - 8 * (1 << 14)
                                = pos16 * scale + (scale - (1 << 14)) * 8
    so they are algebraically identical; this asserts it numerically too, which catches a
    transcription slip in either one.
    """
    bad = []
    n = 0
    for cur in (16, 17, 24, 32, 33, 64, 128):
        for ref in (8, 16, 17, 31, 32, 33, 64, 128, 256):
            if not scale_valid(ref, ref, cur, cur):
                continue
            sc = scale_factor(ref, cur)
            for sub in (0, 1):
                for x in (0, 1, 5, 13):
                    for mv in (-64, -13, -1, 0, 1, 7, 64):
                        spec = scaled_start(x, mv, sub, sc)
                        p = pos16(x, mv, sub)
                        aom_off = (sc - (1 << REF_SCALE_SHIFT)) * HALF_SAMPLE
                        aom = round2signed(p * sc + aom_off, START_SHIFT) + OFF
                        n += 1
                        if spec != aom:
                            bad.append((cur, ref, sub, x, mv, spec, aom))
                        if len(bad) > 4:
                            return bad, n
    return bad, n


# (name, ruw, rfh, fw, fht, sub, x, y, mvr, mvc, h)
CASES = [
    # 1:1 — every scaling term must cancel exactly.
    ("g01 unscaled 1:1",        32, 32, 32, 32, 0,  4,  3,   0,   0,  8),
    ("g02 unscaled neg-mv",     32, 32, 32, 32, 0,  0,  0,  -9,  -7,  8),
    ("g03 unscaled chroma",     32, 32, 32, 32, 1,  3,  2,   7,  -5,  4),
    # 2x DOWNSCALE: the reference is half the current frame (xScale 8192, step 512).
    ("g04 2x-down",             16, 16, 32, 32, 0,  4,  3,   5,  -3,  8),
    # 2x UPSCALE at the exact conformance boundary (xScale 32768, step 2048).
    ("g05 2x-up boundary",      64, 64, 32, 32, 0,  4,  3,   5,  -3,  8),
    ("g06 2x-up h128 maxmid",   64, 64, 32, 32, 0,  0,  0,   0,   0, 128),
    # 16x smaller reference — the other conformance boundary (step 64).
    ("g07 16x-smaller",          2,  2, 32, 32, 0,  1,  1,   3,   3,  8),
    # NON-SQUARE with DIFFERENT x and y scales — an aliased square fixture would let an
    # x/y swap pass green.
    ("g08 asymmetric",          40, 24, 20, 18, 0,  3,  2,  11,  19,  8),
    ("g09 asymmetric chroma",   40, 24, 20, 18, 1,  1,  1,  -6,  10,  4),
    # NEGATIVE baseX/baseY — the ONLY place Round2Signed's away-from-zero branch fires.
    ("g10 negative base",       48, 48, 32, 32, 0,  0,  0, -40, -40,  8),
    ("g11 negative base chroma", 48, 48, 32, 32, 1, 0,  0, -40, -40,  4),
    # ODD dimensions -> a scale factor that is NOT a multiple of 16, so the step's rounding
    # bias (Round2Signed vs a bare shift) is visible.
    ("g12 odd 17->33",          17, 17, 33, 33, 0,  2,  2,   1,   1,  8),
    ("g13 odd 33->17",          33, 33, 17, 17, 0,  2,  2,   1,   1,  8),
    # ruw/rfh 23x41 against 31x25: both axes odd-ratio AND in opposite directions (the
    # reference is narrower but taller than the current frame), so an x/y swap cannot alias.
    ("g14 odd asymmetric",      23, 41, 31, 25, 0,  5,  4,  -7,  13,  8),
    # THE Round2Signed WITNESS. Round2 and Round2Signed agree everywhere EXCEPT an exact
    # tie: writing baseX = -256k - r, Round2 gives -k - [r > 128] and Round2Signed gives
    # -k - [r >= 128], so they differ only at r == 128. A merely-negative MV is NOT enough
    # (the 0.7.103 lesson) — this case is tuned so baseX == -408704 == -1597*256 + 128
    # exactly, where the two round apart: startX is -1565 signed vs -1564 unsigned.
    ("g15 Round2Signed tie",     2,  2, 17, 17, 0,  0,  0, -76, -76,  8),
]


def main():
    bad, n = check_libaom_form()
    if bad:
        print("# libaom cross-form MISMATCH (%d cases): %s" % (len(bad), bad[:3]))
        return 1
    print("# scaled_geom_ref.py — spec 7.11.3.3, spec md5 %s" % SPEC_MD5)
    print("# libaom av1_scaled_x cross-form agrees over %d combinations" % n)
    print("# constants: REF_SCALE_SHIFT=%d SCALE_SUBPEL_BITS=%d SUBPEL_BITS=%d "
          "halfSample=%d off=%d startShift=%d stepShift=%d"
          % (REF_SCALE_SHIFT, SCALE_SUBPEL_BITS, SUBPEL_BITS, HALF_SAMPLE, OFF,
             START_SHIFT, STEP_SHIFT))

    print("\n# conformance bounds (accept exactly at 2x and 16x, reject one past):")
    for (ruw, fw, label) in ((64, 32, "ref 2x current"), (65, 32, "ref 2x+1"),
                             (2, 32, "current 16x ref"), (2, 33, "current 16x+1")):
        print("#   %-18s ruw=%3d fw=%3d -> valid=%d"
              % (label, ruw, fw, scale_valid(ruw, 32, fw, 32)))

    print("\n# KATs: xScale yScale stepX stepY startX startY lastX lastY midH")
    for (name, ruw, rfh, fw, fht, sub, x, y, mvr, mvc, h) in CASES:
        assert scale_valid(ruw, rfh, fw, fht), name
        xs = scale_factor(ruw, fw)
        ys = scale_factor(rfh, fht)
        stx, sty = scaled_step(xs), scaled_step(ys)
        sx = scaled_start(x, mvc, sub, xs)
        sy = scaled_start(y, mvr, sub, ys)
        lx, ly = scaled_last(ruw, sub), scaled_last(rfh, sub)
        mh = scaled_mid_h(h, sty)
        print("#   %-24s %6d %6d %5d %5d %8d %8d %5d %5d %5d"
              % (name, xs, ys, stx, sty, sx, sy, lx, ly, mh))

    print("\n# max intermediateHeight over the whole legal space "
          "(h<=128, step<=2048): %d" % max(scaled_mid_h(h, s)
                                           for h in range(1, 129)
                                           for s in range(1, 2049)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
