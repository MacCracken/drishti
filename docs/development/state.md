# drishti — Current State

> Refreshed every release. CLAUDE.md is preferences/process/procedures
> (durable); this file is **state** (volatile) — versions, counts,
> sizes, in-flight work.

## Version

**0.7.19** — cut 2026-07-11, not yet tagged (user's git). The **0.7.x
AV1 arc** opens the **block/partition decode** (the last stretch to a
decoded keyframe) with its first bite: the default non-coefficient CDF
tables (`av1_noncoeffcdf.cyr` — 19 tables, 1,622 entries) that every
mode-info / tx / partition read will consume, on top of the complete
coefficient decode (0.7.13-0.7.18). The remaining distance to 1.0 is the
rest of the per-codec completion arcs (0.7.x AV1 → 0.10.x VP8/VP9) +
audit (0.11.x) + freeze/docs (0.12.x). See
[`CHANGELOG.md`](../../CHANGELOG.md) + [`roadmap.md`](roadmap.md).

## Toolchain

- **Cyrius pin**: `6.4.46` (in `cyrius.cyml [package].cyrius`) — min
  version for the arithmetic-shift operator `>>>`. The pin is the
  *minimum*; a newer installed `cycc` (currently **6.4.49**) compiles
  clean and only emits a harmless drift note. **Set
  `CYRIUS_NO_WARN_PIN_DRIFT=1`** in the env for clean build/test/lint
  output. Bump the pin only when a new toolchain feature is actually used
  (none needed so far past 6.4.46).
- **`lib/`**: materialized by `cyrius deps` — real directory, never a
  symlink, never committed.

## Source (24 `[lib]` modules, dependency order)

| Module | Family | Surface |
|--------|--------|---------|
| `src/drishti.cyr` | core `dr_` | error record + code bands, `drishti_version()` → 719, format sniff |
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
| `src/av1_coeffs.cyr` | `av1_` | coeffs() reading loop (5.11.39) — decode + inverse encode + txb_skip/dc_sign/txSzCtx contexts + the adaptive per-tile CDF context (av1_ccdf_*); both CDF modes |
| `src/av1_noncoeffcdf.cyr` | `av1_` | default non-coeff CDF tables (intra keyframe) — partition/skip/y-mode/uv-mode/cfl/angle/filter-intra/tx-size/tx-type (1,622) + accessors + av1_ncdf_new |
| `src/h264_nal.cyr` | `h264_` | Annex-B scan, NAL hdr, EPB strip/insert, composer |
| `src/h264_ps.cyr` | `h264_` | SPS (full, incl. High branch + crop) / PPS (minimal) |
| `src/h265_nal.cyr` | `h265_` | strict Annex-B scan, 2-byte NAL hdr, RBSP extract |
| `src/h265_ps.cyr` | `h265_` | PTL, VPS/SPS/PPS + crop math + bomb guard |
| `src/vpx_bool.cyr` | `vbool_` | RFC 6386 boolean coder, decoder + encoder |
| `src/vp8.cyr` | `vp8_` | frame tag/keyframe header parse + builder + writer |
| `src/vp9.cyr` | `vp9_` | uncompressed header parse |

`src/main.cyr` is the include-wiring root (no code).

## Gates (all green, 2026-07-11)

- `make build` — smoke exercises one real operation per family, exit 0
- `make test` — 19 suites / **19,156 assertions**: drishti 51 · bits
  1,211 · ivf 889 · frame 73 · av1 185 · av1_frame 140 · av1_symbol 280 ·
  av1_itx 160 · av1_intra 202 · av1_quant 1,569 · av1_recon 4,209 ·
  av1_scan 137 · av1_coeff 47 · av1_coeffcdf 3,450 · av1_coeffs 3,844 ·
  av1_noncoeffcdf 1,820 · h264 326 · h265 276 · vpx 287
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
  cross-check → 3 clean + 1 real finding, an unbounded golomb loop, fixed),
  and the adaptive coeff-CDF context (3 slices: copy/accessor offsets +
  refactor + adaptation lockstep + libaom → all clean), and the default
  non-coeff CDFs (3 slices: per-table diff of all 19 tables + accessor
  offsets + libaom entropymode cross-check → all clean)

## Dependencies

- stdlib only: string, fmt, alloc, io, vec, str, syscalls, assert, bench
- No external crate deps. No C. No FFI.

## Consumers

None yet — registered targets: tarang, tazama, jalwa, aethersafta
(they arrive at the families' decode milestones).

## In-flight / next

The **0.7.x AV1 arc** is inside the **intra still-picture decode
MILESTONE**. Per-release history is in [`CHANGELOG.md`](../../CHANGELOG.md);
the current picture:

**Done — every AV1 decode primitive is in:** OBU/sequence/frame-header
parse; the multi-symbol adaptive-CDF arithmetic coder (dec + enc); the
**complete intra-prediction layer** (7.11.2 + 7.11.5 — DC/PAETH/SMOOTH,
full directional + edge filter/upsample, filter-intra, chroma-from-luma);
the inverse transform (7.13); dequantization (7.12.2) and the reconstruct
glue (7.12.3) — **first pixels** from a coefficient array; and the
**complete coefficient decode** — scan orders (5.11.41), level contexts
(8.3.2), all 7 default coeff CDF families, and the `coeffs()` reading loop
(5.11.39, decode + inverse encode) with an adaptive per-tile CDF context,
so a transform block decodes **end-to-end in both `disable_cdf_update`
modes** (round-trip tested).

**Now open — the block/partition decode** (a 7-bite, leaf-to-root
sequence toward a decoded keyframe, mapped by a multi-agent scoping pass;
scope + tables per bite are in the review transcript / CHANGELOG):

1. **non-coeff CDF tables** — `av1_noncoeffcdf.cyr` **[done 0.7.19]**
2. **mode-info reads** — `intra_frame_mode_info` intra branch: `read_skip`,
   `intra_frame_y_mode` (above/left neighbour-mode ctx), `uv_mode`
   (CfL-allowed vs not), `read_cfl_alphas`, `angle_delta` (directional),
   `filter_intra` use/mode. Consumes the 0.7.19 CDFs (`av1_ncdf_*`).
   Round-trip-testable via the symbol encoder. Needs block-size tables
   (Block_Width/Height, Mi_Width/Height_Log2, Intra_Mode_Context) + the
   YModes/UVModes neighbour grids. **← NEXT BITE.**
3. **tx-size reads** — `read_tx_size` / `tx_depth` symbol + its ctx; tables
   Max_Tx_Size_Rect / Max_Tx_Depth / Split_Tx_Size; fills InterTxSizes.
4. **`compute_tx_type`** spliced INTO `av1_coeffs_decode`/`_encode`
   (between all_zero and get_scan) — retires the `PlaneTxType` caller-input;
   reads `intra_tx_type` (Set1/Set2 CDFs) + `get_tx_set` + `Mode_To_Txfm`.
   Trickiest seam — must keep the coeffs round-trip green.
5. **residual driver** — `residual()`/`transform_block()` (5.11.34/35):
   per tx block, predict_intra → coeffs() → reconstruct(); manages
   BlockDecoded availability + the level-context strips + CfL MaxLumaW/H.
6. **`decode_partition` tree + `decode_block`** (5.11.4/5.11.5) — the
   partition symbol/ctx + split_or_horz/vert edge CDFs + Partition_Subsize;
   writes the MiSizes grid.
7. **tile/frame loop** (`decode_tile`/tile_group) — clear_above/left,
   the SB loop, init the CDF contexts (av1_ncdf_new + av1_ccdf_new), drive
   into `DrFrame` = **first decoded keyframe**.

Deferred (feature-gated, after the baseline keyframe): 128×128 SBs,
palette, intrabc, segmentation, active delta-q/lf, multi-tile, and the
loop-filter/CDEF/LR/superres + frame-end CDF save/average wrapup.

Full per-codec arc plan + the audit/freeze arcs in
[`roadmap.md`](roadmap.md). Nothing else in flight.

## Working rhythm (handoff)

Each bite = **one coherent subsystem per patch release**: spec-derive
(cite sections inline, cross-check ≥2 impls) → implement in a
family-prefixed flat module (wire into `src/main.cyr` **and**
`cyrius.cyml [lib].modules` in dependency order) → hand-tested
known-answers (round-trip via the symbol encoder for entropy-coded
paths) → adversarial multi-agent spec-review → update docs (CHANGELOG,
this file, roadmap, sources, README) → bump `VERSION` +
`drishti_version()` + `tests/drishti.tcyr` → regenerate `dist/` → run the
full gate. **The user handles all git (commit + push) and cuts each
release** — leave the tree all-green. Large tables (Q/scan/CDF): extract
from the spec markdown, generate the Cyrius fill code, verify with a
weighted checksum + a structural sweep + the adversarial per-value diff
(never hand-transcribe thousands of values). Reference material for the
block-decode arc lives in the scratchpad spec files
(`10.additional.tables.md` etc., re-fetch from the AV1-spec repo if the
scratchpad was cleaned).
