#!/usr/bin/env python3
"""Spec-literal reference port: the inter_frame_mode_info (5.11.15) OUTER DISPATCH.

Transcribed from 06.bitstream.syntax.md — the 5.11.15 driver plus its two decision
leaves under drishti's 0.7.83 scope (segmentation reads, delta-q/lf reads and the
intra fork are hard-gated DR_ERR_UNSUPPORTED until their bites land; roadmap.md):

  read_skip_mode (5.11.11):
      seg SKIP || seg REF_FRAME || seg GLOBALMV || !skip_mode_present ||
      Block_Width < 8 || Block_Height < 8   -> skip_mode = 0, NO symbol
      else                                  -> @@skip_mode
  skip (5.11.15):  skip_mode -> skip = 1, NO symbol ; else @@skip
  read_is_inter (5.11.15):
      skip_mode                 -> is_inter = 1, NO symbol
      seg REF_FRAME active      -> is_inter = FeatureData != INTRA_FRAME, NO symbol
      seg GLOBALMV active       -> is_inter = 1, NO symbol
      else                      -> @@is_inter

The downstream 5.11.23 schedule is inter_block_ref.py's territory. Shares no code with
src/*.cyr — asserted by tests/av1_intermode.tcyr (test_inter_frame_*).
"""

SEG_SKIP, SEG_REF, SEG_GMV = 6, 5, 7
BLOCK_W = [4, 4, 8, 8, 8, 16, 16, 16, 32, 32, 32, 64, 64, 64, 128, 128, 4, 16, 8, 32, 16, 64]
BLOCK_H = [4, 8, 4, 8, 16, 8, 16, 32, 16, 32, 64, 32, 64, 128, 64, 128, 16, 4, 32, 8, 64, 16]


def skip_mode_gate(seg_active, skip_mode_present, mi_size):
    if seg_active(SEG_SKIP) or seg_active(SEG_REF) or seg_active(SEG_GMV):
        return 'forced 0'
    if not skip_mode_present:
        return 'forced 0'
    if BLOCK_W[mi_size] < 8 or BLOCK_H[mi_size] < 8:
        return 'forced 0'
    return '@@skip_mode'


def is_inter_sel(skip_mode, seg_active, feature_data_ref):
    if skip_mode:
        return ('forced', 1)
    if seg_active(SEG_REF):
        return ('forced', 1 if feature_data_ref != 0 else 0)
    if seg_active(SEG_GMV):
        return ('forced', 1)
    return ('@@is_inter', None)


def outer_schedule(skip_mode_present, mi_size, skip_mode, skip):
    """0.7.83 scope: segmentation disabled -> no seg symbols; deltas gated off."""
    no_seg = lambda j: False
    out = []
    g = skip_mode_gate(no_seg, skip_mode_present, mi_size)
    if g == '@@skip_mode':
        out.append('skip_mode')
    if not skip_mode:
        out.append('skip')
    out.append('[cdef splice]')
    sel, _ = is_inter_sel(skip_mode, no_seg, 0)
    if sel == '@@is_inter':
        out.append('is_inter')
    out.append('-> inter_block_mode_info (5.11.23)')
    return out


def main():
    print("== read_skip_mode gate ==")
    no_seg = lambda j: False
    for (tag, sa, smp, sz) in [
        ("plain 16x16, present",  no_seg, 1, 6),
        ("present off",           no_seg, 0, 6),
        ("4x8 (W < 8)",           no_seg, 1, 1),
        ("8x4 (H < 8)",           no_seg, 1, 2),
        ("8x8 (boundary, open)",  no_seg, 1, 3),
        ("seg SKIP active",       (lambda j: j == SEG_SKIP), 1, 6),
        ("seg REF_FRAME active",  (lambda j: j == SEG_REF), 1, 6),
        ("seg GLOBALMV active",   (lambda j: j == SEG_GMV), 1, 6),
    ]:
        print(f"  {tag:26s} -> {skip_mode_gate(sa, smp, sz)}")
    print("== is_inter selection ==")
    for (tag, sm, sa, fd) in [
        ("skip_mode",             1, no_seg, 0),
        ("seg REF datum 0",       0, (lambda j: j == SEG_REF), 0),
        ("seg REF datum 4",       0, (lambda j: j == SEG_REF), 4),
        ("seg GLOBALMV",          0, (lambda j: j == SEG_GMV), 0),
        ("fall-through",          0, no_seg, 0),
    ]:
        print(f"  {tag:26s} -> {is_inter_sel(sm, sa, fd)}")
    print("== outer schedules (0.7.83 scope) ==")
    for (tag, smp, sz, sm, sk) in [
        ("F1 plain inter",        1, 6, 0, 0),
        ("F2 skip_mode",          1, 6, 1, 1),
        ("F3 present off",        0, 6, 0, 0),
        ("F4 4x8 sub-8",          1, 1, 0, 0),
        ("F5 skip=1 non-skipmode", 1, 6, 0, 1),
    ]:
        print(f"  {tag:26s} -> {' | '.join(outer_schedule(smp, sz, sm, sk))}")


if __name__ == "__main__":
    main()
