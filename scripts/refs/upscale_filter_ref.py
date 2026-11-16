#!/usr/bin/env python3
"""upscale_filter_ref.py -- the superres Upscale_Filter[64][8] (7.16) and its 64 position-weighted checksums.

tests/av1_superres.tcyr pins drishti's table with cs[p] = sum_k Upscale_Filter[p][k] * (k + 1)^3 (the cubic weights
pin tap ORDER, which row sums and mirror symmetry cannot). The 64 goldens came from a scratchpad transcription of
dav1d's dav1d_resize_filter (0.7.85), since lost. This port takes the SPEC's table instead — superres_ref.py embeds
it and checks it against the spec markdown when build/spec-dl/ is present — and asserts it reproduces all 64. With
--dav1d PATH it also parses dav1d_resize_filter from dav1d's src/tables.c, which dav1d stores NEGATED (centre tap
-128; resize_c negates the sum back), and checks it is exactly the spec's table negated, entry for entry.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from superres_ref import Upscale_Filter, check_table_against_spec   # noqa: E402

# the 64 goldens of tests/av1_superres.tcyr test_upscale_filter_position_checksum
GOLDEN = [
    8192, 8199, 8466, 8473, 8613, 8681, 9030, 8981,
    8753, 9039, 8990, 9058, 9278, 9564, 9515, 9546,
    9766, 10052, 10083, 10186, 10217, 10248, 10686, 10717,
    10839, 10870, 10612, 11030, 11213, 11335, 11197, 11767,
    11502, 11561, 11807, 11885, 12007, 12190, 12338, 12566,
    12651, 12773, 12858, 13188, 13273, 13358, 13353, 13438,
    13670, 13944, 14029, 13926, 14158, 14432, 14608, 14505,
    14737, 14887, 14784, 15403, 15579, 15665, 15780, 15885,
]


def checksum(row):
    return sum(row[k] * (k + 1) ** 3 for k in range(8))


def parse_dav1d(path):
    """dav1d_resize_filter[64][8] from dav1d's src/tables.c"""
    text = open(path).read()
    start = text.index('dav1d_resize_filter[64][8]')
    body = text[text.index('{', start) + 1:]
    body = body[:body.index('};')]
    body = re.sub(r'/\*.*?\*/', '', body, flags=re.S)
    body = re.sub(r'//[^\n]*', '', body)
    nums = [int(x) for x in re.findall(r'-?\d+', body)]
    assert len(nums) == 512, len(nums)
    return [nums[p * 8:p * 8 + 8] for p in range(64)]


def main():
    note = check_table_against_spec()
    # by hand: phase 0 is the identity row [0, 0, 0, 128, 0, 0, 0, 0], cs = 128 * 4^3 = 8192; phase 1 is
    # [0, 0, -1, 128, 2, -1, 0, 0]: -27 + 8192 + 250 - 216 = 8199.
    assert Upscale_Filter[0] == [0, 0, 0, 128, 0, 0, 0, 0] and checksum(Upscale_Filter[0]) == 8192
    assert checksum(Upscale_Filter[1]) == -27 + 8192 + 250 - 216 == 8199
    assert all(sum(r) == 128 for r in Upscale_Filter)
    bad = [p for p in range(64) if checksum(Upscale_Filter[p]) != GOLDEN[p]]
    assert not bad, bad
    msg = ('upscale_filter_ref: the spec Upscale_Filter reproduces all 64 checksums of tests/av1_superres.tcyr '
           '(%s)' % note)
    if '--dav1d' in sys.argv:
        path = sys.argv[sys.argv.index('--dav1d') + 1]
        d = parse_dav1d(path)
        diff = sum(1 for p in range(64) for k in range(8) if d[p][k] != -Upscale_Filter[p][k])
        assert diff == 0, diff
        msg += '; dav1d_resize_filter (%s) is it negated, entry for entry' % os.path.basename(path)
    print(msg + ' -- OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
