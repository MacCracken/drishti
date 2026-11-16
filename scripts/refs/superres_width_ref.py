#!/usr/bin/env python3
"""superres_width_ref.py — the superres DOWNSCALED width (FrameWidth from UpscaledWidth and SuperresDenom).

The spec's superres_params( ) (5.9.8) computes
    FrameWidth = (UpscaledWidth * SUPERRES_NUM + (SuperresDenom / 2)) / SuperresDenom
and Annex A (annex.a.levels.md) requires every conforming bitstream to have "FrameWidth is greater than or equal
to 16". The formula alone can break that (UpscaledWidth 24 at denominator 16 gives 12), and libaom's ENCODER writes
such frames: both reference decoders therefore compute the width with a floor of Min(16, UpscaledWidth),
transcribed here from their sources, independently:

  libaom av1/common/resize.c, calculate_scaled_size_helper (via av1_calculate_scaled_superres_size):
      const int min_dim = AOMMIN(16, *dim);
      *dim = (*dim * SCALE_NUMERATOR + denom / 2) / (denom);
      *dim = AOMMAX(*dim, min_dim);
  dav1d src/obu.c (both the found_ref and the explicit frame-size paths):
      hdr->width[0] = imax((hdr->width[1] * 8 + (d >> 1)) / d, imin(16, hdr->width[1]));

On every frame that meets Annex A (formula >= 16) the floor changes nothing; it only defines the frames the formula
would make non-conforming, the way both decoders and libaom's encoder agree on. Every claim below is ASSERTED.
Run: python3 scripts/refs/superres_width_ref.py
"""
import sys

SUPERRES_NUM = 8


def spec_formula(upscaled, denom):
    return (upscaled * SUPERRES_NUM + (denom // 2)) // denom            # 5.9.8 (all operands positive)


def libaom_width(upscaled, denom):
    dim = upscaled
    if denom != SUPERRES_NUM:                                           # SCALE_NUMERATOR == 8
        min_dim = min(16, dim)
        dim = (dim * SUPERRES_NUM + denom // 2) // denom
        dim = max(dim, min_dim)
    return dim


def dav1d_width(upscaled, d):
    return max((upscaled * 8 + (d >> 1)) // d, min(16, upscaled))


def main():
    n = 0

    def check(got, want, what):
        nonlocal n
        if got != want:
            print('MISMATCH %s: %r, expected %r' % (what, got, want))
            sys.exit(1)
        n += 1

    per = {}
    for d in range(9, 17):                                              # coded_denom 0..7 + SUPERRES_DENOM_MIN 9
        per[d] = 0
        for w in range(1, 65537):                                       # frame_width_bits_minus_1 <= 15
            a, b, f = libaom_width(w, d), dav1d_width(w, d), spec_formula(w, d)
            if a != b:
                check(a, b, 'libaom vs dav1d at W %d d %d' % (w, d))
            if f >= 16 and a != f:
                check(a, f, 'a conforming width changed at W %d d %d' % (w, d))
            per[d] += (a != f)
    n += 2
    # Where the floor bites: the (W, d) whose formula drops below Min(16, W). Derived by hand for two denominators:
    #   d = 16: formula = floor((W + 1) / 2) < W for W = 2..16 (15), and < 16 for W = 17..30 (14): 29
    #   d = 9:  formula = floor((8W + 4) / 9) < W  <=>  8W + 4 < 9W  <=>  W > 4: W = 5..16 (12); < 16 only at 17: 13
    check(per[16], 29, 'denominator 16')
    check(per[9], 13, 'denominator 9')
    check([per[d] for d in range(10, 16)], [17, 20, 22, 24, 26, 28], 'denominators 10..15')
    clamped = sum(per.values())
    check(clamped, 179, 'the number of (UpscaledWidth, denominator) pairs the floor changes')
    # the unit-test table: (UpscaledWidth, SuperresDenom) -> FrameWidth, with the bare formula alongside
    table = [
        ((2, 16), 2, 1),      # invalid-oss-fuzz-10117: the formula gives 1
        ((1, 16), 1, 1),      # the floor never exceeds UpscaledWidth
        ((24, 16), 16, 12),   # libaom's 24x24 superres encode
        ((16, 16), 16, 8),    # libaom's 16x16 superres encode
        ((30, 16), 16, 15),   # libaom's 30x40 superres encode
        ((31, 16), 16, 16),   # the formula already reaches 16
        ((33, 16), 17, 17),
        ((17, 16), 16, 9),
        ((15, 16), 15, 8),    # below 16: no downscale at all
        ((8, 9), 8, 7),
        ((24, 9), 21, 21),    # a mild denominator leaves 24 conforming
        ((35, 16), 18, 18),
        ((352, 16), 176, 176),
    ]
    for (w, d), want, formula in table:
        check(libaom_width(w, d), want, 'width W %d d %d' % (w, d))
        check(spec_formula(w, d), formula, 'formula W %d d %d' % (w, d))
    print('superres_width_ref: %d checks; libaom == dav1d on all 524288 (W, d) pairs, the floor changes %d of them'
          % (n, clamped))


if __name__ == '__main__':
    main()
