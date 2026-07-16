#!/usr/bin/env python3
"""Spec-literal reference port: read_motion_mode (5.11.27) branch decision + is_scaled.

Transcribed from 06.bitstream.syntax.md, "Read motion mode syntax":

    read_motion_mode( isCompound ) {
        if ( skip_mode ) { motion_mode = SIMPLE; return }
        if ( !is_motion_mode_switchable ) { motion_mode = SIMPLE; return }
        if ( Min( Block_Width[ MiSize ], Block_Height[ MiSize ] ) < 8 ) {
            motion_mode = SIMPLE; return }
        if ( !force_integer_mv && ( YMode == GLOBALMV || YMode == GLOBAL_GLOBALMV ) ) {
            if ( GmType[ RefFrame[ 0 ] ] > TRANSLATION ) { motion_mode = SIMPLE; return } }
        if ( isCompound || RefFrame[ 1 ] == INTRA_FRAME ||
             !has_overlappable_candidates( ) ) { motion_mode = SIMPLE; return }
        find_warp_samples()
        if ( force_integer_mv || NumSamples == 0 ||
             !allow_warped_motion || is_scaled( RefFrame[0] ) ) {
            @@use_obmc          ->  motion_mode = use_obmc ? OBMC : SIMPLE
        } else {
            @@motion_mode
        }
    }

and (same section) the is_scaled helper:

    is_scaled( refFrame ) {
      refIdx = ref_frame_idx[ refFrame - LAST_FRAME ]
      xScale = ( ( RefUpscaledWidth[ refIdx ] << REF_SCALE_SHIFT ) +
                 ( FrameWidth / 2 ) ) / FrameWidth
      yScale = ( ( RefFrameHeight[ refIdx ] << REF_SCALE_SHIFT ) +
                 ( FrameHeight / 2 ) ) / FrameHeight
      noScale = 1 << REF_SCALE_SHIFT
      return xScale != noScale || yScale != noScale
    }

REF_SCALE_SHIFT = 14 (03.symbols.md). Block_Width / Block_Height are the 22-entry
tables from the spec. Shares no code with src/*.cyr — asserted by
tests/av1_intermode.tcyr (test_is_scaled, test_read_motion_mode_gate).
"""

REF_SCALE_SHIFT = 14
LAST_FRAME = 1
INTRA_FRAME = 0
TRANSLATION = 1          # GmType: IDENTITY=0 TRANSLATION=1 ROTZOOM=2 AFFINE=3

# spec YMode numbering (intra 0..13, then the inter modes)
GLOBALMV = 16
GLOBAL_GLOBALMV = 24

# spec Block_Width / Block_Height (22 BLOCK_SIZES, section 6.10.4 semantics order)
BLOCK_WIDTH = [4, 4, 8, 8, 8, 16, 16, 16, 32, 32, 32, 64, 64, 64, 128, 128, 4, 16, 8, 32, 16, 64]
BLOCK_HEIGHT = [4, 8, 4, 8, 16, 8, 16, 32, 16, 32, 64, 32, 64, 128, 64, 128, 16, 4, 32, 8, 64, 16]


def is_scaled(ref_frame, ref_frame_idx, ref_upscaled_width, ref_frame_height,
              frame_width, frame_height):
    ref_idx = ref_frame_idx[ref_frame - LAST_FRAME]
    x_scale = ((ref_upscaled_width[ref_idx] << REF_SCALE_SHIFT) +
               (frame_width // 2)) // frame_width
    y_scale = ((ref_frame_height[ref_idx] << REF_SCALE_SHIFT) +
               (frame_height // 2)) // frame_height
    no_scale = 1 << REF_SCALE_SHIFT
    return 1 if (x_scale != no_scale or y_scale != no_scale) else 0


def read_motion_mode_branch(skip_mode, is_motion_mode_switchable, mi_size,
                            force_integer_mv, y_mode, gm_type_ref0,
                            is_compound, ref_frame1, has_overlappable,
                            num_samples, allow_warped_motion, scaled):
    """Which of the three 5.11.27 outcomes the gate reaches:
    'SIMPLE' (early return, NO symbol), 'OBMC' (@@use_obmc), 'WARP' (@@motion_mode)."""
    if skip_mode:
        return 'SIMPLE'
    if not is_motion_mode_switchable:
        return 'SIMPLE'
    if min(BLOCK_WIDTH[mi_size], BLOCK_HEIGHT[mi_size]) < 8:
        return 'SIMPLE'
    if (not force_integer_mv) and (y_mode == GLOBALMV or y_mode == GLOBAL_GLOBALMV):
        if gm_type_ref0 > TRANSLATION:
            return 'SIMPLE'
    if is_compound or ref_frame1 == INTRA_FRAME or not has_overlappable:
        return 'SIMPLE'
    # find_warp_samples() runs here -> num_samples
    if force_integer_mv or num_samples == 0 or (not allow_warped_motion) or scaled:
        return 'OBMC'
    return 'WARP'


def main():
    print("== is_scaled known answers (ref_uw, ref_h, fw, fh -> scaled) ==")
    idx = [0] * 7          # ref_frame_idx[i] = 0: everything maps to slot 0
    for (ruw, rh, fw, fh) in [
        (64, 64, 64, 64),          # identical dims -> 0
        (128, 64, 64, 64),         # wider ref -> 1
        (64, 128, 64, 64),         # taller ref -> 1
        (32, 64, 64, 64),          # narrower ref -> 1
        (32767, 64, 32768, 64),    # x rounding edge: 16383.5 rounds UP to noScale -> 0
        (32766, 64, 32768, 64),    # one below the rounding edge -> 1
        (64, 32767, 64, 32768),    # y rounding edge -> 0
    ]:
        s = is_scaled(LAST_FRAME, idx, [ruw] * 8, [rh] * 8, fw, fh)
        print(f"  ({ruw}, {rh}, {fw}, {fh}) -> {s}")

    print("== read_motion_mode branch decisions ==")
    # (tag, skip, switchable, mi_size, force_int, y_mode, gm_type, is_comp, ref1,
    #  overlappable, num_samples, allow_warp, scaled)
    NEWMV = 17
    NONE = -1
    cases = [
        ("A  permissive NEWMV",              0, 1, 6, 0, NEWMV, 1, 0, NONE, 1, 4, 1, 0),
        ("B  skip_mode",                     1, 1, 6, 0, NEWMV, 1, 0, NONE, 1, 4, 1, 0),
        ("C  !switchable",                   0, 0, 6, 0, NEWMV, 1, 0, NONE, 1, 4, 1, 0),
        ("D  4x4 (min<8)",                   0, 1, 0, 0, NEWMV, 1, 0, NONE, 1, 4, 1, 0),
        ("D2 4x8 (min<8)",                   0, 1, 1, 0, NEWMV, 1, 0, NONE, 1, 4, 1, 0),
        ("D3 8x8 (boundary IS large)",       0, 1, 3, 0, NEWMV, 1, 0, NONE, 1, 4, 1, 0),
        ("E  GLOBALMV + ROTZOOM",            0, 1, 6, 0, GLOBALMV, 2, 0, NONE, 1, 4, 1, 0),
        ("E2 GLOBALMV + TRANSLATION",        0, 1, 6, 0, GLOBALMV, 1, 0, NONE, 1, 4, 1, 0),
        ("E3 GLOBALMV + ROTZOOM + forceint", 0, 1, 6, 1, GLOBALMV, 2, 0, NONE, 1, 4, 1, 0),
        ("F  compound",                      0, 1, 6, 0, NEWMV, 1, 1, 5, 1, 4, 1, 0),
        ("G  interintra ref1=INTRA",         0, 1, 6, 0, NEWMV, 1, 0, INTRA_FRAME, 1, 4, 1, 0),
        ("H  no overlappable",               0, 1, 6, 0, NEWMV, 1, 0, NONE, 0, 4, 1, 0),
        ("I  NumSamples == 0",               0, 1, 6, 0, NEWMV, 1, 0, NONE, 1, 0, 1, 0),
        ("J  !allow_warped_motion",          0, 1, 6, 0, NEWMV, 1, 0, NONE, 1, 4, 0, 0),
        ("K  scaled ref",                    0, 1, 6, 0, NEWMV, 1, 0, NONE, 1, 4, 1, 1),
        ("L  GLOBAL_GLOBALMV + AFFINE",      0, 1, 6, 0, GLOBAL_GLOBALMV, 3, 0, NONE, 1, 4, 1, 0),
        # the y_mode restriction on the global gate: a NON-GLOBALMV-family mode is NOT
        # gated by a beyond-TRANSLATION model — the gate applies to GLOBALMV family only.
        ("M  NEWMV + ROTZOOM (not gated)",   0, 1, 6, 0, NEWMV, 2, 0, NONE, 1, 4, 1, 0),
        ("M2 NEWMV + AFFINE (not gated)",    0, 1, 6, 0, NEWMV, 3, 0, NONE, 1, 4, 1, 0),
    ]
    for (tag, sk, sw, sz, fi, ym, gt, ic, r1, ov, ns, aw, sc) in cases:
        br = read_motion_mode_branch(sk, sw, sz, fi, ym, gt, ic, r1, ov, ns, aw, sc)
        print(f"  {tag:36s} -> {br}")


if __name__ == "__main__":
    main()
