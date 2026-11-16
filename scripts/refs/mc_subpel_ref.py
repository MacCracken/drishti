#!/usr/bin/env python3
"""mc_subpel_ref.py -- drishti's sub-pel filter table, derived from the SPEC (7.11.3.4), and its 90 checksums.

drishti carries dav1d's form of Subpel_Filters: 6 sets of 15 phases (phase 0, the identity, is dropped and handled
inline), taps halved to rows summing to 64, sets permuted (spec 3 BILINEAR -> 5, spec 4 REGULAR/4 -> 3, spec 5
SMOOTH/4 -> 4). tests/av1_mc.tcyr pins it with 90 position-weighted checksums, sum_k F[s][p][k] * (k + 1)^3 (the
cubic weights pin tap ORDER), whose generator, a scratchpad transcription of dav1d (mc_subpel.py), was lost.

This port re-derives them from the SPEC instead: it takes the spec table bilinear_mc_ref.py machine-generates from
the spec markdown (6 x 16 x 8, rows summing to 128), checks every tap is even (so halving is exact), halves it,
drops phase 0, applies the set permutation, and ASSERTS the 90 checksums equal the goldens in the test. With
--dav1d PATH it also checks the derived table against dav1d's own dav1d_mc_subpel_filters (src/tables.c) entry for
entry, a third source. So the test's table is anchored to the spec and to dav1d, not to one transcription.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bilinear_mc_ref import SPEC_SUBPEL_FILTERS, PERM   # noqa: E402  (spec table: 6 sets x 16 phases x 8 taps)

INV = {d: s for s, d in PERM.items()}                   # drishti / dav1d set -> spec set


def derived_table():
    """drishti / dav1d table [6][15][8]: the spec's, halved, phase 0 dropped, sets permuted"""
    out = []
    for d in range(6):
        rows = []
        for p in range(1, 16):
            spec_row = SPEC_SUBPEL_FILTERS[INV[d]][p]
            assert sum(spec_row) == 128, (d, p, spec_row)
            assert all(v % 2 == 0 for v in spec_row), (d, p, spec_row)   # halving is exact
            # exact: every tap is even, so a canary that rounds the halving instead ((v + 1) // 2) is an
            # EQUIVALENT mutation and stays green; the permutation, the dropped phase and the dav1d designators
            # are the canaries with teeth (each goes red)
            rows.append([v // 2 for v in spec_row])
        out.append(rows)
    return out


def checksum(row):
    return sum(row[k] * (k + 1) ** 3 for k in range(8))


# the 90 goldens of tests/av1_mc.tcyr test_subpel_checksum, by drishti set
GOLDEN = [
    [4243, 4470, 4787, 4977, 5130, 5472, 5679, 5832, 6039, 6192, 6588, 6795, 7093, 7410, 7799],
    [4711, 5017, 5213, 5463, 5713, 5963, 6232, 6264, 6458, 6835, 7085, 7335, 7585, 7889, 8357],
    [4585, 4355, 4690, 4833, 5113, 5364, 5796, 5724, 5706, 6030, 6389, 6615, 7136, 7417, 7295],
    [4262, 4489, 4679, 4869, 5022, 5364, 5571, 5724, 5931, 6084, 6480, 6687, 6985, 7283, 7672],
    [4730, 5017, 5213, 5463, 5713, 5963, 6213, 6372, 6585, 6835, 7085, 7335, 7585, 7889, 8230],
    [4340, 4584, 4828, 5072, 5316, 5560, 5804, 6048, 6292, 6536, 6780, 7024, 7268, 7512, 7756],
]


def parse_dav1d(path):
    """dav1d_mc_subpel_filters[6][15][8] from dav1d's src/tables.c. Each set is introduced by a designator —
    [DAV1D_FILTER_8TAP_REGULAR] (0), _SMOOTH (1), _SHARP (2), [3 + ..._REGULAR] (3), [3 + ..._SMOOTH] (4), [5] —
    which is evaluated to place the set, then stripped so its digits are not read as taps."""
    text = open(path).read()
    start = text.index('dav1d_mc_subpel_filters[6][15][8]')
    body = text[text.index('{', start) + 1:]
    body = re.sub(r'/\*.*?\*/', '', body, flags=re.S)
    body = re.sub(r'//[^\n]*', '', body)
    names = {'DAV1D_FILTER_8TAP_REGULAR': 0, 'DAV1D_FILTER_8TAP_SMOOTH': 1, 'DAV1D_FILTER_8TAP_SHARP': 2}
    table = [None] * 6
    pos = 0
    for _ in range(6):
        m = re.compile(r'\[([^\]]+)\]\s*=\s*\{').search(body, pos)
        expr = m.group(1).strip()
        idx = sum(names[t.strip()] if t.strip() in names else int(t) for t in expr.split('+'))
        depth = 1
        i = m.end()
        while depth:
            depth += {'{': 1, '}': -1}.get(body[i], 0)
            i += 1
        nums = [int(x) for x in re.findall(r'-?\d+', body[m.end():i - 1])]
        assert len(nums) == 15 * 8, (expr, len(nums))
        table[idx] = [nums[p * 8:p * 8 + 8] for p in range(15)]
        pos = i
    assert all(t is not None for t in table)
    return table


def main():
    t = derived_table()
    # by hand: drishti set 0 (REGULAR), phase 1 = the spec's [0, 2, -6, 126, 8, -2, 0, 0] halved =
    # [0, 1, -3, 63, 4, -1, 0, 0]; cs = 1*8 - 3*27 + 63*64 + 4*125 - 1*216 = 8 - 81 + 4032 + 500 - 216 = 4243
    assert t[0][0] == [0, 1, -3, 63, 4, -1, 0, 0], t[0][0]
    assert checksum(t[0][0]) == 4243
    bad = 0
    for s in range(6):
        for p in range(15):
            if checksum(t[s][p]) != GOLDEN[s][p]:
                bad += 1
                print('MISMATCH set %d phase %d: %d, golden %d' % (s, p + 1, checksum(t[s][p]), GOLDEN[s][p]))
    assert bad == 0, bad
    msg = 'mc_subpel_ref: the spec table halved reproduces all 90 checksums of tests/av1_mc.tcyr'
    if '--dav1d' in sys.argv:
        path = sys.argv[sys.argv.index('--dav1d') + 1]
        d = parse_dav1d(path)
        diff = sum(1 for s in range(6) for p in range(15) for k in range(8) if d[s][p][k] != t[s][p][k])
        assert diff == 0, diff
        msg += '; and dav1d_mc_subpel_filters (%s) equals it entry for entry' % os.path.basename(path)
    print(msg + ' -- OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
