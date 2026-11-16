#!/usr/bin/env python3
"""lst_ref.py — spec-literal reference for AV1 large scale tile's syntax and placement (tests/av1_lst.tcyr).

Transcribes, from the AV1 specification (not from drishti or any decoder):
  5.12.1 tile_list_obu()   output_frame_width_in_tiles_minus_1 f(8), output_frame_height_in_tiles_minus_1 f(8),
                           tile_count_minus_1 f(16), then tile_count_minus_1 + 1 tile_list_entry()
  5.12.2 tile_list_entry() anchor_frame_idx f(8), anchor_tile_row f(8), anchor_tile_col f(8),
                           tile_data_size_minus_1 f(16), N = 8 * (tile_data_size_minus_1 + 1), coded_tile_data f(N)
  6.11.1                   tile_count_minus_1 <= 511
  7.3.1                    "the number of tiles ... must be less than or equal to" output_frame_width_in_tiles *
                           output_frame_height_in_tiles; each decoded tile lands at
                           destX = TileWidth * (tile % output_frame_width_in_tiles),
                           destY = TileHeight * (tile / output_frame_width_in_tiles), chroma >> subsampling

A read past the payload is a truncation (drishti: DR_ERR_TRUNCATED); a broken limit is a bad header
(DR_ERR_BAD_HEADER). Every expectation below is ASSERTED against this port, so a mislabelled case fails here
before it can be pinned in the Cyrius suite. Run: python3 scripts/refs/lst_ref.py
"""
import sys


class Truncated(Exception):
    pass


class BadHeader(Exception):
    pass


class Bits:
    """f(n): n bits, most significant first (4.10.2), over a byte payload of sz bytes."""

    def __init__(self, data, sz):
        self.data, self.sz, self.pos = data, sz, 0

    def f(self, n):
        x = 0
        for _ in range(n):
            byte = self.pos >> 3
            if byte >= self.sz:
                raise Truncated()
            x = (x << 1) | ((self.data[byte] >> (7 - (self.pos & 7))) & 1)
            self.pos += 1
        return x


def tile_list_obu(data, sz):
    b = Bits(data, sz)
    out = {'ow': b.f(8) + 1, 'oh': b.f(8) + 1}
    tile_count_minus_1 = b.f(16)
    if tile_count_minus_1 > 511:                                  # 6.11.1
        raise BadHeader()
    if tile_count_minus_1 + 1 > out['ow'] * out['oh']:             # 7.3.1
        raise BadHeader()
    ents = []
    for _ in range(tile_count_minus_1 + 1):                       # tile_list_entry()
        e = {'anchor': b.f(8), 'row': b.f(8), 'col': b.f(8)}
        size = b.f(16) + 1
        e['data'] = b.pos >> 3                                    # byte offset of coded_tile_data
        e['dsize'] = size
        for _ in range(size):
            b.f(8)                                                # coded_tile_data f(N)
        ents.append(e)
    out['ents'] = ents
    return out


def dest(tile, out_w_tiles, tile_w, tile_h, sub_x, sub_y):
    """7.3.1: the output position of the tile-th decoded tile, in samples of a plane with subsampling (sub_x, sub_y)."""
    return ((tile_w * (tile % out_w_tiles)) >> sub_x, (tile_h * (tile // out_w_tiles)) >> sub_y)


def entry(anchor, row, col, nbytes, fill):
    return [anchor, row, col, (nbytes - 1) >> 8, (nbytes - 1) & 255] + [(fill + i) & 255 for i in range(nbytes)]


def outcome(buf, sz):
    try:
        return tile_list_obu(buf, sz)
    except Truncated:
        return 'TRUNCATED'
    except BadHeader:
        return 'BAD_HEADER'


def main():
    n = 0

    def check(got, want, what):
        nonlocal n
        if got != want:
            print('MISMATCH %s: port %r, expected %r' % (what, got, want))
            sys.exit(1)
        n += 1

    # test_lst_parse's fixture: a 2 x 2-tile output frame, three entries
    buf = [1, 1, 0, 2] + entry(5, 1, 0, 2, 170) + entry(7, 0, 1, 1, 204) + entry(0, 2, 3, 3, 1)
    tl = outcome(buf, len(buf))
    check((tl['ow'], tl['oh'], len(tl['ents'])), (2, 2, 3), 'list header')
    e0, e1, e2 = tl['ents']
    check((e0['anchor'], e0['row'], e0['col'], e0['data'], e0['dsize']), (5, 1, 0, 9, 2), 'entry 0')
    check(buf[e0['data'] + 1], 171, 'entry 0 second data byte')
    check((e1['anchor'], e1['data']), (7, 16), 'entry 1')
    check((e2['col'], e2['data'], e2['dsize']), (3, 22, 3), 'entry 2')
    check(len(buf), 25, 'the fixture is 25 bytes')
    check(outcome(buf, 3), 'TRUNCATED', '3 bytes: no list header')
    check(outcome(buf, 24), 'TRUNCATED', 'the last tile one byte short')
    check(outcome(buf, 19), 'TRUNCATED', 'the last entry header cut (4 of its 5 bytes present)')
    check(outcome(buf, 20), 'TRUNCATED', 'the last entry header whole, its data absent')
    over = [1, 1, 0, 4] + entry(0, 0, 0, 1, 0) * 5
    check(outcome(over, len(over)), 'BAD_HEADER', '5 tiles into a 2 x 2 output frame')
    check(outcome([255, 255, 2, 0] + [0] * 4092, 4096), 'BAD_HEADER', 'tile_count_minus_1 512')
    lim = [31, 15, 1, 255]
    for k in range(512):
        lim += entry(k & 127, 0, 0, 1, 0)
    got = outcome(lim, len(lim))
    check(len(got['ents']) if isinstance(got, dict) else got, 512, '512 tiles into a 32 x 16 output frame')

    # test_lst_dest's cases: (tile, output_frame_width_in_tiles, TileWidth, TileHeight, sub) -> (destX, destY)
    check(dest(0, 3, 64, 64, 0, 0), (0, 0), 'tile 0')
    check(dest(4, 3, 64, 64, 0, 0), (64, 64), 'tile 4 of 3 across')
    check(dest(5, 3, 64, 64, 0, 0)[0], 128, 'tile 5 x')
    check(dest(7, 3, 64, 128, 0, 0)[1], 256, 'tile 7, 128 high')
    check(dest(4, 3, 64, 64, 1, 1), (32, 32), 'tile 4 chroma 4:2:0')
    # the reproducer geometry: an 8 x 8-tile output frame of 64 x 64 tiles; the last of 64 tiles, luma and chroma
    check(dest(63, 8, 64, 64, 0, 0), (448, 448), 'tile 63 of an 8 x 8 output')
    check(dest(63, 8, 64, 64, 1, 1), (224, 224), 'tile 63 chroma')
    print('lst_ref: %d checks agree with the spec transcription' % n)


if __name__ == '__main__':
    main()
