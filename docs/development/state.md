# drishti — Current State

> Refreshed every release. CLAUDE.md is preferences/process/procedures
> (durable); this file is **state** (volatile) — versions, counts,
> sizes, in-flight work.

## Version

**0.7.0** — cut 2026-07-10, not yet tagged (user's git). The first cut:
shared core + all four families' bitstream/container/header layers,
spec-derived and adversarially tested. Started at 0.7.0 (not 0.1.0) —
the surface is "almost ready for v1"; the remaining distance is the
per-codec completion arcs (0.7.x AV1 → 0.10.x VP8/VP9) + audit (0.11.x)
+ freeze/docs (0.12.x) → 1.0.0. See [`CHANGELOG.md`](../../CHANGELOG.md)
+ [`roadmap.md`](roadmap.md).

## Toolchain

- **Cyrius pin**: `6.4.43` (in `cyrius.cyml [package].cyrius`)
- **`lib/`**: materialized by `cyrius deps` — real directory, never a
  symlink, never committed.

## Source (12 `[lib]` modules, dependency order)

| Module | Family | Surface |
|--------|--------|---------|
| `src/drishti.cyr` | core `dr_` | error record + code bands, `drishti_version()` → 100, format sniff |
| `src/bits.cyr` | core `dr_` | MSB-first bitreader/bitwriter, leb128/uvlc/ue/se read + write, sticky-latch seam |
| `src/ivf.cyr` | core `dr_ivf_` | IVF read/write (AV01/VP80/VP90) |
| `src/av1_obu.cyr` | `av1_` | OBU parse/walk/write |
| `src/av1_seq.cyr` | `av1_` | sequence_header_obu → Av1Seq |
| `src/h264_nal.cyr` | `h264_` | Annex-B scan, NAL hdr, EPB strip/insert, composer |
| `src/h264_ps.cyr` | `h264_` | SPS (full, incl. High branch + crop) / PPS (minimal) |
| `src/h265_nal.cyr` | `h265_` | strict Annex-B scan, 2-byte NAL hdr, RBSP extract |
| `src/h265_ps.cyr` | `h265_` | PTL, VPS/SPS/PPS + crop math + bomb guard |
| `src/vpx_bool.cyr` | `vbool_` | RFC 6386 boolean coder, decoder + encoder |
| `src/vp8.cyr` | `vp8_` | frame tag/keyframe header parse + builder + writer |
| `src/vp9.cyr` | `vp9_` | uncompressed header parse |

`src/main.cyr` is the include-wiring root (no code).

## Gates (all green, 2026-07-10)

- `make build` — smoke exercises one real operation per family, exit 0
- `make test` — 7 suites / **2,220 assertions**: drishti 51 · bits 206
  · ivf 889 · av1 185 · h264 326 · h265 276 · vpx 287
- `make fuzz` — **1,140 assertions**, no crash/hang, all exits known codes
- `make bench` — bitreader/VLC numbers in CHANGELOG
- `cyrius distlib` — `dist/drishti.cyr` (~4.5k lines, 266 exported
  fns), verified compile-clean + functionally correct via a temp
  consumer program

## Dependencies

- stdlib only: string, fmt, alloc, io, vec, str, syscalls, assert, bench
- No external crate deps. No C. No FFI.

## Consumers

None yet — registered targets: tarang, tazama, jalwa, aethersafta
(they arrive at the families' decode milestones).

## In-flight / next

The **0.7.x AV1 arc** opens next — frame-header OBU → entropy decoder →
intra still-picture decode (first pixels). Full per-codec arc plan +
the audit/freeze arcs in [`roadmap.md`](roadmap.md). Nothing else in
flight.
