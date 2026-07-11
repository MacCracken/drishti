# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.7.16] - 2026-07-10

Completes the AV1 default coefficient CDF tables with the two largest
families — `Default_Coeff_Base_Cdf` (8,400 entries) and
`Default_Coeff_Br_Cdf` (4,200) — extending `src/av1_coeffcdf.cyr`. A
3-agent adversarial review diffed all 12,600 values against the spec and
cross-checked libaom `token_cdfs.h` with no defects. **13,492 suite
assertions + 1,140 fuzz assertions, all green.**

### Added
- **AV1 default `coeff_base` + `coeff_br` CDF tables**
  (`src/av1_coeffcdf.cyr`): `Default_Coeff_Base_Cdf[4][5][2][42][5]` and
  `Default_Coeff_Br_Cdf[4][5][2][21][5]`, each in its own lazily-built
  blob with a CDF accessor (`av1_coeff_base_cdf` /
  `av1_coeff_br_cdf`); the `coeff_br` accessor takes the
  `Min(txSzCtx, TX_32X32)`-clamped size context per the spec. With these,
  **all seven default coefficient CDF families are in** — the complete
  initial adaptive-CDF state the `coeffs()` decode needs. 3,450 assertions
  (up from 919): per-family weighted checksums, a structural sweep
  validating every CDF via its accessor, known values, and offset
  arithmetic.

### Notes
- `drishti_version()` → 716. With the scans (0.7.13), level contexts
  (0.7.14), and now the full CDF set, the next bite is the `coeffs()`
  reading loop itself (plus the `txb_skip`/`dc_sign` neighbour-array
  contexts and the tx-type decode) — where a transform block decodes
  end-to-end from the bitstream into `Quant[]`.

## [0.7.15] - 2026-07-10

Continues the AV1 coefficient decode with the first batch of default
coefficient CDF tables in a new `src/av1_coeffcdf.cyr` module — the
initial adaptive-CDF values the `coeffs()` loop loads per quantizer
bucket. A 3-agent adversarial review (per-family table diffs evaluating
the `128 * x` products, accessor-index arithmetic, and a format +
libaom `token_cdfs.h` cross-check) confirmed every value with no defects.
**10,961 suite assertions + 1,140 fuzz assertions, all green.**

### Added
- **AV1 default coefficient CDF tables — smaller families**
  (`src/av1_coeffcdf.cyr`, new flat module): `Default_Txb_Skip_Cdf`,
  `Default_Eob_Pt_{16,32,64,128,256,512,1024}_Cdf`, `Default_Eob_Extra_Cdf`,
  `Default_Dc_Sign_Cdf`, and `Default_Coeff_Base_Eob_Cdf` (3,396 entries
  across the 4 `COEFF_CDF_Q_CTXS` quantizer buckets), in one lazily-built
  blob with per-family CDF accessors. Values are stored in the symbol
  coder's format (N cumulative freqs ending in 32768, then a 0 adaptation
  count), so they load straight into the adaptive-CDF decoder. Extracted
  from the spec (with the `128 * x` products evaluated) and validated —
  every CDF is non-decreasing, ends in 32768, and has a 0 count. 919
  assertions: a position-weighted blob checksum, a structural sweep
  validating every CDF via its accessor, known values, and the accessor
  offset arithmetic.

### Notes
- `drishti_version()` → 715. `Default_Coeff_Base_Cdf` and
  `Default_Coeff_Br_Cdf` (the two largest families) follow in the next CDF
  sub-bites, then the `coeffs()` reading loop.

## [0.7.14] - 2026-07-10

Continues the AV1 coefficient decode with the level-context layer (spec
8.3.2 CDF selection) in a new `src/av1_coeff.cyr` module — the contexts
that pick each coefficient symbol's CDF. A 4-agent adversarial review
(coeff_base logic, coeff_br/tx_class logic, table diffs + a libaom
`txb_common` cross-check, and an independent recompute of every
hand-traced known-answer) confirmed the logic and tables with no defects.
**10,042 suite assertions + 1,140 fuzz assertions, all green.**

### Added
- **AV1 coefficient level contexts** (`src/av1_coeff.cyr`, new flat
  module): `av1_get_tx_class` (TX_CLASS_2D/HORIZ/VERT), `av1_eob_pt_ctx`,
  `av1_get_coeff_base_ctx` (the `coeff_base` / `coeff_base_eob` context —
  the neighbour-magnitude template over `Quant[]`, the `Coeff_Base_Ctx_Offset`
  position offset, and the EOB variant), and `av1_get_br_ctx` (the
  `coeff_br` context), plus their offset tables (`Coeff_Base_Ctx_Offset`
  [19][5][5], `Coeff_Base_Pos_Ctx_Offset`, `Sig_Ref_Diff_Offset`,
  `Mag_Ref_Offset_With_Tx_Class`, `Adjusted_Tx_Size`). `tx_type` is a
  caller input; the `txb_skip`/`dc_sign` contexts (which need the per-tile
  neighbour arrays) are deferred to the reading-loop bite. 47 assertions:
  the context functions pinned by hand-traced known-answers on constructed
  `Quant[]` arrays (2D / VERT / HORIZ paths, the EOB variants), and the
  offset tables by a weighted checksum + spot values.

### Notes
- `drishti_version()` → 714. Next: the default coefficient CDF tables +
  the `coeffs()` reading loop (with the `txb_skip`/`dc_sign` contexts)
  that walks the scans, consumes the symbol decoder, and fills `Quant[]`.

## [0.7.13] - 2026-07-10

Opens the AV1 **coefficient decode** with the scan-order layer (spec
5.11.41) in a new `src/av1_scan.cyr` module — the read order the
`coeffs()` decode will walk. The 32 scan tables were extracted from the
spec, each validated as a permutation, and a 4-agent adversarial review
(per-value default/mrow/mcol table diffs, `get_scan` selection logic,
libaom cross-check) confirmed every value and selection with no defects.
**9,995 suite assertions + 1,140 fuzz assertions, all green.**

### Added
- **AV1 coefficient scan orders** (`src/av1_scan.cyr`, new flat module):
  the 32 scan tables (14 `Default_Scan_*` + 9 `Mrow_Scan_*` + 9
  `Mcol_Scan_*`, 4,912 entries) in one lazily-built blob, `av1_get_scan`
  (5.11.41 — selects a scan from transform size + `PlaneTxType`, incl. the
  `TX_16X64`/`TX_64X16`→16x32/32x16 and 64x64-class→32x32 clamps and the
  `V_*`/`H_*` mrow/mcol paths via per-TxSize offset tables), and
  `av1_scan_size` (the scan length `Min(32,w)·Min(32,h)`). 137 assertions:
  a position-weighted checksum over the whole 4,912-entry blob
  (order-sensitive), a permutation check on every selected scan (each is a
  bijection over `0..len-1` starting at DC=0), specific known scan values,
  and the full `get_scan` selection matrix.

### Notes
- `drishti_version()` → 713. Next in the coefficient decode: the txb
  context helpers + the default coefficient CDF tables, then the
  `coeffs()` reading loop that walks these scans to fill `Quant[]`.

## [0.7.12] - 2026-07-10

**First pixels.** The reconstruct process (spec 7.12.3) in a new
`src/av1_recon.cyr` module ties the existing pieces together —
dequantize → 2D inverse transform → add the residual onto the
prediction — so a block of quantized coefficients plus a prediction now
produces reconstructed samples. Cross-checked against libaom and reviewed
by a 5-agent adversarial workflow (dequant step, dqDenom/flip/add,
integration + memory safety, libaom multi-source, independent
known-answer recompute — all clean, no defects). **9,858 suite
assertions + 1,140 fuzz assertions, all green.**

### Added
- **AV1 reconstruct process** (`src/av1_recon.cyr`, new flat module):
  `av1_reconstruct` runs the 7.12.3 pipeline — per-coefficient
  dequantization (`av1_dequant_coeff`: `dq = Quant·q`, the 24-bit
  magnitude mask, the `dqDenom` divide for the large transforms, the
  `±2^(7+BitDepth)` clamp), the 2D inverse transform (reusing
  `av1_inverse_transform_2d`), and the `FLIPADST` up/down + left/right
  flipped residual add with `Clip1`. Helpers `av1_dq_denom` (7.12.3 size
  categories) and `av1_recon_flip_ud`/`av1_recon_flip_lr`. The quantizer
  matrix path (`using_qmatrix`) is deferred (`q2 == q`); `q_dc`/`q_ac`
  and the `Quant[]` array are caller inputs until coefficient decode.
  4,209 assertions: the dequant arithmetic (mask, clip, `dqDenom`, signs),
  the `dqDenom`/flip selection matrices, and the **full pipeline** —
  reusing the inverse transform's hand-verified DC/IDTX/WHT vectors, plus
  the transform-as-oracle for the flip placement and a 64×64
  `dqDenom=4`/stride path (all 4,096 samples matched).

### Notes
- `drishti_version()` → 712. With prediction (7.11) + dequant (7.12.2) +
  reconstruct (7.12.3) all in, the remaining path to a decoded keyframe
  is the `coeffs()` entropy decode (scan + CDF + context) that fills
  `Quant[]`, then the partition/block wiring that drives these per block.

## [0.7.11] - 2026-07-10

Opens the AV1 **reconstruction** milestone with the dequantization layer
(spec 7.12.2) in a new `src/av1_quant.cyr` module — the first step from
parsed coefficients toward first pixels. The `Dc_Qlookup`/`Ac_Qlookup`
tables were extracted directly from the spec and cross-checked against
libaom `quant_common.c`; a 5-agent adversarial review (per-value Dc/Ac
table diffs, 7.12.2 logic, libaom multi-source, edge cases) confirmed
every value and returned no defects. **5,649 suite assertions + 1,140
fuzz assertions, all green.**

### Added
- **AV1 dequantization** (`src/av1_quant.cyr`, new flat module): the
  `Dc_Qlookup[3][256]` / `Ac_Qlookup[3][256]` quantizer tables (all three
  8/10/12-bit rows, lazy-init) + `av1_dc_q` / `av1_ac_q` (the
  `Q_lookup[(BitDepth-8)>>1][Clip3(0,255,b)]` lookups), `av1_get_qindex`
  (7.12.2 — the base / delta-q / segment-ALT_Q selection), and
  `av1_get_dc_quant` / `av1_get_ac_quant` (adding the plane's
  `DeltaQ*Dc`/`DeltaQ*Ac`). The per-block qindex/segment/delta state are
  caller inputs until block decode lands. The depth index is clamped to
  0..2 as an out-of-bounds backstop. 1,569 assertions: spec-value anchors
  across all three bit-depths, a **full-table checksum** (every one of the
  2×768 entries summed through the real lookup path), per-row
  monotonicity, the `get_qindex` branch matrix, and the delta/clip cases.

### Notes
- `drishti_version()` → 711. Next: the reconstruct glue (7.12.3) —
  dequant → inverse transform → residual add — which turns a coefficient
  array into reconstructed pixels; then the `coeffs()` entropy decode.

## [0.7.10] - 2026-07-10

Adds AV1 chroma-from-luma (CfL) prediction — the sixth (and final)
intra-prediction milestone sub-bite. Derived verbatim from spec 7.11.5,
cross-checked against libaom `cfl.c` + dav1d `ipred`, and reviewed by a
5-agent adversarial workflow (spec conformance ×2, multi-source,
memory-safety/overflow, independent known-answer recompute — all clean).
**4,080 suite assertions + 1,140 fuzz assertions, all green.**

### Added
- **AV1 chroma-from-luma prediction** (`src/av1_intra.cyr`):
  `av1_predict_chroma_from_luma` (7.11.5) forms chroma as
  `DC(chroma) + alpha·AC(luma)` — the reconstructed luma of the block is
  subsampled to the chroma grid (summed over the subsampling footprint,
  left-shifted to 3 fractional bits), its block mean subtracted to leave
  the AC, scaled by the signed CfL alpha with a 6-bit signed round
  (`Round2Signed`), and added onto the DC prediction already written by a
  prior `predict_intra(DC_PRED)`. Handles every subsampling mode
  (4:4:4 / 4:2:2 / 4:4:0 / 4:2:0) via the `subX`/`subY` footprint.
  `alpha` (CflAlphaU/V) and `MaxLumaW`/`MaxLumaH` are caller inputs until
  block/mode-info decode lands; the luma extent is clamped to the luma
  plane as an out-of-bounds backstop. 202 assertions (up from 172): the
  hand-computed 4:4:4 and 4:2:0 known answers (positive and negative
  alpha), the Clip1 saturation at both ends, the MaxLuma edge-replication
  clamp, and the zero-alpha / flat-luma identity invariants.

### Notes
- `drishti_version()` → 710. This completes the AV1 **intra prediction**
  layer (7.11.2 + 7.11.5); coefficient decode (with the default CDF
  tables) is the next milestone sub-bite toward first pixels.

## [0.7.9] - 2026-07-10

Adds AV1 recursive filter-intra prediction — the fifth milestone
sub-bite. Derived verbatim from spec 7.11.2.3 + the `Intra_Filter_Taps`
table, and cross-checked by a 4-agent adversarial spec review (clean).
**4,050 suite assertions + 1,140 fuzz assertions, all green.**

### Added
- **AV1 recursive filter-intra prediction** (`src/av1_intra.cyr`):
  `av1_intra_filter_intra` (7.11.2.3) filters the luma block in 4x2
  sub-blocks in raster order, each from 7 neighbours (the AboveRow /
  LeftCol edges plus already-predicted samples), driven by the
  `Intra_Filter_Taps[5][8][7]` table (lazy-init, all 280 taps transcribed
  verbatim; every position's row sums to 16, so a flat reference
  reproduces itself). Adds `av1_round2_signed` (Round2 for x≥0,
  −Round2(−x) for x<0 — spec section 4) over the arithmetic `av1_round2`.
  The `predict_intra` driver gains a `filter_intra_mode` (0..4) input and
  now routes `plane == 0 && use_filter_intra` here (previously
  `DR_ERR_UNSUPPORTED`); the filter-intra path uses the plain reference
  samples (no directional edge filter/upsample). 172 assertions (up from
  96): the hand-computed known answer, the flat-reference invariant for
  all five filter modes, the tap-table spot-checks + the sum-to-16
  invariant, and the `Round2Signed` sign/rounding cases.

### Notes
- `drishti_version()` → 709. Chroma-from-luma (7.11.5) is the remaining
  intra sub-bite before coefficient decode.

## [0.7.8] - 2026-07-10

Completes AV1 directional intra prediction — the fourth milestone
sub-bite. Derived from spec 7.11.2.4 + the intra edge machinery
(7.11.2.7-12), and cross-checked by a 4-agent adversarial spec review
(clean). **3,974 suite assertions + 1,140 fuzz assertions, all green.**

### Added
- **AV1 directional intra prediction** (`src/av1_intra.cyr`): the full
  `av1_intra_directional` (7.11.2.4) — all four angle quadrants
  (pAngle <90, 90-180 with the LeftCol fallback, >180, and the 90°/180°
  copies), the intra edge **filter corner** (7.11.2.7), **filter strength
  selection** (7.11.2.9), **upsample selection** (7.11.2.10), **edge
  upsample** (7.11.2.11), and **edge filter** (7.11.2.12), plus the
  `Dr_Intra_Derivative` and `Intra_Edge_Kernel` tables. The `predict_intra`
  driver now routes every directional mode here (the reference scratch
  gained -2 headroom for the edge upsample) and takes `enable_edge_filter`
  + `filter_type` inputs. The signed shift in the 90-180 quadrant uses the
  arithmetic `>>>`. 96 assertions (up from 48).

### Notes
- `drishti_version()` → 708. Filter-intra (7.11.2.3) and chroma-from-luma
  (7.11.5) remain later sub-bites.

## [0.7.7] - 2026-07-10

Adopt cyrius 6.4.46's new arithmetic-shift operator and retire the 0.7.5
workaround. **3,926 suite assertions + 1,140 fuzz assertions, all green.**

### Changed
- **Arithmetic right shift now uses the native `>>>`** (cyrius 6.4.46):
  the `dr_ashr` shim added in 0.7.5 is deleted, and its call sites — the
  inverse-transform `Round2` / WHT and `av1_read_global_param`'s
  `PrevGmParams` shift — use `x >>> n` directly. `>>` remains a LOGICAL
  shift (note: the reverse of JS/Java, because `>>` is load-bearing for
  crypto rotates upstream). The transform / global-motion known-answers
  are unchanged. Closes the upstream issue filed at 0.7.5.
- **Toolchain pin → 6.4.46** (`cyrius.cyml`), the minimum with `>>>`;
  resolves the pin-drift warning.

### Notes
- `drishti_version()` → 707.

## [0.7.6] - 2026-07-10

The third sub-bite of the AV1 intra still-picture decode milestone: intra
prediction — the non-directional modes and the exact vertical/horizontal
directional cases. Derived from spec 7.11.2, pinned by hand-computed
known-answers, and cross-checked by a 4-agent adversarial spec review
(clean). **3,927 suite assertions + 1,140 fuzz assertions, all green.**

### Added
- **AV1 intra prediction** (`src/av1_intra.cyr`, prefix `av1_`): the
  `predict_intra` driver (7.11.2.1) — reference-sample (AboveRow/LeftCol)
  construction from the reconstructed `DrFrame` with the availability /
  subsampling / edge-clamp rules and the corner sample — dispatching to
  DC (7.11.2.5), PAETH (basic, 7.11.2.2), SMOOTH / SMOOTH_V / SMOOTH_H
  (7.11.2.6, with the `Sm_Weights` tables), and the pAngle 90° / 180°
  vertical / horizontal directional copies, then writing the prediction
  back into the frame. 48 assertions.
- Deferred to later 0.7.x sub-bites (return `DR_ERR_UNSUPPORTED`): the
  angled directional modes + intra edge filter/upsample (7.11.2.7-12),
  the recursive filter-intra (7.11.2.3), and chroma-from-luma (7.11.5).

### Notes
- `drishti_version()` → 706; toolchain pin unchanged (`6.4.43`).

## [0.7.5] - 2026-07-10

A focused correctness fix. Cyrius's runtime `>>` is a LOGICAL (unsigned)
shift, so shifting a negative value logically corrupts it — surfaced
while building the inverse transform. **3,879 suite assertions + 1,140
fuzz assertions, all green.**

### Fixed
- **AV1 global-motion param decode** (`av1_read_global_param`, spec
  5.9.25): `PrevGmParams[ref][idx] >> precDiff` was a logical shift, but
  the reference value can be negative (the spec intends an arithmetic
  shift). This corrupted the decoded warp params for inter frames whose
  primary reference carries negative saved global-motion params — latent
  since 0.7.1 (dormant until inter global-motion compensation lands, but
  a real value bug). Now shifts through `dr_ashr`. Regression-tested: a
  zero subexp delta must recover a negative `PrevGmParams` exactly.

### Added
- **Core `dr_ashr`** (`src/bits.cyr`): arithmetic (sign-preserving) right
  shift = floor(x / 2^n), the shared helper for shifting signed values.
  `av1_itx`'s `Round2` / WHT and `av1_read_global_param` now route through
  it. An audit of every `>>` in the tree confirmed no other negative-
  operand shift is wrong (the rest are non-negative, or byte/bit
  extractions with `& mask` that make the shift kind irrelevant).

### Notes
- `drishti_version()` → 705; toolchain pin unchanged (`6.4.43`).

## [0.7.4] - 2026-07-10

The second sub-bite of the AV1 intra still-picture decode milestone: the
inverse transform block (spec 7.13). Transcribed verbatim from the spec
pseudocode, pinned by hand-computed known-answers, and cross-checked by a
5-agent adversarial spec review (clean). **3,862 suite assertions +
1,140 fuzz assertions, all green.**

### Added
- **AV1 inverse transform** (`src/av1_itx.cyr`, prefix `av1_`): the full
  inverse transform block — inverse DCT (sizes 4-64, the 31-step
  butterfly), inverse ADST (4/8/16), the identity transforms (4/8/16/32),
  the lossless Walsh-Hadamard, and the `av1_inverse_transform_2d` driver
  that routes each of the 16 PlaneTxTypes to the right row/column
  transform with the spec's 64-point zeroing, rectangular 2896 scaling,
  clamps, and rounding shifts. Includes the butterfly primitives
  (`cos128`/`sin128`/`brev`/B/H), `Round2`, and the `Cos128_Lookup` /
  `Tx_*_Log2` / `Transform_Row_Shift` tables. 160 assertions.

### Notes
- `drishti_version()` → 704; toolchain pin unchanged (`6.4.43`).
- Cyrius runtime `>>` is a LOGICAL shift (it does not sign-extend), so
  signed transform intermediates round through an explicit arithmetic
  shift (`av1_shr`); `Round2` and the WHT use it.

## [0.7.3] - 2026-07-10

The shared substrate for pixel output: a planar YUV frame-buffer type,
the first piece of the 0.7.x AV1 intra still-picture decode milestone (it
lands with the first decoder to emit pixels and is reused by every
family). **3,702 suite assertions + 1,140 fuzz assertions, all green.**

### Added
- **YUV planar-frame buffer** (`src/frame.cyr`, core prefix `dr_`): a
  `DrFrame` holding 1 (monochrome) or 3 (Y/U/V) planes of 16-bit samples
  — 8/10/12-bit share one representation — with per-plane subsampling
  (4:2:0 / 4:2:2 / 4:4:4, chroma dims via ceil) and an optional padding
  border so intra "above"/"left" neighbours (and later inter read-past)
  are addressable at negative coordinates. `dr_frame_new` (with a
  16384-per-dimension bomb guard), sample get/set, `dr_frame_fill`, and
  the reconstruction workhorse `dr_clip1` (Clip3 to the bit-depth range).
  73 assertions.

### Notes
- `drishti_version()` → 703; toolchain pin unchanged (`6.4.43`).

## [0.7.2] - 2026-07-10

The **0.7.x AV1 arc** continues with the entropy substrate: the
multi-symbol adaptive-CDF arithmetic (symbol) decoder (spec 8.2) that
every tile decode reads through, plus its paired encoder (the
encode-lane seed). Encoder-independent known-answers pin the decoder to
the spec; encode→decode round-trips (bit-exact CDF adaptation on both
sides) prove the encoder is its exact inverse; a 5-agent adversarial
spec review came back clean. **3,629 suite assertions + 1,140 fuzz
assertions, all green.**

### Added
- **AV1 symbol coder** (`src/av1_symbol.cyr`, prefix `av1_`): the daala/
  msac-lineage multi-symbol range coder. DECODER (spec 8.2) — `init_symbol`
  (SymbolValue/Range/MaxBits), `read_symbol` (the multi-symbol decode +
  in-place CDF adaptation, `EC_PROB_SHIFT`/`EC_MIN_PROB`), `read_bool`,
  `read_literal`, `exit_symbol` — over an `Av1SymDec` reading a partition
  through the core MSB-first bitreader. ENCODER — the exact inverse
  (`u=U(R,s-1)`, `v=U(R,s)`, `low+=R-u`, `rng=u-v`) with the daala
  normalization + carry flush (cross-checked against rav1e `src/ec.rs`),
  over an `Av1SymEnc`; the two share one CDF-adaptation routine so they
  stay bit-for-bit in lockstep. 280 assertions.
- **Core `dr_br_skip`** (`src/bits.cyr`): forward bit-skip that (unlike
  `dr_br_read_bits`) accepts n > 32, bounds-checked — used by
  `exit_symbol` to advance over trailing bits.

### Notes
- `drishti_version()` → 702; toolchain pin unchanged (`6.4.43`).
- Symbol-decoder fuzz-corpus expansion (random bytes / CDFs) is folded
  into the 0.11.x audit arc; this cut relies on the round-trip,
  known-answer, and truncation-padding tests plus the spec review.

## [0.7.1] - 2026-07-10

The **0.7.x AV1 arc** opens: the full uncompressed frame header (spec
5.9.2) for every frame type — key / inter / intra-only / switch /
show_existing — parsed cursor-true, plus the reference-frame state
machine. Spec-derived and adversarially reviewed (a 12-agent
field-by-field cross-check against the AV1 spec markdown found and fixed
one tile-count heap-overflow). **3,349 suite assertions + 1,140 fuzz
assertions, all green** (up from 2,220 + 1,140).

### Added
- **AV1 frame header** (`src/av1_frame.cyr`, prefix `av1_`): the complete
  `uncompressed_header()` (5.9.2) — the frame-type / show / error-
  resilient prologue, screen-content + integer-mv gating, order hints,
  frame-size overrides + superres (5.9.5–5.9.9), interpolation filter,
  loop-filter / quantization / segmentation / delta-Q / delta-LF /
  tile-info (5.9.3 tile_log2 + `ns()`) / CDEF / loop-restoration /
  TX-mode / reference-mode / skip-mode / global-motion (subexp decode
  5.9.25–5.9.29) / film-grain (5.9.30) params — cursor-true for key,
  inter, intra-only, switch, and show_existing frames. Emits an
  `Av1FrameHeader` record with a `CodedLossless` / `AllLossless`
  derivation via `get_qindex` (7.12.2). 134 assertions.
- **AV1 reference-frame state machine**: `set_frame_refs` (7.8),
  `frame_size_with_refs`, `mark_ref_frames`, and the reference frame
  update (7.20) over an eight-slot `Av1RefState` tracking RefValid /
  RefOrderHint / RefFrameId / Ref{Upscaled,Frame,Render}{Width,Height} /
  RefFrameType / SavedGmParams — the geometry and order hints the header
  reads back on later frames.
- **Full-fidelity `Av1Seq` growth** (`src/av1_seq.cyr`): the sequence
  header now captures every field the frame header consults (OrderHintBits,
  the `seq_force_*` SELECT defaults, frame-id lengths,
  `use_128x128_superblock`, the `enable_*` tool flags, decoder-model
  field lengths, subsampling / NumPlanes / separate_uv_delta_q, per-op
  operating-point idc + decoder-model flags) — not just the 0.7.0
  summary set. ABI-stable for the original seven accessors.
- **Core `su(n)` / `ns(n)` descriptors** (`src/bits.cyr`): the AV1 signed
  (4.10.6) and non-symmetric (4.10.7) bit descriptors — read and write —
  plus `FloorLog2`, with exhaustive round-trip tests.

### Security
- **Tile-count bound** (MAX_TILE_COLS / MAX_TILE_ROWS): the non-uniform
  `tile_info` loop is capped so a hostile stream of one-superblock tiles
  cannot overrun the fixed `MiColStarts` / `MiRowStarts` arrays — found by
  the adversarial spec review, rejected with `AV1_ERR_BAD_FRAME`, and
  covered by a regression vector.

### Notes
- `drishti_version()` → 701; toolchain pin unchanged (`6.4.43`).

## [0.7.0] - 2026-07-10

The first cut — one repo, four codec families as flat `[lib]` modules
over a shared core (the shravan model — [ADR 0001](docs/adr/0001-one-repo-module-per-codec.md)
records the collapse of the five planned `drishti-*` repos into this
one, and the merge of the AV1 decode and encode charters). Every
family's bitstream/container/header layer, spec-derived and
adversarially tested: **2,220 suite assertions + 1,140 fuzz assertions,
all green**; `dist/drishti.cyr` verified via a consumer-style build.

> **Versioned at 0.7.0** (not 0.1.0): the shared substrate + all four
> families' full bitstream/container/header surface is substantial and
> already hardened — "almost ready for v1, but not quite." The
> remaining distance is the per-codec decode/encode completion arcs
> (0.7.x AV1 → 0.8.x H.264 → 0.9.x H.265 → 0.10.x VP8/VP9), then an
> audit arc (0.11.x) and a freeze/documentation arc (0.12.x) before the
> 1.0.0 close-out. See [`docs/development/roadmap.md`](docs/development/roadmap.md).

### Added
- **Core** (`src/drishti.cyr`, `src/bits.cyr`, `src/ivf.cyr`, prefix `dr_`):
  error record + per-family error-code bands + format sniff (IVF fourcc
  / Annex-B / unknown); MSB-first bitreader with sticky-error
  discipline; leb128 read/write (AV1 4.10.5 conformance bounds), uvlc
  (4.10.3), exp-Golomb ue/se read (H.264 9.1 / H.265 9.2); bit writer
  with ue/se/leb128 write — the encode-lane seed; IVF container
  read/write (AV01/VP80/VP90); external sticky-latch seam
  `dr_br_set_err` / `dr_bw_set_err` for family modules.
- **AV1** (`src/av1_obu.cyr`, `src/av1_seq.cyr`, prefix `av1_`): OBU
  header parse (spec 5.3.2/5.3.3, forbidden-bit rejection), OBU buffer
  walk, `av1_obu_write_header` encode seed; sequence_header_obu parse
  (5.5.1/5.5.2) on both the reduced-still-picture and full
  operating-points paths → {profile, dims, bitdepth 8/10/12, mono,
  still}. 185 assertions.
- **H.264/AVC** (`src/h264_nal.cyr`, `src/h264_ps.cyr`, prefix
  `h264_`): Annex-B scan (3-/4-byte start codes, zero_byte
  attribution), NAL header parse (Table 7-1), emulation-prevention
  both directions (RBSP strip + EPB insert, round-trip proven), Annex-B
  composer (encode seed); full SPS parse (7.3.2.1.1 incl. High-profile
  branch + cropped display dims) + minimal PPS. 326 assertions.
- **H.265/HEVC** (`src/h265_nal.cyr`, `src/h265_ps.cyr`, prefix
  `h265_`, decode-only charter): strict Annex-B scan (B.2.2), two-byte
  NAL header (7.3.1.2) + VCL/IRAP/IDR predicates, RBSP extraction,
  profile_tier_level (7.3.3), VPS/SPS/PPS with crop math (Table 6-1)
  and an A.4.2 dimension-bomb guard. 276 assertions.
- **VP8/VP9** (`src/vpx_bool.cyr`, `src/vp8.cyr`, `src/vp9.cyr`,
  prefixes `vbool_`/`vp8_`/`vp9_`): the RFC 6386 7.3 boolean
  arithmetic coder — decoder AND encoder with
  carry-at-renormalization, bounds-hardened (the RFC reference reads
  past the buffer; this port latches sticky `DR_ERR_TRUNCATED`); VP8
  frame framing (9.1) with validated builder + byte-exact writer; VP9
  uncompressed header (6.2-6.2.4) incl. the show_existing_frame
  short-circuit and the RGB-in-profile-0/2 rejection. 287 assertions
  incl. two hand-computed encoder known-answer vectors.
- Smoke program exercising one real operation per family; fuzz harness
  (1,140 assertions: exhaustive IVF header mutation, hostile frame-size
  fields, every truncation prefix, random-garbage buffers through
  reader + all VLCs); bitreader/VLC benchmarks; Makefile
  (build/test/fuzz/bench/dist/lint gates); docs tree (roadmap with
  per-family phase plans, sources citation index, ADR 0001,
  getting-started guide).

### Notes
- Toolchain pin `6.4.43`; scaffolded via `cyrius init --lib`.
- Benchmarks (64 KiB inputs, 20 iters): `dr_br_read_bit` ×524,288 in
  ~3.7 ms; `dr_br_read_bits(7)` ×74,898 in ~4.4 ms; `dr_ue_read` drain
  of 64 KiB random in ~6.5 ms.
