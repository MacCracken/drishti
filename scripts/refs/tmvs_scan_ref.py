#!/usr/bin/env python3
# tmvs_scan_ref.py — spec-literal oracle for the AV1 temporal MV scan (spec 7.10.2.5 temporal_scan + 7.10.2.6
# add_tpl_ref_mv + the ZeroMvContext derivation). Independent transcription from the AV1 spec (7.10.2.5/6 +
# 7.10.2.10 lower_mv_precision) cross-checked vs dav1d refmvs.c + libaom mvref_common.c — NOT derived from the
# Cyrius. Anchors tests/av1_mv.tcyr test_temporal_scan_*. Bite 3 (0.7.104) — the output-CHANGING temporal bite.
#
# drishti reads an ALREADY-projected MV from the per-ref pre-scaled MotionFieldMvs (built by
# av1_motion_field_estimation, 0.7.103), so the scan does NO re-projection (unlike dav1d's deferred scaling);
# it only lowers precision, derives ZeroMvContext, and dedup/appends with weight 2.

SENTINEL = -(1 << 15)  # -32768
MAX_REF_MV_STACK_SIZE = 8


def lower_mv_comp(v, allow_hp, force_int):
    # spec 7.10.2.10 lower_mv_precision, per component (matches av1_lower_mv_comp).
    if allow_hp == 1:
        return v
    if force_int != 0:
        a = -v if v < 0 else v
        aint = (a + 3) >> 3
        return (aint << 3) if v > 0 else -(aint << 3)
    if v & 1:               # odd
        return v - 1 if v > 0 else v + 1
    return v


class Scene:
    def __init__(self, mi_row, mi_col, bw4, bh4, ref0, ref1=None,
                 gmv0=(0, 0), gmv1=(0, 0), allow_hp=1, force_int=0,
                 tile=(0, 16, 0, 16)):
        self.mi_row = mi_row
        self.mi_col = mi_col
        self.bw4 = bw4
        self.bh4 = bh4
        self.ref0 = ref0
        self.ref1 = ref1          # None for single-ref
        self.gmv0 = gmv0
        self.gmv1 = gmv1
        self.allow_hp = allow_hp
        self.force_int = force_int
        self.tile = tile          # (row_start, row_end, col_start, col_end)
        self.field = {}           # (ref, y8, x8) -> (row, col); absent => sentinel
        # stack state:
        self.stack = []           # list of dicts {mv0:(r,c), mv1:(r,c) or None, w:int}
        self.num = 0
        self.zeromvctx = 0        # the driver sets this to 0 before the scan

    def set_cell(self, ref, y8, x8, r, c):
        self.field[(ref, y8, x8)] = (r, c)

    def seed_stack(self, mv0, mv1, w):
        self.stack.append({'mv0': mv0, 'mv1': mv1, 'w': w})
        self.num += 1

    def is_inside(self, r, c):
        rs, re, cs, ce = self.tile
        return rs <= r < re and cs <= c < ce

    def get(self, ref, y8, x8, comp):
        v = self.field.get((ref, y8, x8))
        if v is None:
            return SENTINEL
        return v[comp]

    def lower(self, mv):
        return (lower_mv_comp(mv[0], self.allow_hp, self.force_int),
                lower_mv_comp(mv[1], self.allow_hp, self.force_int))

    def append(self, mv0, mv1, is_compound):
        for e in self.stack:
            if e['mv0'] == mv0 and (not is_compound or e['mv1'] == mv1):
                e['w'] += 2
                return
        if self.num < MAX_REF_MV_STACK_SIZE:
            self.stack.append({'mv0': mv0, 'mv1': mv1 if is_compound else None, 'w': 2})
            self.num += 1

    def add_tpl_ref_mv(self, delta_row, delta_col, is_compound):
        mv_row = (self.mi_row + delta_row) | 1
        mv_col = (self.mi_col + delta_col) | 1
        if not self.is_inside(mv_row, mv_col):
            return
        y8 = mv_row >> 1
        x8 = mv_col >> 1
        at_origin = (delta_row == 0 and delta_col == 0)
        if at_origin:
            self.zeromvctx = 1                          # unconditional, before the candidate read
        if not is_compound:
            c0r = self.get(self.ref0, y8, x8, 0)
            if c0r == SENTINEL:
                return
            c0c = self.get(self.ref0, y8, x8, 1)
            l0 = self.lower((c0r, c0c))
            if at_origin:
                if abs(l0[0] - self.gmv0[0]) >= 16 or abs(l0[1] - self.gmv0[1]) >= 16:
                    self.zeromvctx = 1
                else:
                    self.zeromvctx = 0                  # assignment — may reset to 0
            self.append(l0, None, False)
        else:
            d0r = self.get(self.ref0, y8, x8, 0)
            if d0r == SENTINEL:
                return
            d1r = self.get(self.ref1, y8, x8, 0)
            if d1r == SENTINEL:
                return                                  # both refs must be valid
            l0 = self.lower((d0r, self.get(self.ref0, y8, x8, 1)))
            l1 = self.lower((d1r, self.get(self.ref1, y8, x8, 1)))
            if at_origin:
                if (abs(l0[0] - self.gmv0[0]) >= 16 or abs(l0[1] - self.gmv0[1]) >= 16 or
                        abs(l1[0] - self.gmv1[0]) >= 16 or abs(l1[1] - self.gmv1[1]) >= 16):
                    self.zeromvctx = 1
                else:
                    self.zeromvctx = 0
            self.append(l0, l1, True)

    def sb_ok(self, dR, dC):
        row = (self.mi_row & 15) + dR
        col = (self.mi_col & 15) + dC
        return 0 <= row < 16 and 0 <= col < 16

    def temporal_scan(self, is_compound):
        stepW4 = 4 if self.bw4 >= 16 else 2
        stepH4 = 4 if self.bh4 >= 16 else 2
        endR = min(self.bh4, 16)
        endC = min(self.bw4, 16)
        dR = 0
        while dR < endR:
            dC = 0
            while dC < endC:
                self.add_tpl_ref_mv(dR, dC, is_compound)
                dC += stepW4
            dR += stepH4
        if 2 <= self.bh4 < 16 and 2 <= self.bw4 < 16:
            for dR, dC in ((self.bh4, -2), (self.bh4, self.bw4), (self.bh4 - 2, self.bw4)):
                if self.sb_ok(dR, dC):
                    self.add_tpl_ref_mv(dR, dC, is_compound)

    def dump(self, label):
        print(f"# {label}: ZeroMvContext={self.zeromvctx} NumMvFound={self.num}")
        for i, e in enumerate(self.stack):
            m1 = f" mv1={e['mv1']}" if e['mv1'] is not None else ""
            print(f"    [{i}] mv0={e['mv0']}{m1} w={e['w']}")


def block4x4():
    # BLOCK_4X4: bw4=bh4=1 -> only the (0,0) sample, no extension. Origin cell at (MiRow|1)>>1 etc.
    # MiRow=4,MiCol=6 -> mvRow=5,mvCol=7 -> y8=2,x8=3.
    print("## origin-only (BLOCK_4X4) single-ref, gmv0=(40,0)")
    # A1: sentinel origin -> ZeroMvContext stays 1, no append.
    s = Scene(4, 6, 1, 1, ref0=1, gmv0=(40, 0)); s.temporal_scan(0); s.dump("A1 sentinel origin")
    # A2: valid origin, |cand-gmv|>=16 -> ZeroMvContext=1 + append.
    s = Scene(4, 6, 1, 1, ref0=1, gmv0=(40, 0)); s.set_cell(1, 2, 3, 8, 0); s.temporal_scan(0)
    s.dump("A2 far cand (8,0) vs gmv (40,0)")
    # A3: valid origin, both comps <16 from gmv -> ZeroMvContext=0 (reset) + append.
    s = Scene(4, 6, 1, 1, ref0=1, gmv0=(40, 0)); s.set_cell(1, 2, 3, 32, 8); s.temporal_scan(0)
    s.dump("A3 near cand (32,8) vs gmv (40,0)")
    # A4: lower_mv_precision witness — allow_hp=0, odd candidate rounds toward zero.
    s = Scene(4, 6, 1, 1, ref0=1, gmv0=(0, 0), allow_hp=0); s.set_cell(1, 2, 3, 7, 0 - 3); s.temporal_scan(0)
    s.dump("A4 lower allow_hp=0 cand (7,-3)->(6,-2)")


def block16x16():
    # BLOCK_16X16: bw4=bh4=4 -> main grid (0,0),(0,2),(2,0),(2,2); ext {4,-2},{4,4},{2,4}.
    # MiRow=4,MiCol=4. Map each (dR,dC): mvRow=(4+dR)|1, mvCol=(4+dC)|1, y8=mvRow>>1, x8=mvCol>>1.
    #  (0,0):y8=2,x8=2  (0,2):y8=2,x8=3  (2,0):y8=3,x8=2  (2,2):y8=3,x8=3
    #  {4,-2}:mvRow=9->y8=4,mvCol=(4-2)|1=3->x8=1  {4,4}:y8=4,mvCol=(4+4)|1=9->x8=4  {2,4}:y8=3,x8=4
    print("## grid + extension (BLOCK_16X16) single-ref, gmv0=(0,0)")
    s = Scene(4, 4, 4, 4, ref0=1, gmv0=(0, 0))
    s.set_cell(1, 2, 2, 10, 0)    # (0,0) origin
    s.set_cell(1, 2, 3, 20, 0)    # (0,2)
    s.set_cell(1, 3, 2, 30, 0)    # (2,0)
    s.set_cell(1, 3, 3, 10, 0)    # (2,2) — DUP of origin -> weight +=2 (dedup witness)
    s.set_cell(1, 4, 1, 40, 0)    # {4,-2}
    s.set_cell(1, 4, 4, 50, 0)    # {4,4}
    s.set_cell(1, 3, 4, 60, 0)    # {2,4}
    s.temporal_scan(0)
    s.dump("B grid+ext, (2,2) dups origin")
    # dedup vs a pre-seeded spatial entry.
    s = Scene(4, 4, 4, 4, ref0=1, gmv0=(0, 0))
    s.seed_stack((10, 0), None, 640)   # a spatial entry with REF_CAT_LEVEL weight
    s.set_cell(1, 2, 2, 10, 0)         # origin temporal == the spatial entry -> +=2
    s.temporal_scan(0)
    s.dump("B2 temporal dedups a spatial entry (640+2)")


def compound():
    print("## compound (BLOCK_4X4) ref0=1 ref1=2, gmv0=(0,0) gmv1=(40,0)")
    # both valid -> append the pair; zeromvctx driven by ref1 vs gmv1.
    s = Scene(4, 6, 1, 1, ref0=1, ref1=2, gmv0=(0, 0), gmv1=(40, 0))
    s.set_cell(1, 2, 3, 4, 0)      # cand0 within 16 of gmv0
    s.set_cell(2, 2, 3, 8, 0)      # cand1 (8,0) vs gmv1 (40,0) -> >=16 -> zeromvctx=1
    s.temporal_scan(1)
    s.dump("C1 both-valid, ref1 drives zeromvctx=1")
    # one sentinel (ref1 absent at the cell) -> no append, zeromvctx stays 1 (origin set fired).
    s = Scene(4, 6, 1, 1, ref0=1, ref1=2, gmv0=(0, 0), gmv1=(40, 0))
    s.set_cell(1, 2, 3, 4, 0)      # only ref0 present
    s.temporal_scan(1)
    s.dump("C2 ref1 sentinel -> no append, zeromvctx=1")


def sb_border():
    # A 2-SB-wide frame (32x32, tile [0,32)) with the block in the SECOND SB at MiCol=16 (col&15=0). The
    # extension {4,-2} has check_sb_border col=(0)+(-2)=-2 -> REJECT, but is_inside would PASS (mvCol=(16-2)|1
    # =15 < 32) -> this ISOLATES check_sb_border from is_inside, so a mutation dropping the border check reads
    # the {4,-2} cell (y8=(4+4|1)>>1=4, x8=15>>1=7) and wrongly appends it. Block MiRow=4,MiCol=16,BLOCK_16X16.
    print("## sb_border reject (BLOCK_16X16 in 2nd SB at MiCol=16, 32x32 frame)")
    s = Scene(4, 16, 4, 4, ref0=1, gmv0=(0, 0), tile=(0, 32, 0, 32))
    s.set_cell(1, 2, 8, 10, 0)     # origin (0,0): mvRow=5->y8=2, mvCol=17->x8=8
    s.set_cell(1, 4, 7, 77, 0)     # the {4,-2} cell a border-drop mutant would read (must NOT appear)
    s.set_cell(1, 4, 10, 99, 0)    # {4,4}: mvRow=9->y8=4, mvCol=21->x8=10 -> in-SB, appended
    s.temporal_scan(0)
    s.dump("D sb_border: {4,-2} rejected, {4,4} kept")


if __name__ == "__main__":
    block4x4()
    block16x16()
    compound()
    sb_border()
