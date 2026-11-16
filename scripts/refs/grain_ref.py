#!/usr/bin/env python3
# grain_ref.py — spec-literal reference for the AV1 FILM GRAIN SYNTHESIS process (spec 7.18.3: 7.18.3.2 random
# number, 7.18.3.3 generate grain, 7.18.3.4 scaling lookup initialisation, 7.18.3.5 add noise synthesis; the
# Gaussian_Sequence table of the additional tables). Shares NO code with src/av1_grain.cyr.
#
# Every process below is transcribed from build/spec-dl/08.decoding.process.md (the AV1 spec master text; the
# directory is gitignored — fetch the markdown with curl from raw.githubusercontent.com/AOMediaCodec/av1-spec/
# master/), and Gaussian_Sequence is READ from build/spec-dl/10.additional.tables.md, never embedded. The spec's
# ">>" is an arithmetic shift and "/" truncates toward zero; Python's >> is arithmetic (floor) too, and the only
# divisions here have non-negative operands (deltaX > 0), so // is exact.
#
# Modes:
#   grain_ref.py                 print the known answers tests/av1_grain.tcyr asserts (fixtures below)
#   grain_ref.py --emit          print the av1_grain_hex(...) fill lines for src/av1_grain.cyr
#   grain_ref.py --crosscheck PROBE SKIP REF W H FMT BD
#                                apply this port's synthesis to every frame of SKIP (aomdec --skip-film-grain
#                                --rawvideo output) with the parameters vector-probe printed (PROBE) and compare
#                                with REF (aomdec's normal, grained output): validates the PORT against libaom
#                                independently of drishti's synthesis.

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = os.path.join(HERE, '..', '..', 'build', 'spec-dl', '10.additional.tables.md')


def gaussian_sequence():
    if not os.path.exists(TABLES):
        sys.exit('grain_ref: %s is missing — fetch the spec markdown first' % TABLES)
    t = open(TABLES).read()
    i = t.index('Gaussian_Sequence[ 2048 ] = {')
    vals = [int(v) for v in re.findall(r'-?\d+', t[i + len('Gaussian_Sequence[ 2048 ] = {'):t.index('}', i)])]
    assert len(vals) == 2048, len(vals)
    assert all(-2048 <= v <= 2047 for v in vals)
    return vals


GS = None


def round2(x, n):
    return x if n == 0 else (x + (1 << (n - 1))) >> n


def clip3(lo, hi, x):
    return lo if x < lo else (hi if x > hi else x)


class Grain:
    """The state of one invocation of 7.18.3 (RandomRegister, the grain arrays, ScalingLut)."""

    def __init__(self, p, bit_depth, mono, subx, suby, mc_identity=False):
        self.p, self.bd, self.mono, self.subx, self.suby = p, bit_depth, mono, subx, suby
        self.mc_identity = mc_identity
        self.num_planes = 1 if mono else 3

    # 7.18.3.2
    def get_random_number(self, bits):
        r = self.RandomRegister
        bit = ((r >> 0) ^ (r >> 1) ^ (r >> 3) ^ (r >> 12)) & 1
        r = (r >> 1) | (bit << 15)
        result = (r >> (16 - bits)) & ((1 << bits) - 1)
        self.RandomRegister = r
        return result

    # 7.18.3.3
    def generate_grain(self):
        p, bd = self.p, self.bd
        shift = 12 - bd + p['grain_scale_shift']
        L = [[0] * 82 for _ in range(73)]
        for y in range(73):
            for x in range(82):
                g = GS[self.get_random_number(11)] if p['num_y_points'] > 0 else 0
                L[y][x] = round2(g, shift)
        shift = p['ar_coeff_shift_minus_6'] + 6
        lag = p['ar_coeff_lag']
        for y in range(3, 73):
            for x in range(3, 82 - 3):
                s = 0
                pos = 0
                done = False
                for dr in range(-lag, 1):
                    for dc in range(-lag, lag + 1):
                        if dr == 0 and dc == 0:
                            done = True
                            break
                        c = p['ar_coeffs_y_plus_128'][pos] - 128
                        s += L[y + dr][x + dc] * c
                        pos += 1
                    if done:
                        break
                L[y][x] = clip3(self.GrainMin, self.GrainMax, L[y][x] + round2(s, shift))
        self.LumaGrain = L
        if self.mono:
            return
        cw = 44 if self.subx else 82
        ch = 38 if self.suby else 73
        shift = 12 - bd + p['grain_scale_shift']
        csfl = p['chroma_scaling_from_luma']
        Cb = [[0] * cw for _ in range(ch)]
        Cr = [[0] * cw for _ in range(ch)]
        self.RandomRegister = p['grain_seed'] ^ 0xb524
        for y in range(ch):
            for x in range(cw):
                g = GS[self.get_random_number(11)] if (p['num_cb_points'] > 0 or csfl) else 0
                Cb[y][x] = round2(g, shift)
        self.RandomRegister = p['grain_seed'] ^ 0x49d8
        for y in range(ch):
            for x in range(cw):
                g = GS[self.get_random_number(11)] if (p['num_cr_points'] > 0 or csfl) else 0
                Cr[y][x] = round2(g, shift)
        shift = p['ar_coeff_shift_minus_6'] + 6
        for y in range(3, ch):
            for x in range(3, cw - 3):
                s0 = s1 = 0
                pos = 0
                done = False
                for dr in range(-lag, 1):
                    for dc in range(-lag, lag + 1):
                        c0 = p['ar_coeffs_cb_plus_128'][pos] - 128
                        c1 = p['ar_coeffs_cr_plus_128'][pos] - 128
                        if dr == 0 and dc == 0:
                            if p['num_y_points'] > 0:
                                luma = 0
                                lx = ((x - 3) << self.subx) + 3
                                ly = ((y - 3) << self.suby) + 3
                                for i in range(self.suby + 1):
                                    for j in range(self.subx + 1):
                                        luma += L[ly + i][lx + j]
                                luma = round2(luma, self.subx + self.suby)
                                s0 += luma * c0
                                s1 += luma * c1
                            done = True
                            break
                        s0 += Cb[y + dr][x + dc] * c0
                        s1 += Cr[y + dr][x + dc] * c1
                        pos += 1
                    if done:
                        break
                Cb[y][x] = clip3(self.GrainMin, self.GrainMax, Cb[y][x] + round2(s0, shift))
                Cr[y][x] = clip3(self.GrainMin, self.GrainMax, Cr[y][x] + round2(s1, shift))
        self.CbGrain, self.CrGrain = Cb, Cr

    # 7.18.3.4
    def get_x(self, plane, i):
        p = self.p
        if plane == 0 or p['chroma_scaling_from_luma']:
            return p['point_y_value'][i]
        return p['point_cb_value'][i] if plane == 1 else p['point_cr_value'][i]

    def get_y(self, plane, i):
        p = self.p
        if plane == 0 or p['chroma_scaling_from_luma']:
            return p['point_y_scaling'][i]
        return p['point_cb_scaling'][i] if plane == 1 else p['point_cr_scaling'][i]

    def scaling_init(self):
        p = self.p
        self.ScalingLut = [[0] * 256 for _ in range(3)]
        for plane in range(self.num_planes):
            if plane == 0 or p['chroma_scaling_from_luma']:
                n = p['num_y_points']
            elif plane == 1:
                n = p['num_cb_points']
            else:
                n = p['num_cr_points']
            lut = self.ScalingLut[plane]
            if n == 0:
                continue
            for x in range(self.get_x(plane, 0)):
                lut[x] = self.get_y(plane, 0)
            for i in range(n - 1):
                dy = self.get_y(plane, i + 1) - self.get_y(plane, i)
                dx = self.get_x(plane, i + 1) - self.get_x(plane, i)
                delta = dy * ((65536 + (dx >> 1)) // dx)
                for x in range(dx):
                    lut[self.get_x(plane, i) + x] = self.get_y(plane, i) + ((x * delta + 32768) >> 16)
            for x in range(self.get_x(plane, n - 1), 256):
                lut[x] = self.get_y(plane, n - 1)

    def scale_lut(self, plane, index):
        shift = self.bd - 8
        x = index >> shift
        rem = index - (x << shift)
        if self.bd == 8 or x == 255:
            return self.ScalingLut[plane][x]
        start = self.ScalingLut[plane][x]
        end = self.ScalingLut[plane][x + 1]
        return start + round2((end - start) * rem, shift)

    # 7.18.3.5 — full noiseStripe / noiseImage arrays, exactly as the spec writes them
    def add_noise(self, OutY, OutU, OutV, w, h, subX, subY):
        p, bd = self.p, self.bd
        GMin, GMax = self.GrainMin, self.GrainMax
        overlap = p['overlap_flag']
        stripes = []
        lumaNum = 0
        y = 0
        while y < (h + 1) // 2:
            self.RandomRegister = p['grain_seed']
            self.RandomRegister ^= ((lumaNum * 37 + 178) & 255) << 8
            self.RandomRegister ^= ((lumaNum * 173 + 105) & 255)
            ns = [dict() for _ in range(self.num_planes)]
            x = 0
            while x < (w + 1) // 2:
                rand = self.get_random_number(8)
                offx = rand >> 4
                offy = rand & 15
                for plane in range(self.num_planes):
                    psx = subX if plane > 0 else 0
                    psy = subY if plane > 0 else 0
                    pox = 6 + offx if psx else 9 + offx * 2
                    poy = 6 + offy if psy else 9 + offy * 2
                    for i in range(34 >> psy):
                        for j in range(34 >> psx):
                            if plane == 0:
                                g = self.LumaGrain[poy + i][pox + j]
                            elif plane == 1:
                                g = self.CbGrain[poy + i][pox + j]
                            else:
                                g = self.CrGrain[poy + i][pox + j]
                            if psx == 0:
                                if j < 2 and overlap and x > 0:
                                    old = ns[plane][(i, x * 2 + j)]
                                    g = old * 27 + g * 17 if j == 0 else old * 17 + g * 27
                                    g = clip3(GMin, GMax, round2(g, 5))
                                ns[plane][(i, x * 2 + j)] = g
                            else:
                                if j == 0 and overlap and x > 0:
                                    old = ns[plane][(i, x + j)]
                                    g = old * 23 + g * 22
                                    g = clip3(GMin, GMax, round2(g, 5))
                                ns[plane][(i, x + j)] = g
                x += 16
            stripes.append(ns)
            lumaNum += 1
            y += 16
        noise = [None] * self.num_planes
        for plane in range(self.num_planes):
            psx = subX if plane > 0 else 0
            psy = subY if plane > 0 else 0
            ph, pw = (h + psy) >> psy, (w + psx) >> psx
            img = [[0] * pw for _ in range(ph)]
            for yy in range(ph):
                ln = yy >> (5 - psy)
                i = yy - (ln << (5 - psy))
                for xx in range(pw):
                    g = stripes[ln][plane][(i, xx)]
                    if psy == 0:
                        if i < 2 and ln > 0 and overlap:
                            old = stripes[ln - 1][plane][(i + 32, xx)]
                            g = old * 27 + g * 17 if i == 0 else old * 17 + g * 27
                            g = clip3(GMin, GMax, round2(g, 5))
                    else:
                        if i < 1 and ln > 0 and overlap:
                            old = stripes[ln - 1][plane][(i + 16, xx)]
                            g = old * 23 + g * 22
                            g = clip3(GMin, GMax, round2(g, 5))
                    img[yy][xx] = g
            noise[plane] = img
        if p['clip_to_restricted_range']:
            minV = 16 << (bd - 8)
            maxL = 235 << (bd - 8)
            maxC = maxL if self.mc_identity else 240 << (bd - 8)
        else:
            minV = 0
            maxL = (256 << (bd - 8)) - 1
            maxC = maxL
        shiftS = p['grain_scaling_minus_8'] + 8
        hi = (1 << bd) - 1
        if self.num_planes > 1:
            for yy in range((h + subY) >> subY):
                for xx in range((w + subX) >> subX):
                    lx, ly = xx << subX, yy << subY
                    lnx = min(lx + 1, w - 1)
                    avg = round2(OutY[ly][lx] + OutY[ly][lnx], 1) if subX else OutY[ly][lx]
                    for plane, Out, npts, mult, lmult, off in (
                            (1, OutU, p['num_cb_points'], p['cb_mult'], p['cb_luma_mult'], p['cb_offset']),
                            (2, OutV, p['num_cr_points'], p['cr_mult'], p['cr_luma_mult'], p['cr_offset'])):
                        if npts > 0 or p['chroma_scaling_from_luma']:
                            orig = Out[yy][xx]
                            if p['chroma_scaling_from_luma']:
                                merged = avg
                            else:
                                comb = avg * (lmult - 128) + orig * (mult - 128)
                                merged = clip3(0, hi, (comb >> 6) + ((off - 256) << (bd - 8)))
                            n = round2(self.scale_lut(plane, merged) * noise[plane][yy][xx], shiftS)
                            Out[yy][xx] = clip3(minV, maxC, orig + n)
        for yy in range(h):
            for xx in range(w):
                orig = OutY[yy][xx]
                n = round2(self.scale_lut(0, orig) * noise[0][yy][xx], shiftS)
                if p['num_y_points'] > 0:
                    OutY[yy][xx] = clip3(minV, maxL, orig + n)

    # 7.18.3.1
    def synthesize(self, OutY, OutU, OutV, w, h):
        self.RandomRegister = self.p['grain_seed']
        self.GrainCenter = 128 << (self.bd - 8)
        self.GrainMin = -self.GrainCenter
        self.GrainMax = (256 << (self.bd - 8)) - 1 - self.GrainCenter
        self.generate_grain()
        self.scaling_init()
        self.add_noise(OutY, OutU, OutV, w, h, self.subx, self.suby)


def blank_params():
    return dict(grain_seed=0, num_y_points=0, point_y_value=[0] * 16, point_y_scaling=[0] * 16,
                chroma_scaling_from_luma=0, num_cb_points=0, point_cb_value=[0] * 16, point_cb_scaling=[0] * 16,
                num_cr_points=0, point_cr_value=[0] * 16, point_cr_scaling=[0] * 16, grain_scaling_minus_8=0,
                ar_coeff_lag=0, ar_coeffs_y_plus_128=[0] * 24, ar_coeffs_cb_plus_128=[0] * 25,
                ar_coeffs_cr_plus_128=[0] * 25, ar_coeff_shift_minus_6=0, grain_scale_shift=0, cb_mult=0,
                cb_luma_mult=0, cb_offset=0, cr_mult=0, cr_luma_mult=0, cr_offset=0, overlap_flag=0,
                clip_to_restricted_range=0)


def digest(values):
    h = 0
    for v in values:
        h = (h * 131 + (v & 0xFFFFFFFF)) % 2147483647
    return h


# ---- the fixtures tests/av1_grain.tcyr asserts. A deterministic LCG builds both the parameters and the frame. ----
def lcg(seed):
    x = seed
    while True:
        x = (x * 1103515245 + 12345) % 2147483648
        yield x >> 16


def fixture_params(seed, lag, num_y, num_cb, num_cr, csfl, scale_m8, ar_shift_m6, scale_shift, overlap, clip,
                   extreme=0):
    r = lcg(seed)
    p = blank_params()
    p['grain_seed'] = next(r) & 0xFFFF
    p['ar_coeff_lag'] = lag
    p['chroma_scaling_from_luma'] = csfl
    for key, n in (('y', num_y), ('cb', num_cb), ('cr', num_cr)):
        p['num_%s_points' % key] = n
        v = 0
        for i in range(n):
            v += 1 + next(r) % (240 // max(n, 1))
            p['point_%s_value' % key][i] = min(v, 255)
            p['point_%s_scaling' % key][i] = next(r) % 256
    for k in range(24):
        p['ar_coeffs_y_plus_128'][k] = 128 + (next(r) % 61) - 30
    for k in range(25):
        p['ar_coeffs_cb_plus_128'][k] = 128 + (next(r) % 61) - 30
        p['ar_coeffs_cr_plus_128'][k] = 128 + (next(r) % 61) - 30
    p['grain_scaling_minus_8'] = scale_m8
    p['ar_coeff_shift_minus_6'] = ar_shift_m6
    p['grain_scale_shift'] = scale_shift
    p['cb_mult'], p['cb_luma_mult'], p['cb_offset'] = next(r) % 256, next(r) % 256, next(r) % 512
    p['cr_mult'], p['cr_luma_mult'], p['cr_offset'] = next(r) % 256, next(r) % 256, next(r) % 512
    p['overlap_flag'], p['clip_to_restricted_range'] = overlap, clip
    if extreme:   # drive the Cb merge above Clip1's top and the Cr merge below 0
        p['cb_mult'], p['cb_luma_mult'], p['cb_offset'] = 255, 255, 511
        p['cr_mult'], p['cr_luma_mult'], p['cr_offset'] = 0, 0, 0
    return p


def fixture_frame(seed, w, h, subx, suby, bd, mono, bright=0):
    r = lcg(seed)
    hi = (1 << bd) - 1

    def inv(v):   # bright: the pattern mirrored to the top of the range (exercises the upper clamps)
        return hi - v if bright else v
    Y = [[inv((x * 7 + y * 13 + next(r) % 40) * (hi + 1) // 512 % (hi + 1)) for x in range(w)] for y in range(h)]
    if mono:
        return Y, None, None
    cw, ch = (w + subx) >> subx, (h + suby) >> suby
    U = [[inv((x * 5 + y * 3 + next(r) % 30) * (hi + 1) // 400 % (hi + 1)) for x in range(cw)] for y in range(ch)]
    V = [[inv((x * 11 + y * 2 + next(r) % 50) * (hi + 1) // 700 % (hi + 1)) for x in range(cw)] for y in range(ch)]
    return Y, U, V


# name, w, h, subx, suby, bd, mono, mc_identity, seed, lag, num_y, num_cb, num_cr, csfl, scale_m8, ar_shift_m6,
# scale_shift, overlap, clip[, bright, extreme]
FIXTURES = [
    ('420 8-bit lag3 overlap', 67, 45, 1, 1, 8, 0, 0, 101, 3, 6, 4, 5, 0, 3, 1, 0, 1, 0),
    ('420 10-bit csfl lag2 clip', 50, 70, 1, 1, 10, 0, 0, 202, 2, 8, 0, 0, 1, 1, 0, 1, 1, 1),
    ('444 12-bit lag1 clip MC_IDENTITY', 41, 37, 0, 0, 12, 0, 1, 303, 1, 3, 2, 7, 0, 0, 3, 2, 0, 1),
    ('422 8-bit lag0 overlap, no luma points', 66, 34, 1, 0, 8, 0, 0, 404, 0, 0, 3, 2, 0, 2, 2, 3, 1, 0),
    ('mono 10-bit lag3 overlap', 33, 66, 1, 1, 10, 1, 0, 505, 3, 14, 0, 0, 0, 2, 1, 0, 1, 0),
    # bright frame + extreme chroma multipliers: the restricted-range tops (MC_IDENTITY's luma-range chroma) and
    # the Clip1 on the Cb / Cr merge (above the top / below 0) all bind
    ('444 12-bit bright, clip MC_IDENTITY, extreme mults', 37, 29, 0, 0, 12, 0, 1, 606, 2, 5, 3, 4, 0, 1, 2, 0, 0, 1,
     1, 1),
]


def run_fixture(f):
    name, w, h, sx, sy, bd, mono, mci, seed, lag, ny, ncb, ncr, csfl, sm8, as6, ss, ov, clip = f[:19]
    bright, extreme = (f[19], f[20]) if len(f) > 19 else (0, 0)
    p = fixture_params(seed, lag, ny, ncb, ncr, csfl, sm8, as6, ss, ov, clip, extreme)
    Y, U, V = fixture_frame(seed + 1, w, h, sx, sy, bd, mono, bright)
    g = Grain(p, bd, mono, sx, sy, bool(mci))
    flatY = [v for row in Y for v in row]
    g.synthesize(Y, U, V, w, h)
    out = dict(name=name, params=p,
               luma_grain=digest(v for row in g.LumaGrain for v in row),
               lut=[digest(g.ScalingLut[k]) for k in range(3)],
               Y=digest(v for row in Y for v in row), changedY=sum(1 for a, b in zip(flatY, (v for row in Y for v in row)) if a != b))
    if not mono:
        out['cb_grain'] = digest(v for row in g.CbGrain for v in row)
        out['cr_grain'] = digest(v for row in g.CrGrain for v in row)
        out['U'] = digest(v for row in U for v in row)
        out['V'] = digest(v for row in V for v in row)
    return out


def emit():
    b = ''.join('%03x' % (v + 2048) for v in GS)
    for k in range(0, len(b), 84):   # 28 values a line keeps it under the 120-column lint limit
        print('    av1_grain_hex(t, %d, "%s");' % (k // 3, b[k:k + 84]))


# ---- --crosscheck: this port vs aomdec on a real stream ----
def load_probe(path):
    """Per OUTPUT frame (show_frame or show_existing_frame, in stream order), the fields vector-probe printed,
    with the sequence's matrix_coefficients attached."""
    frames, cur, mc = [], None, 2
    for line in open(path):
        line = line.strip()
        if '=' not in line:
            continue
        k, v = line.split('=', 1)
        v = v.split()[0] if v.split() else ''
        if k == 'matrix_coefficients':
            mc = int(v)
            continue
        if k == 'frame_type':
            cur = {'matrix_coefficients': mc}
            frames.append(cur)
        if cur is None:
            continue
        if k.startswith('fg_') and ',' in v:
            cur[k] = [int(t) for t in v.split(',')]
        else:
            try:
                cur[k] = int(v)
            except ValueError:
                pass
    return [f for f in frames if f.get('show_existing_frame') == 1 or f.get('show_frame') == 1]


def crosscheck(probe, skip, ref, w, h, fmt, bd):
    subx, suby = {'420': (1, 1), '422': (1, 0), '444': (0, 0), 'mono': (1, 1)}[fmt]
    mono = fmt == 'mono'
    bps = 2 if bd > 8 else 1
    cw, ch = (w + subx) >> subx, (h + suby) >> suby
    fsize = (w * h + (0 if mono else 2 * cw * ch)) * bps
    frames = load_probe(probe)
    sb, rb = open(skip, 'rb').read(), open(ref, 'rb').read()
    n = len(sb) // fsize
    assert n == len(rb) // fsize == len(frames), (n, len(rb) // fsize, len(frames))
    ok = grained = 0
    for k in range(n):
        def plane(buf, off, pw, ph):
            return [[int.from_bytes(buf[off + (y * pw + x) * bps:off + (y * pw + x + 1) * bps], 'little')
                     for x in range(pw)] for y in range(ph)]
        base = k * fsize
        Y = plane(sb, base, w, h)
        U = V = None
        if not mono:
            U = plane(sb, base + w * h * bps, cw, ch)
            V = plane(sb, base + (w * h + cw * ch) * bps, cw, ch)
        f = frames[k]
        if f.get('fg_apply_grain'):
            grained += 1
            p = blank_params()
            for key in p:
                if ('fg_' + key) in f:
                    v = f['fg_' + key]
                    if isinstance(p[key], list):
                        p[key][:len(v)] = v
                    else:
                        p[key] = v
            Grain(p, bd, mono, subx, suby, f.get('matrix_coefficients') == 0).synthesize(Y, U, V, w, h)
        out = bytearray()
        for pl in ([Y] if mono else [Y, U, V]):
            for row in pl:
                for v in row:
                    out += v.to_bytes(bps, 'little')
        if bytes(out) == rb[base:base + fsize]:
            ok += 1
        else:
            print('frame %d DIFFERS' % (k + 1))
    print('crosscheck: %d/%d frames match aomdec (%d with grain applied)' % (ok, n, grained))
    return ok == n


def main():
    global GS
    GS = gaussian_sequence()
    if '--emit' in sys.argv:
        emit()
        return
    if '--crosscheck' in sys.argv:
        a = sys.argv[sys.argv.index('--crosscheck') + 1:]
        sys.exit(0 if crosscheck(a[0], a[1], a[2], int(a[3]), int(a[4]), a[5], int(a[6])) else 1)
    print('Gaussian_Sequence: 2048 entries from the spec markdown; digest(v + 2048) =',
          digest(v + 2048 for v in GS), '; GS[0..3] =', GS[:4], '; GS[2047] =', GS[2047])
    g = Grain(blank_params(), 8, 0, 1, 1)
    g.RandomRegister = 0x1234
    print('get_random_number from 0x1234: bits 11 x4 =', [g.get_random_number(11) for _ in range(4)],
          '; then bits 8 =', g.get_random_number(8), '; register now', g.RandomRegister)
    for f in FIXTURES:
        o = run_fixture(f)
        print('fixture %s: seed %d' % (o['name'], o['params']['grain_seed']))
        print('   luma_grain %d cb_grain %s cr_grain %s lut %s' % (o['luma_grain'], o.get('cb_grain'), o.get('cr_grain'),
                                                                   o['lut']))
        print('   Y %d (%d samples changed) U %s V %s' % (o['Y'], o['changedY'], o.get('U'), o.get('V')))


if __name__ == '__main__':
    main()
