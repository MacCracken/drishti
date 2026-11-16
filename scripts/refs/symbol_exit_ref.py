#!/usr/bin/env python3
"""symbol_exit_ref.py — spec-literal reference for the symbol decoder's EXIT process (tests/av1_symbol.tcyr).

Transcribes, from the AV1 specification's parsing process (09.parsing.process.md, section 8.2), not from drishti:
  8.2.2 init_symbol( sz ):   numBits = Min( sz * 8, 15 ); buf = f( numBits ); paddedBuf = buf << ( 15 - numBits );
                             SymbolValue = ( ( 1 << 15 ) - 1 ) ^ paddedBuf; SymbolRange = 1 << 15;
                             SymbolMaxBits = 8 * sz - 15
  8.2.3 read_bool( ):        read_symbol over the fixed cdf { 1 << 14, 1 << 15, 0 }
  8.2.6 read_symbol( cdf ):  the cur / prev search, then the renormalisation that reads
                             numBits = Min( bits, Max( 0, SymbolMaxBits ) ) more bits and lowers SymbolMaxBits by bits
  8.2.4 exit_symbol( ):      the three conformance requirements —
                               SymbolMaxBits >= -14;
                               trailingBitPosition = get_position( ) - Min( 15, SymbolMaxBits + 15 ) holds a 1;
                               every bit strictly between it and paddingEndPosition (after advancing
                               Max( 0, SymbolMaxBits )) is 0.

Each case is (bytes, number of read_bool calls) -> the exit verdict, and every expectation is ASSERTED.
Run: python3 scripts/refs/symbol_exit_ref.py
"""
import sys

EC_PROB_SHIFT, EC_MIN_PROB = 6, 4


class Reader:
    def __init__(self, data):
        self.d, self.pos = data, 0

    def f(self, n):
        x = 0
        for _ in range(n):
            x = (x << 1) | ((self.d[self.pos >> 3] >> (7 - (self.pos & 7))) & 1)
            self.pos += 1
        return x


def floor_log2(x):
    return x.bit_length() - 1


def decode(data, nbools):
    """-> (verdict, trailingBitPosition or None). verdict: 'ok' / 'maxbits' / 'trailing' / 'padding'."""
    r = Reader(data)
    sz = len(data)
    nb = min(sz * 8, 15)
    buf = r.f(nb)
    value = ((1 << 15) - 1) ^ (buf << (15 - nb))
    rng = 1 << 15
    maxbits = 8 * sz - 15
    for _ in range(nbools):
        cdf, n = [1 << 14, 1 << 15, 0], 2
        cur, sym = rng, -1
        while True:
            sym += 1
            prev = cur
            f = (1 << 15) - cdf[sym]
            cur = ((rng >> 8) * (f >> EC_PROB_SHIFT) >> (7 - EC_PROB_SHIFT)) + EC_MIN_PROB * (n - sym - 1)
            if value >= cur:
                break
        rng = prev - cur
        value = value - cur
        bits = 15 - floor_log2(rng)
        rng = rng << bits
        num = min(bits, max(0, maxbits))
        new = r.f(num)
        padded = new << (bits - num)
        value = padded ^ (((value + 1) << bits) - 1)
        maxbits -= bits
    if maxbits < -14:
        return 'maxbits', None
    trailing = r.pos - min(15, maxbits + 15)
    r.pos += max(0, maxbits)
    end = r.pos
    bit = lambda p: (data[p >> 3] >> (7 - (p & 7))) & 1
    if bit(trailing) != 1:
        return 'trailing', trailing
    if any(bit(p) for p in range(trailing + 1, end)):
        return 'padding', trailing
    return 'ok', trailing


def main():
    n = 0

    def check(got, want, what):
        nonlocal n
        if got != want:
            print('MISMATCH %s: port %r, expected %r' % (what, got, want))
            sys.exit(1)
        n += 1

    # By hand, for no reads (the exit sees init's position only):
    #   1 byte:  SymbolMaxBits = -7, position 8, Min(15, 8) = 8 -> trailing bit 0, nothing to advance, end 8
    #   2 bytes: SymbolMaxBits = 1, position 15, Min(15, 16) = 15 -> trailing bit 0, advance 1, end 16
    cases = [
        (([0x80], 0), ('ok', 0), '1 byte 1000 0000: the trailing bit then zero padding'),
        (([0x81], 0), ('padding', 0), '1 byte 1000 0001: a 1 in the padding'),
        (([0x40], 0), ('trailing', 0), '1 byte 0100 0000: the trailing bit is 0'),
        (([0x80, 0x00], 0), ('ok', 0), '2 bytes 0x80 0x00'),
        (([0x80, 0x01], 0), ('padding', 0), '2 bytes 0x80 0x01: the last padding bit set'),
        (([0x80, 0x00, 0x00, 0x00], 0), ('ok', 0), 'whole zero bytes of padding'),
        (([0x80, 0x00, 0x00, 0x10], 0), ('padding', 0), 'a 1 three bytes into the padding'),
        # With reads, derived by hand. One byte 0x80: init leaves value 16383 and SymbolMaxBits -7, so no read ever
        # pulls data; each read_bool then takes exactly 1 bit (the value runs 32767, 32759, 32743, ... and stays >=
        # the symbol-0 bound 16388 through read 8). After k reads SymbolMaxBits = -7 - k and the position is still 8,
        # so trailingBitPosition = 8 - (8 - k) = k. The same holds for 0x81 (its values 32511, 32247, ... >= 16388).
        (([0x80], 7), ('trailing', 7), 'one byte 0x80, 7 bools: the trailing bit lands on bit 7, a 0'),
        (([0x81], 7), ('ok', 7), 'one byte 0x81, 7 bools: bit 7 is the trailing 1 and nothing follows'),
        (([0x80], 8), ('maxbits', None), 'one byte, 8 bools: SymbolMaxBits -15 < -14'),
        # Two bytes 0x80 0x00: init reads 15 bits (SymbolMaxBits 1); read 1 pulls bit 15 (a 0) and every later read
        # none, each taking 1 bit, so after k >= 1 reads the position is 16, SymbolMaxBits 1 - k, trailing bit k.
        (([0x80, 0x00], 1), ('trailing', 1), 'two bytes, 1 bool: trailing bit 1 is a 0'),
        (([0x80, 0x00], 15), ('trailing', 15), 'two bytes, 15 bools: SymbolMaxBits -14 still allowed, bit 15 a 0'),
        (([0x80, 0x00], 16), ('maxbits', None), 'two bytes, 16 bools: SymbolMaxBits -15'),
    ]
    for (data, k), want, what in cases:
        check(decode(bytes(data), k), want, what)
    print('symbol_exit_ref: %d checks agree with the spec transcription' % n)


if __name__ == '__main__':
    main()
