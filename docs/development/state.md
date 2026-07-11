# drishti — Current State

> Refreshed every release. CLAUDE.md is preferences/process/procedures
> (durable); this file is **state** (volatile) — versions, counts,
> sizes, in-flight work.

## Version

**0.7.1** — cut 2026-07-10, not yet tagged (user's git). The **0.7.x
AV1 arc** has opened: the full uncompressed frame header (5.9.2, all
frame types, cursor-true) + the reference-frame state machine, on top of
the 0.7.0 baseline (shared core + all four families' bitstream/
container/header layers). The remaining distance to 1.0 is the rest of
the per-codec completion arcs (0.7.x AV1 → 0.10.x VP8/VP9) + audit
(0.11.x) + freeze/docs (0.12.x). See [`CHANGELOG.md`](../../CHANGELOG.md)
+ [`roadmap.md`](roadmap.md).

## Toolchain

- **Cyrius pin**: `6.4.43` (in `cyrius.cyml [package].cyrius`)
- **`lib/`**: materialized by `cyrius deps` — real directory, never a
  symlink, never committed.

## Source (13 `[lib]` modules, dependency order)

| Module | Family | Surface |
|--------|--------|---------|
| `src/drishti.cyr` | core `dr_` | error record + code bands, `drishti_version()` → 701, format sniff |
| `src/bits.cyr` | core `dr_` | MSB-first bitreader/bitwriter, leb128/uvlc/ue/se + su/ns read + write, FloorLog2, sticky-latch seam |
| `src/ivf.cyr` | core `dr_ivf_` | IVF read/write (AV01/VP80/VP90) |
| `src/av1_obu.cyr` | `av1_` | OBU parse/walk/write |
| `src/av1_seq.cyr` | `av1_` | sequence_header_obu → full-fidelity Av1Seq |
| `src/av1_frame.cyr` | `av1_` | uncompressed frame header (5.9.2, all frame types) + ref-frame state machine (Av1FrameHeader / Av1RefState) |
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
- `make test` — 8 suites / **3,349 assertions**: drishti 51 · bits 1,201
  · ivf 889 · av1 185 · av1_frame 134 · h264 326 · h265 276 · vpx 287
- `make fuzz` — **1,140 assertions**, no crash/hang, all exits known codes
- `make bench` — bitreader/VLC numbers in CHANGELOG
- `make lint` / `make fmt-check` — clean for the AV1 modules (a
  pre-existing deferral in `h264_ps.cyr`, surfaced by toolchain drift,
  is tracked separately)
- `cyrius distlib` — `dist/drishti.cyr` (~6.6k lines, 454 exported
  fns), verified compile-clean via a consumer-style build
- **adversarial spec review** — a 12-agent field-by-field cross-check of
  the frame-header parser against the AV1 spec markdown: 11 slices clean,
  1 confirmed critical (the tile-count overflow, now fixed + regressed)

## Dependencies

- stdlib only: string, fmt, alloc, io, vec, str, syscalls, assert, bench
- No external crate deps. No C. No FFI.

## Consumers

None yet — registered targets: tarang, tazama, jalwa, aethersafta
(they arrive at the families' decode milestones).

## In-flight / next

The **0.7.x AV1 arc** is underway. Done: the frame-header OBU
(uncompressed_header + ref-frame state machine, this cut). Next: the
**entropy decoder** — the multi-symbol adaptive-CDF arithmetic decoder
(daala lineage) that every tile decode needs — then intra still-picture
decode (first pixels). Full per-codec arc plan + the audit/freeze arcs
in [`roadmap.md`](roadmap.md). Nothing else in flight.
