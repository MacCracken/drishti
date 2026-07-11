# drishti — Current State

> Refreshed every release. CLAUDE.md is preferences/process/procedures
> (durable); this file is **state** (volatile) — versions, counts,
> sizes, in-flight work.

## Version

**0.7.10** — cut 2026-07-10, not yet tagged (user's git). The **0.7.x
AV1 arc** continues through the intra still-picture decode milestone:
chroma-from-luma prediction (7.11.5) in `av1_intra.cyr` completes the AV1
intra-prediction layer, on top of 0.7.9's filter-intra, 0.7.8's
directional prediction, and 0.7.6's non-directional modes. The remaining
distance to 1.0 is the rest of the per-codec completion arcs (0.7.x AV1
→ 0.10.x VP8/VP9) + audit (0.11.x) + freeze/docs (0.12.x). See
[`CHANGELOG.md`](../../CHANGELOG.md) + [`roadmap.md`](roadmap.md).

## Toolchain

- **Cyrius pin**: `6.4.46` (in `cyrius.cyml [package].cyrius`) — min
  version for the arithmetic-shift operator `>>>`. The pin is the
  *minimum*; a newer installed `cycc` (e.g. 6.4.47) compiles clean and
  only emits a harmless drift note (`CYRIUS_NO_WARN_PIN_DRIFT=1` silences
  it) — bump the pin only when a new toolchain feature is actually used.
- **`lib/`**: materialized by `cyrius deps` — real directory, never a
  symlink, never committed.

## Source (17 `[lib]` modules, dependency order)

| Module | Family | Surface |
|--------|--------|---------|
| `src/drishti.cyr` | core `dr_` | error record + code bands, `drishti_version()` → 710, format sniff |
| `src/bits.cyr` | core `dr_` | MSB-first bitreader/bitwriter, leb128/uvlc/ue/se + su/ns read + write, FloorLog2, bit-skip, sticky-latch seam |
| `src/ivf.cyr` | core `dr_ivf_` | IVF read/write (AV01/VP80/VP90) |
| `src/frame.cyr` | core `dr_frame_` | shared YUV planar-frame buffer (DrFrame): 1/3 planes, 16-bit samples, subsampling, border, dr_clip1 |
| `src/av1_obu.cyr` | `av1_` | OBU parse/walk/write |
| `src/av1_seq.cyr` | `av1_` | sequence_header_obu → full-fidelity Av1Seq |
| `src/av1_frame.cyr` | `av1_` | uncompressed frame header (5.9.2, all frame types) + ref-frame state machine (Av1FrameHeader / Av1RefState) |
| `src/av1_symbol.cyr` | `av1_` | multi-symbol adaptive-CDF arithmetic coder (spec 8.2) — decoder + encoder (Av1SymDec / Av1SymEnc) |
| `src/av1_itx.cyr` | `av1_` | inverse transform block (spec 7.13) — DCT 4-64 / ADST 4-16 / identity / WHT + 2D driver |
| `src/av1_intra.cyr` | `av1_` | intra prediction (spec 7.11.2 + 7.11.5) — predict_intra + DC/PAETH/SMOOTH×3 + full directional (edge filter/upsample) + recursive filter-intra (7.11.2.3) + chroma-from-luma (7.11.5) |
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
- `make test` — 12 suites / **4,080 assertions**: drishti 51 · bits 1,211
  · ivf 889 · frame 73 · av1 185 · av1_frame 140 · av1_symbol 280 ·
  av1_itx 160 · av1_intra 202 · h264 326 · h265 276 · vpx 287
- `make fuzz` — **1,140 assertions**, no crash/hang, all exits known codes
- `make bench` — bitreader/VLC numbers in CHANGELOG
- `make fmt-check` — clean; `make lint` — clean for the AV1 modules.
  Three pre-existing deferrals surfaced by toolchain drift are tracked
  separately: `h264_ps.cyr:59`, `vpx_bool.cyr:104`, and a >120-char line
  in `tests/av1_frame.tcyr:55` (none touched by this cut)
- `cyrius distlib` — `dist/drishti.cyr` verified compile-clean via a
  consumer-style build
- **adversarial spec reviews** — field-by-field cross-checks against the
  AV1 spec markdown: the frame-header parser (12 slices → 1 confirmed
  critical, the tile-count overflow, fixed + regressed), the symbol
  coder (5 slices → clean), the inverse transform (5 slices → clean), and
  intra prediction (non-directional 4 slices + directional 4 slices +
  filter-intra 4 slices + chroma-from-luma 5 slices incl. a libaom/dav1d
  multi-source cross-check → all clean)

## Dependencies

- stdlib only: string, fmt, alloc, io, vec, str, syscalls, assert, bench
- No external crate deps. No C. No FFI.

## Consumers

None yet — registered targets: tarang, tazama, jalwa, aethersafta
(they arrive at the families' decode milestones).

## In-flight / next

The **0.7.x AV1 arc** is underway, now inside the **intra still-picture
decode MILESTONE**. Done: the frame-header OBU (0.7.1), the
entropy/symbol decoder + encoder (0.7.2), the shared YUV frame buffer
(0.7.3), the inverse transform block (0.7.4), the arithmetic-shift fix
(0.7.5), non-directional intra prediction (0.7.6), the `>>>` adoption
(0.7.7), the full directional intra prediction (0.7.8), recursive
filter-intra prediction (0.7.9), and chroma-from-luma (0.7.10, this cut).
The **AV1 intra-prediction layer (7.11.2 + 7.11.5) is now complete.**
Remaining milestone sub-bites: coefficient decode (`coeff()` syntax +
the default CDF tables, consuming the symbol decoder) → the
partition/block reconstruction glue that emits first pixels. Full
per-codec arc plan + the audit/freeze arcs in [`roadmap.md`](roadmap.md).
Nothing else in flight.
