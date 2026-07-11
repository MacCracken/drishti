# drishti — Current State

> Refreshed every release. CLAUDE.md is preferences/process/procedures
> (durable); this file is **state** (volatile) — versions, counts,
> sizes, in-flight work.

## Version

**0.7.17** — cut 2026-07-11, not yet tagged (user's git). The **0.7.x
AV1 arc** reaches a key milestone: the `coeffs()` reading loop (5.11.39)
in the new `av1_coeffs.cyr` module — so **a transform block now decodes
end-to-end** (encoded bytes → `Quant[]`, round-trip tested against the
inverse encode). It ties together the scans (0.7.13), level contexts
(0.7.14), CDFs (0.7.15-0.7.16), and the symbol coder, plus the remaining
txb_skip/dc_sign/txSzCtx contexts. The remaining distance to 1.0 is the
rest of the per-codec completion arcs (0.7.x AV1 → 0.10.x VP8/VP9) +
audit (0.11.x) + freeze/docs (0.12.x). See
[`CHANGELOG.md`](../../CHANGELOG.md) + [`roadmap.md`](roadmap.md).

## Toolchain

- **Cyrius pin**: `6.4.46` (in `cyrius.cyml [package].cyrius`) — min
  version for the arithmetic-shift operator `>>>`. The pin is the
  *minimum*; a newer installed `cycc` (e.g. 6.4.47) compiles clean and
  only emits a harmless drift note (`CYRIUS_NO_WARN_PIN_DRIFT=1` silences
  it) — bump the pin only when a new toolchain feature is actually used.
- **`lib/`**: materialized by `cyrius deps` — real directory, never a
  symlink, never committed.

## Source (23 `[lib]` modules, dependency order)

| Module | Family | Surface |
|--------|--------|---------|
| `src/drishti.cyr` | core `dr_` | error record + code bands, `drishti_version()` → 717, format sniff |
| `src/bits.cyr` | core `dr_` | MSB-first bitreader/bitwriter, leb128/uvlc/ue/se + su/ns read + write, FloorLog2, bit-skip, sticky-latch seam |
| `src/ivf.cyr` | core `dr_ivf_` | IVF read/write (AV01/VP80/VP90) |
| `src/frame.cyr` | core `dr_frame_` | shared YUV planar-frame buffer (DrFrame): 1/3 planes, 16-bit samples, subsampling, border, dr_clip1 |
| `src/av1_obu.cyr` | `av1_` | OBU parse/walk/write |
| `src/av1_seq.cyr` | `av1_` | sequence_header_obu → full-fidelity Av1Seq |
| `src/av1_frame.cyr` | `av1_` | uncompressed frame header (5.9.2, all frame types) + ref-frame state machine (Av1FrameHeader / Av1RefState) |
| `src/av1_symbol.cyr` | `av1_` | multi-symbol adaptive-CDF arithmetic coder (spec 8.2) — decoder + encoder (Av1SymDec / Av1SymEnc) |
| `src/av1_itx.cyr` | `av1_` | inverse transform block (spec 7.13) — DCT 4-64 / ADST 4-16 / identity / WHT + 2D driver |
| `src/av1_intra.cyr` | `av1_` | intra prediction (spec 7.11.2 + 7.11.5) — predict_intra + DC/PAETH/SMOOTH×3 + full directional (edge filter/upsample) + recursive filter-intra (7.11.2.3) + chroma-from-luma (7.11.5) |
| `src/av1_quant.cyr` | `av1_` | dequantization (spec 7.12.2) — Dc/Ac Qlookup tables (8/10/12-bit) + dc_q/ac_q/get_qindex/get_dc_quant/get_ac_quant |
| `src/av1_recon.cyr` | `av1_` | reconstruct process (spec 7.12.3) — dequant + dqDenom + FLIPADST flip + residual-add glue (av1_reconstruct) |
| `src/av1_scan.cyr` | `av1_` | coefficient scan orders (spec 5.11.41) — 32 Default/Mrow/Mcol scan tables + get_scan + scan_size |
| `src/av1_coeff.cyr` | `av1_` | coefficient level contexts (spec 8.3.2) — get_tx_class / get_coeff_base_ctx / get_br_ctx + offset tables |
| `src/av1_coeffcdf.cyr` | `av1_` | default coefficient CDF tables (8.3.2) — all 7 families: txb_skip / eob_pt / eob_extra / dc_sign / coeff_base_eob / coeff_base / coeff_br + accessors |
| `src/av1_coeffs.cyr` | `av1_` | coeffs() reading loop (5.11.39) — decode + inverse encode + txb_skip/dc_sign/txSzCtx contexts (disable_cdf_update mode) |
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
- `make test` — 18 suites / **13,920 assertions**: drishti 51 · bits
  1,211 · ivf 889 · frame 73 · av1 185 · av1_frame 140 · av1_symbol 280 ·
  av1_itx 160 · av1_intra 202 · av1_quant 1,569 · av1_recon 4,209 ·
  av1_scan 137 · av1_coeff 47 · av1_coeffcdf 3,450 · av1_coeffs 428 ·
  h264 326 · h265 276 · vpx 287
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
  multi-source cross-check → all clean), and dequantization (5 slices:
  per-value Dc/Ac table diffs + 7.12.2 logic + libaom cross-check → all
  clean; one refuted robustness note prompted a proactive depth-clamp
  backstop), and the reconstruct glue (5 slices: dequant step + dqDenom/
  flip/add + integration/safety + libaom multi-source + independent
  known-answer recompute → all clean, no defects), and the coefficient
  scan orders (4 slices: per-value default/mrow/mcol table diffs +
  get_scan selection + libaom cross-check → all clean), and the
  coefficient level contexts (4 slices: coeff_base/coeff_br logic +
  Coeff_Base_Ctx_Offset diff + libaom txb_common cross-check +
  known-answer recompute → all clean), and the default coefficient CDFs
  (7 slices across two cuts: per-family table diffs of all 15,996 values +
  accessor arithmetic + format/libaom token_cdfs cross-check → all clean),
  and the coeffs() reading loop (4 slices: decode conformance + encode
  symmetry + per-symbol CDF/context selection + libaom decodetxb
  cross-check → 3 clean + 1 real finding, an unbounded golomb loop, fixed)

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
filter-intra prediction (0.7.9), and chroma-from-luma (0.7.10). The
**AV1 intra-prediction layer (7.11.2 + 7.11.5) is complete**, as is the
dequant + reconstruct path: dequantization (7.12.2, 0.7.11) and the
reconstruct glue (7.12.3, 0.7.12) now turn a coefficient array +
prediction into reconstructed pixels — **first pixels**. The
**coefficient decode** is underway: the scan-order layer (5.11.41,
0.7.13) and the level-context helpers (8.3.2, 0.7.14, this cut) are in.
The `coeffs()` reading loop (5.11.39) is **in** (0.7.17) — a transform
block decodes end-to-end (round-trip tested). Remaining toward a decoded
keyframe: the **block/partition decode** — intra-mode + uv-mode + CfL-alpha
reads and their CDFs, `compute_tx_type` (so `PlaneTxType` stops being a
caller input), the adaptive per-tile CDF context (so decode works with
`disable_cdf_update = 0`, the common case), the partition tree, and the
tile/frame wiring that drives `coeffs()` + predict + reconstruct per
block. Full per-codec arc plan + the audit/freeze arcs in
[`roadmap.md`](roadmap.md). Nothing else in flight.
