#!/usr/bin/env python3
# qm_ref.py — spec-literal reference for the AV1 QUANTIZER MATRICES (spec 7.12.3 step 1b; the Quantizer_Matrix and
# Qm_Offset tables, 9.5.3; the informative derivation, 9.5.2). Shares NO code with src/av1_qm.cyr.
#
# The normative table is Quantizer_Matrix[15][2][QM_TOTAL_SIZE] (QM_TOTAL_SIZE = 3344): 100,320 entries, read here
# from the spec markdown itself (build/spec-dl/10.additional.tables.md; fetch it with curl from
# raw.githubusercontent.com/AOMediaCodec/av1-spec/master/10.additional.tables.md — the directory is gitignored).
# Too large to embed as-is in drishti, so src/av1_qm.cyr stores each (level, plane type)'s FUNDAMENTAL matrices
# and expands them by the informative 9.5.2 subsampling. This script proves, over EVERY entry, that the expansion
# reproduces the normative table, and checks two independent sources against each other:
#
#   1. the spec's Quantizer_Matrix and Qm_Offset (the normative text);
#   2. libaom's iwt_matrix_ref (ref/aom/av1/common/quant_common.c, when the checkout is present), with libaom's
#      own offset walk (av1_qm_init: a running sum over TX_SIZES_ALL that skips every size whose
#      av1_get_adjusted_tx_size differs from itself).
#
# Structure it verifies (and drishti's packing relies on): every 32x32 fundamental is SYMMETRIC, and every
# 16x32 fundamental is the TRANSPOSE of its 32x16. So each (level, plane type) is packed as
#   tri[528]   the 32x32 matrix's lower triangle, row-major: for r in 0..31, for c in 0..r: M32[r][c]
#   m3216[512] the 32x16 matrix (Tx_Width 32, Tx_Height 16), row-major: M3216[r][c] at r * 32 + c
# = 1040 bytes, 31,200 for all 30. Every value lies in 30..242, so one byte each.
#
# Usage:
#   scripts/refs/qm_ref.py           verify everything; print the known answers tests/av1_qm.tcyr asserts
#   scripts/refs/qm_ref.py --emit    print the av1_qm_hex(...) fill lines for src/av1_qm.cyr
#
# 7.12.3 step 1 (the dequantisation this script also ports, verbatim from 08.decoding.process.md):
#   a. q = (i == 0 && j == 0) ? get_dc_quant( plane ) : get_ac_quant( plane )
#   b. if using_qmatrix == 1 && PlaneTxType < IDTX && SegQMLevel[ plane ][ segment_id ] < 15:
#        q2 = Round2( q * Quantizer_Matrix[ SegQMLevel[ plane ][ segment_id ] ][ plane > 0 ][ Qm_Offset[ txSz ]
#             + i * tw + j ], 5 )
#      else q2 = q
#   c. dq = Quant[ i * tw + j ] * q2
#   d. sign = ( dq < 0 ) ? -1 : 1
#   e. dq2 = sign * ( Abs( dq ) & 0xFFFFFF ) / dqDenom
#   f. Dequant[ i ][ j ] = Clip3( - ( 1 << ( 7 + BitDepth ) ), ( 1 << ( 7 + BitDepth ) ) - 1, dq2 )
# The spec's "/" truncates toward zero (C semantics); Python's // floors, so the division goes through cdiv.

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
SPEC = os.path.join(ROOT, 'build', 'spec-dl', '10.additional.tables.md')
LIBAOM = os.path.join(ROOT, 'ref', 'aom', 'av1', 'common', 'quant_common.c')

QM_TOTAL_SIZE = 3344
LEVELS = 15
# Tx_Width / Tx_Height (spec, 3. symbols / the tx size tables), in TX_SIZES_ALL order:
# TX_4X4 8X8 16X16 32X32 64X64 4X8 8X4 8X16 16X8 16X32 32X16 32X64 64X32 4X16 16X4 8X32 32X8 16X64 64X16
TX_W = [4, 8, 16, 32, 64, 4, 8, 8, 16, 16, 32, 32, 64, 4, 16, 8, 32, 16, 64]
TX_H = [4, 8, 16, 32, 64, 8, 4, 16, 8, 32, 16, 64, 32, 16, 4, 32, 8, 64, 16]
TX_NAMES = ['4X4', '8X8', '16X16', '32X32', '64X64', '4X8', '8X4', '8X16', '16X8', '16X32', '32X16', '32X64',
            '64X32', '4X16', '16X4', '8X32', '32X8', '16X64', '64X16']
IDTX = 9


def cdiv(a, b):
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def round2(x, n):
    return (x + (1 << (n - 1))) >> n if n else x


def clip3(lo, hi, x):
    return lo if x < lo else (hi if x > hi else x)


def numbers(text):
    return [int(v) for v in re.findall(r'-?\d+', re.sub(r'/\*.*?\*/', '', text, flags=re.S))]


def parse_spec():
    if not os.path.exists(SPEC):
        sys.exit('qm_ref: %s is missing — fetch the spec markdown first (see the header)' % SPEC)
    t = open(SPEC).read()
    o = t.index('Qm_Offset[ TX_SIZES_ALL ] = {')
    qm_offset = numbers(t[o + len('Qm_Offset[ TX_SIZES_ALL ] = {'):t.index('}', o)])
    head = 'Quantizer_Matrix[ 15 ][ 2 ][ QM_TOTAL_SIZE ] = {'
    i = t.index(head)
    flat = numbers(t[i + len(head):t.index('~~~~~', i)])
    assert len(qm_offset) == 19, 'Qm_Offset: %d entries' % len(qm_offset)
    assert len(flat) == LEVELS * 2 * QM_TOTAL_SIZE, 'Quantizer_Matrix: %d entries' % len(flat)
    qm = [[flat[(lv * 2 + p) * QM_TOTAL_SIZE:(lv * 2 + p + 1) * QM_TOTAL_SIZE] for p in range(2)]
          for lv in range(LEVELS)]
    return qm_offset, qm


def libaom_adjusted(t):
    # av1_get_adjusted_tx_size: any 64 dimension maps to 32 (TX_64X64/32X64/64X32 -> TX_32X32,
    # TX_16X64 -> TX_16X32, TX_64X16 -> TX_32X16).
    w, h = min(32, TX_W[t]), min(32, TX_H[t])
    for k in range(19):
        if TX_W[k] == w and TX_H[k] == h:
            return k
    raise AssertionError('no adjusted size for %s' % TX_NAMES[t])


def check_libaom(qm_offset, qm):
    if not os.path.exists(LIBAOM):
        return 'libaom checkout absent (ref/aom); spec table used unchecked against it'
    src = open(LIBAOM).read()
    i = src.index('static const qm_val_t iwt_matrix_ref[NUM_QM_LEVELS - 1][2][QM_TOTAL_SIZE] = {')
    body = src[src.index('{', i) + 1:src.index('\n};', i)]
    flat = numbers(body)
    assert len(flat) == LEVELS * 2 * QM_TOTAL_SIZE, 'iwt_matrix_ref: %d entries' % len(flat)
    # libaom's offset walk (av1_qm_init)
    off, current = {}, 0
    for t in range(19):
        a = libaom_adjusted(t)
        if a != t:
            off[t] = off[a]
        else:
            off[t] = current
            current += TX_W[t] * TX_H[t]
    assert current == QM_TOTAL_SIZE, 'libaom walk sums to %d' % current
    assert [off[t] for t in range(19)] == qm_offset, 'libaom offsets differ from Qm_Offset'
    # libaom stores each region in ITS coefficient layout, which is the TRANSPOSE of the spec's i * tw + j
    # (libaom's scans are transposed to match): spec [i][j] is libaom's [j * th + i]. The square regions hide it
    # (every square matrix is symmetric); the rectangular ones differ at 48,538 entries read directly. So
    # copying libaom's table into the spec's indexing would mis-dequantise every rectangular transform.
    bad = direct = 0
    for lv in range(LEVELS):
        for p in range(2):
            a = flat[(lv * 2 + p) * QM_TOTAL_SIZE:(lv * 2 + p + 1) * QM_TOTAL_SIZE]
            for t in range(19):
                if libaom_adjusted(t) != t:
                    continue
                w, h = TX_W[t], TX_H[t]
                for i in range(h):
                    for j in range(w):
                        s = qm[lv][p][qm_offset[t] + i * w + j]
                        bad += a[qm_offset[t] + j * h + i] != s
                        direct += a[qm_offset[t] + i * w + j] != s
    assert bad == 0, 'iwt_matrix_ref (transposed) differs from Quantizer_Matrix at %d entries' % bad
    assert direct > 0, 'libaom layout check is vacuous: the direct read matched too'
    return ('libaom iwt_matrix_ref == spec Quantizer_Matrix at all 100,320 entries, read TRANSPOSED (j * th + i; '
            'a direct read differs at %d); its offset walk == Qm_Offset' % direct)


def fundamentals(qm_offset, m):
    f32 = m[qm_offset[3]:qm_offset[3] + 1024]        # TX_32X32
    f3216 = m[qm_offset[10]:qm_offset[10] + 512]     # TX_32X16: w 32, h 16
    f1632 = m[qm_offset[9]:qm_offset[9] + 512]       # TX_16X32: w 16, h 32
    return f32, f3216, f1632


def derive(qm_offset, m, tx):
    """9.5.2 (informative): the tw x th matrix for tx, from the fundamental of its shape class."""
    f32, f3216, f1632 = fundamentals(qm_offset, m)
    w, h = min(32, TX_W[tx]), min(32, TX_H[tx])     # the table's own index space is tw x th (7.12.3)
    if w == h:
        fm, fw, fh = f32, 32, 32
    elif w > h:
        fm, fw, fh = f3216, 32, 16
    else:
        fm, fw, fh = f1632, 16, 32
    rw, rh = fw // w, fh // h
    pw, ph = (rw + 1) // 2 - 1, (rh + 1) // 2 - 1
    return [fm[(rh * i + ph) * fw + rw * j + pw] for i in range(h) for j in range(w)]


def check_structure(qm_offset, qm):
    asym = trans = deriv = 0
    for lv in range(LEVELS):
        for p in range(2):
            m = qm[lv][p]
            f32, f3216, f1632 = fundamentals(qm_offset, m)
            asym += sum(1 for r in range(32) for c in range(32) if f32[r * 32 + c] != f32[c * 32 + r])
            trans += sum(1 for r in range(32) for c in range(16) if f1632[r * 16 + c] != f3216[c * 32 + r])
            for tx in range(19):
                d = derive(qm_offset, m, tx)
                deriv += sum(1 for k, v in enumerate(d) if m[qm_offset[tx] + k] != v)
    assert asym == 0, '%d asymmetric 32x32 entries' % asym
    assert trans == 0, '%d 16x32 entries are not the 32x16 transpose' % trans
    assert deriv == 0, '%d entries differ from the 9.5.2 derivation' % deriv
    # every entry of the normative table is covered by some tx size's tw x th region (so expanding all 19 sizes
    # fills the whole table — no byte is left unwritten)
    covered = set()
    for tx in range(19):
        covered.update(range(qm_offset[tx], qm_offset[tx] + min(32, TX_W[tx]) * min(32, TX_H[tx])))
    assert covered == set(range(QM_TOTAL_SIZE)), 'tx regions do not tile QM_TOTAL_SIZE'
    lo = min(min(qm[lv][p]) for lv in range(LEVELS) for p in range(2))
    hi = max(max(qm[lv][p]) for lv in range(LEVELS) for p in range(2))
    assert 0 < lo and hi < 256, 'values %d..%d do not fit a byte' % (lo, hi)
    return ('32x32 symmetric, 16x32 = transpose(32x16), and the 9.5.2 derivation reproduces every one of the '
            '100,320 entries; values %d..%d' % (lo, hi))


def packed(qm_offset, qm):
    out = []
    for lv in range(LEVELS):
        for p in range(2):
            f32, f3216, _ = fundamentals(qm_offset, qm[lv][p])
            out += [f32[r * 32 + c] for r in range(32) for c in range(r + 1)]
            out += f3216
    assert len(out) == LEVELS * 2 * 1040
    return out


def digest(values):
    # position-weighted polynomial hash mod the Mersenne prime 2^31 - 1 (NOT permutation-invariant; products stay
    # below 2^39, so the Cyrius side computes it exactly in i64)
    h = 0
    for v in values:
        h = (h * 131 + v) % 2147483647
    return h


def dequant(quant, tx, q_dc, q_ac, qmrow, bit_depth):
    """7.12.3 step 1, verbatim. qmrow is Quantizer_Matrix[level][ptype][Qm_Offset[tx]:], or None (q2 == q)."""
    lw, lh = TX_W[tx].bit_length() - 1, TX_H[tx].bit_length() - 1
    tw, th = min(32, TX_W[tx]), min(32, TX_H[tx])
    if (lw, lh) in ((6, 6), (5, 6), (6, 5)):
        den = 4
    elif (lw, lh) in ((5, 5), (4, 5), (5, 4), (4, 6), (6, 4)):
        den = 2
    else:
        den = 1
    out = []
    for i in range(th):
        for j in range(tw):
            q = q_dc if (i == 0 and j == 0) else q_ac
            q2 = round2(q * qmrow[i * tw + j], 5) if qmrow is not None else q
            dq = quant[i * tw + j] * q2
            sign = -1 if dq < 0 else 1
            dq2 = cdiv(sign * (abs(dq) & 0xFFFFFF), den)
            out.append(clip3(-(1 << (7 + bit_depth)), (1 << (7 + bit_depth)) - 1, dq2))
    return out


def fixture_quant(n, seed):
    # deterministic LCG coefficients: mostly small, every 7th large (drives the 0xFFFFFF mask and the clip)
    x, out = seed, []
    for k in range(n):
        x = (x * 1103515245 + 12345) % 2147483648
        v = (x >> 16) % 41 - 20
        if k % 7 == 3:
            v = v * 4099
        out.append(v)
    return out


# The dequant fixtures tests/av1_qm.tcyr asserts: (name, tx, level, ptype, q_dc, q_ac, bit_depth, seed)
FIXTURES = [
    ('8x4 luma L3 8-bit', 6, 3, 0, 52, 61, 8, 7),
    ('64x32 chroma L0 10-bit', 12, 0, 1, 1336, 1567, 10, 11),
    ('16x64 luma L14 12-bit', 17, 14, 0, 4247, 5347, 12, 13),
    ('4x4 chroma L9 8-bit', 0, 9, 1, 4, 4, 8, 17),
    # DC weight 35 (most DC weights are 32 = 1.0; 31 / 33 / 35 occur at small sizes and low levels) with a q_dc
    # large enough that Round2 does not hide it: pins that step 1b scales the DC coefficient too
    ('4x4 chroma L0 10-bit DC35', 0, 0, 1, 1000, 900, 10, 19),
]


def main():
    qm_offset, qm = parse_spec()
    if '--emit' in sys.argv:
        b = packed(qm_offset, qm)
        for g in range(LEVELS * 2):
            lv, p = g // 2, g % 2
            print('    # level %d, %s: 32x32 lower triangle (528) then 32x16 (512)' % (lv, 'chroma' if p else 'luma'))
            for k in range(0, 1040, 40):
                off = g * 1040 + k
                print('    av1_qm_hex(t, %d, "%s");' % (off, ''.join('%02x' % v for v in b[off:off + 40])))
        return
    print('Qm_Offset:', qm_offset)
    print(check_structure(qm_offset, qm))
    print(check_libaom(qm_offset, qm))
    full = [v for lv in range(LEVELS) for p in range(2) for v in qm[lv][p]]
    print('digest(Quantizer_Matrix, 100,320 entries in [level][ptype][k] order) =', digest(full))
    print('digest(packed fundamentals, 31,200 bytes) =', digest(packed(qm_offset, qm)))
    print('spot values Quantizer_Matrix[level][ptype][k]:')
    spots = [(0, 0, 0), (0, 0, 15), (0, 1, 15), (14, 1, QM_TOTAL_SIZE - 1), (7, 0, qm_offset[10] + 5 * 32 + 30),
             (7, 0, qm_offset[9] + 30 * 16 + 5), (3, 1, qm_offset[3] + 31 * 32 + 0), (3, 1, qm_offset[3] + 0 * 32 + 31),
             (5, 0, qm_offset[13] + 15 * 4 + 3), (5, 0, qm_offset[14] + 3 * 16 + 15), (11, 1, qm_offset[15] + 31 * 8 + 7),
             (11, 1, qm_offset[16] + 7 * 32 + 31), (2, 0, qm_offset[5] + 7 * 4 + 1), (2, 0, qm_offset[6] + 1 * 8 + 7)]
    for lv, p, k in spots:
        print('  [%d][%d][%d] = %d' % (lv, p, k, qm[lv][p][k]))
    # TRANSPOSE-SENSITIVE spots: in each rectangular region, the first [i][j] whose value differs from the
    # transposed read [j * th + i] — a decoder indexing a rectangular matrix the libaom way gets these wrong.
    print('transpose-sensitive spots Quantizer_Matrix[level][ptype][k] (value; transposed read):')
    for lv, p, t in [(0, 0, 5), (4, 1, 6), (6, 0, 9), (8, 1, 10), (10, 0, 13), (12, 1, 16)]:
        w, h, o = TX_W[t], TX_H[t], qm_offset[t]
        hit = next((i, j) for i in range(h) for j in range(w)
                   if qm[lv][p][o + i * w + j] != qm[lv][p][o + j * h + i])
        k = o + hit[0] * w + hit[1]
        print('  [%d][%d][%d] = %d (TX_%s i=%d j=%d; transposed read %d)' % (lv, p, k, qm[lv][p][k], TX_NAMES[t],
              hit[0], hit[1], qm[lv][p][o + hit[1] * h + hit[0]]))
    for name, tx, lv, p, qdc, qac, bd, seed in FIXTURES:
        n = min(32, TX_W[tx]) * min(32, TX_H[tx])
        quant = fixture_quant(n, seed)
        row = qm[lv][p][qm_offset[tx]:]
        dq = dequant(quant, tx, qdc, qac, row, bd)
        flat = dequant(quant, tx, qdc, qac, None, bd)
        print('fixture %s (tx %s, Qm_Offset %d): digest(Dequant) = %d, flat digest = %d, entries changed by the '
              'matrix = %d/%d, Dequant[0..5] = %s' % (name, TX_NAMES[tx], qm_offset[tx], digest([v & 0xFFFFFFFF
              for v in dq]), digest([v & 0xFFFFFFFF for v in flat]), sum(1 for a, b in zip(dq, flat) if a != b),
              n, dq[:6]))


if __name__ == '__main__':
    main()
