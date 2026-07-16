#!/usr/bin/env python3
"""Spec-literal reference port: the read_ref_frames (5.11.25) DISPATCH.

Transcribed from 06.bitstream.syntax.md, "Ref frames syntax":

    read_ref_frames( ) {
        if ( skip_mode ) {
            RefFrame[ 0 ] = SkipModeFrame[ 0 ]
            RefFrame[ 1 ] = SkipModeFrame[ 1 ]
        } else if ( seg_feature_active( SEG_LVL_REF_FRAME ) ) {
            RefFrame[ 0 ] = FeatureData[ segment_id ][ SEG_LVL_REF_FRAME ]
            RefFrame[ 1 ] = NONE
        } else if ( seg_feature_active( SEG_LVL_SKIP ) ||
                    seg_feature_active( SEG_LVL_GLOBALMV ) ) {
            RefFrame[ 0 ] = LAST_FRAME
            RefFrame[ 1 ] = NONE
        } else {
            bw4 = Num_4x4_Blocks_Wide[ MiSize ]
            bh4 = Num_4x4_Blocks_High[ MiSize ]
            if ( reference_select && ( Min( bw4, bh4 ) >= 2 ) )
                @@comp_mode
            else
                comp_mode = SINGLE_REFERENCE
            ... (the single_ref / compound_ref trees, verified 0.7.68 / 0.7.69)
        }
    }

and 5.11.14: seg_feature_active( feature ) = segmentation_enabled &&
FeatureEnabled[ segment_id ][ feature ]. SEG_LVL_REF_FRAME = 5, SEG_LVL_SKIP = 6,
SEG_LVL_GLOBALMV = 7 (section 3 symbols). The single/compound TREES are prior ports'
territory — this port pins WHICH PATH the dispatcher takes and WHICH symbols are coded.
Shares no code with src/*.cyr — asserted by tests/av1_intermode.tcyr
(test_read_ref_frames_dispatch, test_read_ref_frames_tree).
"""

SEG_LVL_REF_FRAME = 5
SEG_LVL_SKIP = 6
SEG_LVL_GLOBALMV = 7
NONE = -1
LAST_FRAME = 1

# spec Num_4x4_Blocks_Wide/High (Block_Width / Block_Height over 4)
NUM_4X4_W = [1, 1, 2, 2, 2, 4, 4, 4, 8, 8, 8, 16, 16, 16, 32, 32, 1, 4, 2, 8, 4, 16]
NUM_4X4_H = [1, 2, 1, 2, 4, 2, 4, 8, 4, 8, 16, 8, 16, 32, 16, 32, 4, 1, 8, 2, 16, 4]


def seg_feature_active(seg_enabled, feature_enabled, segment_id, feature):
    return 1 if (seg_enabled and feature_enabled[segment_id][feature]) else 0


def read_ref_frames_dispatch(skip_mode, seg_enabled, feature_enabled, feature_data,
                             segment_id, skip_mode_frame, reference_select, mi_size):
    """-> (path, symbols, fixed_pair or None). symbols names what the bitstream carries."""
    if skip_mode:
        return ('SKIP_MODE', 'none', (skip_mode_frame[0], skip_mode_frame[1]))
    if seg_feature_active(seg_enabled, feature_enabled, segment_id, SEG_LVL_REF_FRAME):
        return ('SEG_REF', 'none',
                (feature_data[segment_id][SEG_LVL_REF_FRAME], NONE))
    if (seg_feature_active(seg_enabled, feature_enabled, segment_id, SEG_LVL_SKIP) or
            seg_feature_active(seg_enabled, feature_enabled, segment_id, SEG_LVL_GLOBALMV)):
        return ('SEG_FIXED', 'none', (LAST_FRAME, NONE))
    bw4 = NUM_4X4_W[mi_size]
    bh4 = NUM_4X4_H[mi_size]
    if reference_select and min(bw4, bh4) >= 2:
        return ('TREE', 'comp_mode + tree', None)
    return ('TREE', 'tree only (forced SINGLE)', None)


def main():
    def fe(seg=None, j=None):
        rows = [[0] * 8 for _ in range(8)]
        if seg is not None:
            rows[seg][j] = 1
        return rows

    fd = [[0] * 8 for _ in range(8)]
    fd[2][SEG_LVL_REF_FRAME] = 4          # GOLDEN
    fd[4][SEG_LVL_REF_FRAME] = 7          # ALTREF (upper clip boundary)
    fd[5][SEG_LVL_REF_FRAME] = 0          # INTRA_FRAME datum (lower clip boundary)
    smf = (1, 5)

    cases = [
        # (tag, skip, seg_en, feature_enabled, segment_id, ref_select, mi_size)
        ("A  skip_mode",                       1, 0, fe(), 0, 1, 6),
        ("B  seg REF_FRAME active",            0, 1, fe(2, SEG_LVL_REF_FRAME), 2, 1, 6),
        ("B2 ...same but segmentation OFF",    0, 0, fe(2, SEG_LVL_REF_FRAME), 2, 1, 6),
        ("B3 ...same but OTHER segment_id",    0, 1, fe(2, SEG_LVL_REF_FRAME), 3, 1, 6),
        ("B4 seg REF_FRAME data 7 (ALTREF)",   0, 1, fe(4, SEG_LVL_REF_FRAME), 4, 1, 6),
        ("B5 seg REF_FRAME data 0 (INTRA)",    0, 1, fe(5, SEG_LVL_REF_FRAME), 5, 1, 6),
        ("C  seg SKIP active",                 0, 1, fe(1, SEG_LVL_SKIP), 1, 1, 6),
        ("C2 seg GLOBALMV active",             0, 1, fe(1, SEG_LVL_GLOBALMV), 1, 1, 6),
        ("D  skip_mode BEATS seg REF_FRAME",   1, 1, fe(2, SEG_LVL_REF_FRAME), 2, 1, 6),
        ("E  tree, ref_select on, 16x16",      0, 0, fe(), 0, 1, 6),
        ("E2 tree, ref_select OFF, 16x16",     0, 0, fe(), 0, 0, 6),
        ("F  tree, 4x8 (min bw4,bh4 = 1)",     0, 0, fe(), 0, 1, 1),
        ("F2 tree, 8x4 (min = 1)",             0, 0, fe(), 0, 1, 2),
        ("F3 tree, 8x8 (min = 2, boundary)",   0, 0, fe(), 0, 1, 3),
    ]
    print("== read_ref_frames dispatch (path / symbols / fixed pair) ==")
    for (tag, sk, se, feats, sid, rs, sz) in cases:
        path, sym, pair = read_ref_frames_dispatch(sk, se, feats, fd, sid, smf, rs, sz)
        print(f"  {tag:36s} -> {path:9s} | {sym:26s} | {pair}")
    # the REF_FRAME-beats-SKIP priority, both features on the SAME segment:
    both = fe(3, SEG_LVL_REF_FRAME)
    both[3][SEG_LVL_SKIP] = 1
    fd[3][SEG_LVL_REF_FRAME] = 2          # LAST2
    path, sym, pair = read_ref_frames_dispatch(0, 1, both, fd, 3, smf, 1, 6)
    print(f"  {'G  REF_FRAME beats SKIP (same seg)':36s} -> {path:9s} | {sym:26s} | {pair}")


if __name__ == "__main__":
    main()
