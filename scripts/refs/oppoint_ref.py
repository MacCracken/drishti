#!/usr/bin/env python3
"""oppoint_ref.py — spec-literal reference for AV1 operating point selection and drop_obu (tests/av1_oppoint.tcyr).

Transcribes, from the AV1 specification (not from drishti or any decoder):
  5.3.1  open_bitstream_unit():
             if ( obu_type != OBU_SEQUENCE_HEADER && obu_type != OBU_TEMPORAL_DELIMITER &&
                  OperatingPointIdc != 0 && obu_extension_flag == 1 ) {
                 inTemporalLayer = (OperatingPointIdc >> temporal_id ) & 1
                 inSpatialLayer = (OperatingPointIdc >> ( spatial_id + 8 ) ) & 1
                 if ( !inTemporalLayer || ! inSpatialLayer ) { drop_obu( ); return }
             }
  5.5.1  operatingPoint = choose_operating_point( ); OperatingPointIdc = operating_point_idc[ operatingPoint ]
  6.4.1  choose_operating_point "must return a value ... between 0 and operating_points_cnt_minus_1"; an operating
         point "may be explicitly signaled by external means". The fall-back to 0 for a request out of range is the
         choice libaom (read_sequence_header_obu) and dav1d make; aomdec / dav1d --oppoint 9 on a 4-point stream
         decode operating point 0 (checked in 0.8.4).

Every boundary case is ASSERTED, so a mislabelled expectation fails here before it can be pinned in the Cyrius suite.
The sweep covers every operating_point_idc (12 bits), every obu_type (0..15), both extension flags, every
temporal_id (0..7) and spatial_id (0..3), in that nesting order, and prints the dropped count and an FNV-1a digest of
the keep (1) / drop (0) sequence. Run: python3 scripts/refs/oppoint_ref.py
"""
import sys

OBU_SEQUENCE_HEADER, OBU_TEMPORAL_DELIMITER, OBU_FRAME_HEADER, OBU_TILE_GROUP = 1, 2, 3, 4
OBU_METADATA, OBU_FRAME, OBU_TILE_LIST, OBU_PADDING = 5, 6, 8, 15
DIGEST = 0x10DAAB85   # FNV-1a over the sweep, as printed by this port (the count is derived independently below)


def in_operating_point(op_idc, obu_type, ext, tid, sid):
    """1 when the OBU is decoded, 0 when 5.3.1 calls drop_obu()."""
    if obu_type != OBU_SEQUENCE_HEADER and obu_type != OBU_TEMPORAL_DELIMITER and op_idc != 0 and ext == 1:
        in_temporal = (op_idc >> tid) & 1
        in_spatial = (op_idc >> (sid + 8)) & 1
        if not in_temporal or not in_spatial:
            return 0
    return 1


def choose(requested, op_cnt_minus_1):
    return requested if 0 <= requested <= op_cnt_minus_1 else 0


def sweep():
    h, drops = 2166136261, 0
    for op_idc in range(4096):
        for obu_type in range(16):
            for ext in range(2):
                for tid in range(8):
                    for sid in range(4):
                        r = in_operating_point(op_idc, obu_type, ext, tid, sid)
                        drops += 1 - r
                        h = ((h ^ r) * 16777619) & 0xFFFFFFFF
    return drops, h


def main():
    n = 0

    def check(got, want, what):
        nonlocal n
        if got != want:
            print('MISMATCH %s: port %r, expected %r' % (what, got, want))
            sys.exit(1)
        n += 1

    # (op_idc, obu_type, ext, tid, sid) -> keep; the cases tests/av1_oppoint.tcyr pins
    cases = [
        ((0x101, OBU_FRAME, 1, 1, 0), 0, 'temporal layer 1 outside { TL0 } x { SL0 }'),
        ((0x101, OBU_FRAME, 1, 0, 1), 0, 'spatial layer 1 outside { TL0 } x { SL0 }'),
        ((0x101, OBU_FRAME, 1, 0, 0), 1, 'the base layer inside it'),
        ((0x101, OBU_FRAME, 0, 1, 1), 1, 'no extension header: never dropped (its tid / sid read as 0 anyway)'),
        ((0x000, OBU_FRAME, 1, 7, 3), 1, 'OperatingPointIdc 0: every OBU decodes'),
        ((0x101, OBU_SEQUENCE_HEADER, 1, 7, 3), 1, 'a sequence header is never dropped'),
        ((0x101, OBU_TEMPORAL_DELIMITER, 1, 7, 3), 1, 'nor a temporal delimiter'),
        ((0x101, OBU_FRAME_HEADER, 1, 5, 0), 0, 'a frame header is'),
        ((0x101, OBU_TILE_GROUP, 1, 5, 0), 0, 'a tile group is'),
        ((0x101, OBU_METADATA, 1, 5, 0), 0, 'metadata is'),
        ((0x101, OBU_TILE_LIST, 1, 5, 0), 0, 'a tile list is'),
        ((0x101, OBU_PADDING, 1, 5, 0), 0, 'padding is'),
        ((0x101, 0, 1, 5, 0), 0, 'a reserved type is'),
        ((0xF80, OBU_FRAME, 1, 7, 3), 1, 'the top temporal (bit 7) and spatial (bit 11) layers'),
        ((0x780, OBU_FRAME, 1, 7, 3), 0, 'bit 11 clear: spatial layer 3 out'),
        ((0xF7F, OBU_FRAME, 1, 7, 3), 0, 'bit 7 clear: temporal layer 7 out'),
        ((0x307, OBU_FRAME, 1, 2, 1), 1, 'L2T3 operating point 0 (0x307): TL2 SL1 in'),
        ((0x307, OBU_FRAME, 1, 3, 0), 0, '...TL3 out'),
        ((0x307, OBU_FRAME, 1, 0, 2), 0, '...SL2 out'),
        ((0x200, OBU_FRAME, 1, 0, 1), 0, 'a spatial bit with no temporal bit: nothing is in'),
        ((0x001, OBU_FRAME, 1, 0, 0), 0, 'a temporal bit with no spatial bit: nothing is in'),
    ]
    for args, want, what in cases:
        check(in_operating_point(*args), want, what)
    # choose_operating_point: (requested, operating_points_cnt_minus_1) -> chosen
    for args, want, what in [((0, 0), 0, 'no scalability'), ((3, 3), 3, 'the last point'),
                             ((4, 3), 0, 'one past it falls back to 0'), ((31, 0), 0, '31 of 1'),
                             ((2, 8), 2, 'inside'), ((-1, 8), 0, 'negative')]:
        check(choose(*args), want, 'choose ' + what)
    drops, digest = sweep()
    # the count, derived without the port: only the 14 droppable types with ext 1 and op_idc != 0 can drop, and
    # an op_idc with T temporal and S spatial bits keeps T * S of the 32 (tid, sid) cells. Sum over every op_idc of
    # T * S = (sum of popcounts over 256 temporal masks) * (over 16 spatial masks) = 1024 * 32 = 32768, so the
    # drops are 14 * (32 * 4095 - 32768) = 1375808.
    check(drops, 14 * (32 * 4095 - 32768), 'sweep drop count')
    check(digest, DIGEST, 'sweep digest')
    print('oppoint_ref: %d checks agree with the spec transcription; sweep: %d of %d dropped, digest 0x%08X'
          % (n, drops, 4096 * 16 * 2 * 8 * 4, digest))


if __name__ == '__main__':
    main()
