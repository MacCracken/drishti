# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.7.36] - 2026-07-11

Adds the AV1 **symbol-coder subexponential primitives** (`src/av1_symbol.cyr`) —
the entropy substrate `read_lr` needs to read loop-restoration unit params. These
are the arithmetic-coded ("_bool") counterparts of the frame-header f/ns subexp
coder: `NS(n)` over the symbol coder, `decode_subexp_bool(numSyms, k)`, and the
unsigned/signed with-reference variants, each with a matching encoder + the forward
`av1_recenter` (the exact inverse of the existing `av1_inverse_recenter`). A 1-agent
adversarial review brute-forced **bit-pattern equality** (not just round-trip)
against the spec and cross-checked the decode side against the production
frame-header `av1_decode_subexp` — **all match, no conformance bugs**. **20,324
suite assertions + 1,140 fuzz assertions, all green; `make lint` green.**

### Added
- **Subexp-bool primitives** (`src/av1_symbol.cyr`): `av1_sym_read_ns` /
  `av1_sym_encode_ns` (NS(n) via the arithmetic coder's literal reads, matching
  `dr_ns_read`/`dr_ns_write`); `av1_decode_subexp_bool` / `av1_encode_subexp_bool`
  (subexponential value in `[0, numSyms)` with parameter `k`); the
  `unsigned`/`signed_subexp_with_ref_bool` decode+encode pairs; and `av1_recenter`
  (`src/av1_frame.cyr`, the forward inverse of `av1_inverse_recenter`).
- **Tests** (`tests/av1_symbol.tcyr`, +82): full-range round-trips for `NS`
  (n = 1/5/16), `subexp_bool` (all values, k = 1/2/3), and
  `signed_subexp_with_ref_bool` across the real Wiener-tap (`[-5,10]` …) and
  SGR-xqd (`[-32,95]`) ranges with negative references — cross-checked against a
  Python model — plus the encoder-bounds guards below.

### Fixed / hardened
- **Encoder range validation (review note):** `av1_sym_encode_ns` and
  `av1_encode_subexp_bool` now reject out-of-range `value` with `DR_ERR_BOUNDS`,
  matching the sibling `dr_ns_write` (the decoders were already spec-exact; this
  closes an encoder-side defensive asymmetry the review flagged). Regression tested.

### Notes
- `drishti_version()` -> 736. `read_lr` is split (it is bigger than `read_cdef`):
  these entropy primitives this bite; next the restoration-type CDFs + `read_lr_unit`
  (the per-unit type + Wiener-coeff / SGR-set-xqd reads), then the `read_lr`
  per-superblock geometry + `decode_tile` wiring.

## [0.7.35] - 2026-07-11

Completes the AV1 **loop-restoration driver** (spec 7.17.1 process + 7.17.2
loop_restore_block, `src/av1_lr.cyr`): the stripe-based loop that copies
`UpscaledCdefFrame` -> `LrFrame`, then per 4x4 block dispatches the Wiener or SGR
kernel by restoration-unit type. **This closes the in-loop filter layer's pixel
processes** — all three filters (deblocking, CDEF, loop restoration) now have both
kernels and drivers. A 1-agent adversarial review verified all 7 driver geometry
points (count_units, the copy/UsesLr gate, the **negative-`StripeStartY`
arithmetic shift**, the `unitRow`(+8)/`unitCol` index asymmetry, block extent, the
pass->vfilter/hfilter dispatch mapping, and grid memory) with **no geometry/dispatch
bugs**, and found one low-severity ordering bug (**fixed**, see below). **20,242
suite assertions + 1,140 fuzz assertions, all green; `make lint` green.**

### Added
- **AV1 loop-restoration driver** (`src/av1_lr.cyr`): `av1_lr_process` (7.17.1 —
  `LrFrame = copy(UpscaledCdefFrame)`; return on `UsesLr == 0`; else per 4x4 block
  per plane with `FrameRestorationType != RESTORE_NONE`, invoke loop_restore_block);
  `av1_lr_restore_block` (7.17.2 — `stripeNum = (lumaY+8)/64`, `StripeStartY =
  (stripeNum*64 - 8) >>> subY` (arithmetic: negative for stripe 0), the unit-index
  `Min` clamps, the block extent `x/y/w/h`, then the Wiener (vfilter=coeff[0],
  hfilter=coeff[1]) or SGR (set + xqd) dispatch); `av1_lr_count_units`; and the
  `Av1LrParams` structure + accessors holding the per-restoration-unit `LrType` /
  `LrWiener` / `LrSgrSet` / `LrSgrXqd` grids.
- **Tests** (`tests/av1_lr.tcyr`, +13 -> 57): `count_units`, and the full process
  on an impulse frame where the output **discriminates the dispatched filter**
  (WIENER -> 169, SGRPROJ -> 199, RESTORE_NONE -> 200 copy, `UsesLr == 0` -> copy)
  plus the flat DC-passthrough — all cross-checked against a Python model of
  7.17.1/2.

### Fixed
- **`av1_lr_params_set_plane` state-before-validation (review finding):** it wrote
  `FrameRestorationType[plane]` (the dispatch gate) before validating the grid
  allocations, so on OOM it returned `DR_ERR_OOM` but left the plane dispatchable
  with null grids -> a caller ignoring the error would near-null OOB-read. Reordered
  to allocate + validate first and write `RTYPE` last, so on OOM the plane stays
  `RESTORE_NONE` and is never dispatched (never-crash contract).

### Notes
- `drishti_version()` -> 735. The in-loop filter pixel processes are complete;
  remaining LR integration is `read_lr` (5.11.57) to populate `Av1LrParams` from
  the bitstream. Then the frame-level driver that runs deblock -> CDEF -> LR
  end-to-end (which also activates the wired-but-inert CDEF `set_cdef_ctx`), then
  inter prediction.

## [0.7.34] - 2026-07-11

Adds the AV1 loop-restoration **self-guided / SGR** filter kernels (spec 7.17.2 +
7.17.3), the second loop-restoration filter path (`src/av1_lr.cyr`): the
`Sgr_Params` table (16 sets), the **box filter** (7.17.3 — the A/B box statistics
with the integer reciprocal/mtable divisions, then the 3x3 two-pass weighted
output), and the **self-guided projection** (7.17.2 — two box-filter passes
combined by the projection weights into `LrFrame`). All cross-checked against an
independent Python model of 7.17.2/7.17.3. A 1-agent adversarial review of the
box filter — AV1 LR's most numerically intricate kernel — confirmed **all match,
no bugs**, specifically clearing the four trap sites: the `z == 255` a2 boundary,
the raw-`b` (not rounded `d`) usage in `b2`, the negative-`i+dy` parity, and every
shift/round amount. **20,229 suite assertions + 1,140 fuzz assertions, all green;
`make lint` green.**

### Added
- **AV1 loop-restoration SGR kernels** (`src/av1_lr.cyr`): `av1_lr_sgr_params`
  (the 16-set `Sgr_Params` table), `av1_lr_box_filter` (7.17.3 — builds `A`/`B`
  over a 1-sample boundary: `n=(2r+1)^2`, the `s`/`oneOverN` division constants,
  `a2` via the `z`-indexed reciprocal with the 256/1/formula three-way branch, then
  the pass-dependent 3x3 weighted output into `F`; returns 0 without writing when
  the pass radius `r == 0`); `av1_lr_self_guided` (7.17.2 — pass 0 -> `flt0`,
  pass 1 -> `flt1`, then `Round2(w1*u + w0*{flt0|u} + w2*{flt1|u}, RST_BITS+PRJ_BITS)`
  -> `Clip1`, with `w2 = (1<<PRJ_BITS) - w0 - w1`). SGRPROJ constants inline
  (MTABLE 20 / SGR 8 / RECIP 12 / RST 4 / PRJ 7).
- **Tests** (`tests/av1_lr.tcyr`, +21 -> 44): the `Sgr_Params` values, the box
  filter on a flat block (set-0 pass-0 -> 1602, pass-1 -> 1600) + the `r == 0` skip
  path, and the self-guided **DC-preservation** passthrough / vertical ramp /
  impulse (200 -> 199) / `r0 == 0` set (uses the source) — all matching the model.

### Notes
- `drishti_version()` -> 734. Loop restoration now has both filter kernels
  (Wiener 0.7.33 + SGR 0.7.34); next is the stripe-loop driver (7.17.1/2) + the
  `read_lr` (5.11.57) unit-param read + `LrFrame`. **Review robustness note
  (systemic, not an SGR bug):** the box-filter scratch `alloc`s are unchecked
  before use — the codebase-wide bump-allocator pattern (bounded by the
  restoration-unit size, not a dimension-bomb vector), tracked with the audit-arc
  arena-strategy item, not silently patched here.

## [0.7.33] - 2026-07-11

Starts the AV1 **loop restoration** filter (spec 7.17, the third and last in-loop
filter, after deblocking + CDEF) with the **Wiener** path kernels (`src/av1_lr.cyr`,
new module): the symmetric 3->7-tap coefficient expansion (7.17.6), the
stripe-aware source fetch (7.17.7), and the separable 7-tap Wiener filter (7.17.5).
All cross-checked against an independent Python model of 7.17.5. A 1-agent
adversarial review (coeff expansion / rounding / get_source_sample / the filter
convolution + memory) confirmed **all match, no bugs** — including the offset/limit
bit-grouping, the source-coord offsets, and the horizontal/vertical + curr/cdef
assignments. **20,208 suite assertions + 1,140 fuzz assertions, all green; `make
lint` green.**

### Added
- **AV1 loop-restoration Wiener kernels** (`src/av1_lr.cyr`): `av1_lr_wiener_coeff`
  (7.17.6 — expands the 3 coded taps to the 7-tap symmetric, unit-DC-gain filter;
  chroma's `coeff[0] == 0` degenerates to 5-tap); `av1_lr_get_source_sample`
  (7.17.7 — clamps to the plane extent and routes by the stripe boundary: within
  the stripe from `UpscaledCdefFrame`, outside from `UpscaledCurrFrame`, with the
  3rd-line-above/below crop); `av1_lr_wiener_filter` (7.17.5 — two 1-D 7-tap
  convolutions, horizontal into an `intermediate[(h+6) x w]` array then vertical
  into `LrFrame`, with per-bit-depth rounding `InterRound0/1` from 7.11.3.2,
  isCompound = 0).
- **Tests** (`tests/av1_lr.tcyr`, 23 assertions): the coefficient expansion (luma
  7-tap + chroma 5-tap, sum = 128), the source fetch (plane-extent clamp + stripe
  routing + 3rd-line crop), and the filter — the **unit-DC-gain passthrough** (a
  flat block is unchanged, the strongest check), a vertical ramp (also passes
  through), and an impulse spread — all matching the Python model.

### Notes
- `drishti_version()` -> 733. Loop restoration is split like CDEF was: Wiener
  kernels this bite, the self-guided / SGR box filter (7.17.3) next, then the
  stripe-loop driver (7.17.1/2) + `read_lr` wiring + `LrFrame`. Two review caveats
  are driver contracts (the caller must pass in-plane stripe bounds and keep
  `UpscaledCurrFrame`/`UpscaledCdefFrame` at the same bit depth), not kernel bugs.

## [0.7.32] - 2026-07-11

Wires the CDEF-index syntax into the decode/encode path: `read_cdef` is spliced
into `intra_frame_mode_info` (after `read_skip`, spec 5.11.16 order), `write_cdef`
mirrors it, and `clear_cdef` runs per superblock in the `decode_tile`/`encode_tile`
loops. A tile carries a CDEF read context (`av1_tile_set_cdef_ctx`) bundling the
frame-header flags + the `CdefIdx` grid; the splice is guarded by `cdef_ctx != 0`
so existing non-CDEF streams stay **byte-identical** (every prior test unchanged).
A 1-agent adversarial review verified all 6 wiring points (ctx offset agreement,
splice placement, 18-arg threading, `clear_cdef` placement, backward-compat,
spec-order) with **no wiring bugs**. **Scope honesty: the mechanism is wired and
round-trip tested, but no production frame-level driver calls `set_cdef_ctx` yet**
— so in the current build the splice is inert for real streams (see Notes). **20,185
suite assertions + 1,140 fuzz assertions, all green; `make lint` green.**

### Added
- **CDEF-index decode/encode wiring**: `read_cdef` / `write_cdef` spliced into
  `av1_intra_frame_mode_info_decode` / `_encode` (`av1_modeinfo.cyr`) after skip,
  guarded by the tile's CDEF context; `clear_cdef` in the `decode_tile` /
  `encode_tile` superblock loops (`av1_tile.cyr`, `use_128 = 0` for 64x64 SBs).
- **Tile CDEF read context** (`av1_residual.cyr`): `AV1TILE_CDEF_CTX` + the
  `av1_tile_set_cdef_ctx(enable_cdef, cdef_bits, coded_lossless, allow_intrabc,
  plan)` setter (7-i64 bundle: flags + `CdefIdx` grid ptr + stride + encode plan).
  Fails `DR_ERR_BOUNDS` if called before `av1_tile_grids_new` (would capture a
  null grid — enforces the ordering the review flagged).
- **Tests** (+15): a cdef-enabled mode-info round-trip proving `cdef_idx` reads at
  the correct bit position **and** `y_mode` stays aligned (a misplaced/absent
  splice would misalign it), a skip-gated variant (no cdef bits, grid stays -1),
  and the `set_cdef_ctx` grid-guard + layout. All 9 pre-existing
  `intra_frame_mode_info` call sites updated for the 3 new trailing args.

### Notes
- `drishti_version()` -> 732. **Activation gap (tracked, honest):** `set_cdef_ctx`
  has no production caller yet, so `AV1TILE_CDEF_CTX == 0` on every current path
  and the splice is inert for real bitstreams — the wiring activates when the
  frame-level decode driver (which parses the frame header and assembles the tile)
  calls `set_cdef_ctx`, a later bite (roadmap.md). A full tile-level CDEF round-trip
  is additionally blocked by the deferred non-skip encode lane (cdef only reads on
  non-skip blocks), so the wiring is validated at the mode-info level for now. Next:
  the frame-level CDEF activation, then loop restoration (7.17).

## [0.7.31] - 2026-07-11

Adds the AV1 **CDEF-index syntax** primitives — `read_cdef` (spec 5.11.56) +
`clear_cdef` + the paired `write_cdef` — the per-64x64 `cdef_idx` bitstream read
that feeds the 0.7.30 CDEF driver's `CdefIdx` grid. Standalone and round-trip
tested this bite; the decode-path wiring (into `intra_frame_mode_info` + the
`decode_tile` superblock loop) is the next bite, mirroring the 0.7.29 (kernels) ->
0.7.30 (driver) split. A 1-agent adversarial review (6 points vs spec 5.11.56 +
`clear_cdef`) confirmed **all match, no conformance bugs, encode/decode symmetric**
(its two suggestions — a comment-accuracy fix and a 128x128 round-trip test —
are both applied). **20,170 suite assertions + 1,140 fuzz assertions, all green;
`make lint` green.**

### Added
- **CDEF-index syntax** (`src/av1_modeinfo.cyr`): `av1_read_cdef` (5.11.56) reads
  `cdef_idx` once per 64x64 (guarded by `cdef_idx[r1][c1] == -1`; gated off on
  skip / CodedLossless / !enable_cdef / allow_intrabc) via `L(cdef_bits)` and
  fills the block's 4x4 extent (`r1 = MiRow & ~15`, step `cdefSize4 = 16`);
  `av1_write_cdef` is the byte-identical encode mirror (emits `plan[r1][c1]`);
  `av1_clear_cdef` resets a superblock's anchor(s) to -1 (one for 64x64, four for
  128x128). Pointer-based (grid + stride) so they sit in an early module the
  decode-path wiring can reach.
- **Tests** (`tests/av1_modeinfo.tcyr`, +26 -> 336 assertions): a two-unit
  `write_cdef`->`read_cdef` round-trip, the once-per-64x64 guard (with a proof
  that non-anchor cells stay -1), the single-`BLOCK_128X128` four-anchor fill
  round-trip, all four disabling gates (`read_cdef` consumes nothing), and
  `clear_cdef` (64x64 + 128x128).

### Notes
- `drishti_version()` -> 731. **Next (0.7.32): wire `read_cdef`/`clear_cdef` into
  the decode path** — thread the CDEF read context (grid + `enable_cdef` /
  `cdef_bits` / `CodedLossless` / `allow_intrabc` / `use_128x128`) into
  `intra_frame_mode_info` after `read_skip`, and `clear_cdef` into the
  `decode_tile` SB loop — so a real profile-0 keyframe populates `CdefIdx` for the
  0.7.30 driver. Then loop restoration (7.17).

## [0.7.30] - 2026-07-11

Completes the AV1 **CDEF driver** — the process (spec 7.15) + block process
(7.15.1) that walk every 8x8 block, copy `CurrFrame`->`CdefFrame`, and (per the
64x64 `CdefIdx` + the `Skips` grid) run the direction search, the var-scaled luma
strength derivation, and the per-plane filter over the 0.7.29 kernels. A whole
deblocked frame now derings into a fresh `CdefFrame`. This bite also **enforces
the CDEF frame contract** flagged at 0.7.29 (review finding 1): the process
rejects (never OOBs) any frame that doesn't cover the MI grid. A 2-agent
adversarial review (7.15/7.15.1 spec conformance; coverage guard + memory safety)
confirmed the spec logic with **no conformance findings** and surfaced **one
latent OOB (fixed)** — an unbounded `CdefIdx` could index past the frame-header
strength arrays. **20,144 suite assertions + 1,140 fuzz assertions, all green;
`make lint` green.**

### Added
- **AV1 CDEF process + block process** (`src/av1_cdef.cyr`): `av1_cdef_process`
  (7.15) — the outer loop over 8x8 blocks (step 2 MI units), reading each block's
  64x64-aligned `CdefIdx`; `av1_cdef_block` (7.15.1) — copies the block (luma +
  chroma) to `CdefFrame`, returns on `idx == -1` / all-skip, else runs the
  direction search, the luma strength derivation (`dir` from the pre-var-scaled
  `priStr`; `priStr = var ? (priStr*(4+varStr)+8)>>4 : 0`; damping = CdefDamping +
  coeffShift) and filter, then the chroma path (uv strengths, `Cdef_Uv_Dir`
  remap, damping-1); `av1_cdef_frame_new` allocates a `CdefFrame` (border >= 8, so
  it always covers the MI grid); `av1_cdef_coverage_ok` is the MI-grid coverage
  guard.
- **`CdefIdx` grid** (`src/av1_residual.cyr`): a per-64x64, MI-indexed grid on the
  `Av1Tile` (`AV1TILE_CDEFIDX`), allocated by `av1_tile_grids_new` **initialized
  to -1** (clear_cdef: no filtering until `read_cdef` sets it), with
  `av1_cdefidx_get/set`.
- **Tests** (`tests/av1_cdef.tcyr`, +22 -> 42 assertions): the block process on a
  32x32 frame — a var-scaled luma spike (140 -> 138), `idx == -1` copy-through,
  all-skip passthrough, the coverage guard (undersized frame -> `DR_ERR_BOUNDS`,
  bordered frame -> `DR_OK`), the chroma path (uv spike 132 -> 128), and the two
  hardening regressions below. All cross-checked against a Python model of 7.15.1.

### Fixed / hardened
- **Latent OOB read of the frame header (review finding, fixed):** `av1_cdef_block`
  now bounds `idx` to the 8-entry CDEF strength arrays (`idx >= 8` degrades to
  copy-through) — a garbage/fuzzed `CdefIdx` can no longer index past the frame
  header (trust-no-input; the future `read_cdef` will also bound it to
  `[0, 2^cdef_bits)`). Regression test added.
- **Null-frame guard:** `av1_cdef_process` rejects a null `curr`/`cdef` (e.g. an
  OOM'd `CdefFrame`) with `DR_ERR_BOUNDS` instead of dereferencing near-null.
  Regression test added.

### Notes
- `drishti_version()` -> 730. Two by-contract preconditions are documented (not
  guarded, as they are unreachable from the decode path): even `mi_cols/mi_rows`
  (they are `2*ceil(dim/8)`) and grids-allocated-before-process. **Review finding
  2 (systemic per-block bump-allocator scratch) is unchanged — deferred to the
  audit arc.** Next: `read_cdef` (5.11.56) to populate `CdefIdx` from the
  bitstream during `decode_block`, then loop restoration (7.17).

## [0.7.29] - 2026-07-11

Starts AV1 **CDEF** (Constrained Directional Enhancement Filter, the second
in-loop filter) with the pixel-math kernels (`src/av1_cdef.cyr`, spec 7.15.2 +
7.15.3): the 8x8 direction/variance search, the `constrain` non-linearity, and
the primary/secondary tap filter that derings a block. All values cross-checked
against an independent Python model of 7.15.2/7.15.3. A 3-agent adversarial spec
review (constant tables / direction+constrain math / filter+memory-safety)
confirmed the tables and the math are **spec-exact with no correctness findings**;
two non-correctness findings are tracked, not silently accepted (see Notes).
**20,122 suite assertions + 1,140 fuzz assertions, all green — and `make lint`
is now genuinely green (see Fixed).**

### Added
- **AV1 CDEF kernels** (`src/av1_cdef.cyr`): `av1_cdef_direction` (7.15.2) — the
  8-direction `partial`/`cost` search returning `(yDir, var)`; `av1_cdef_constrain`
  (7.15.3) — the damped clamp-toward-zero non-linearity; `av1_cdef_filter`
  (7.15.3) — the per-8x8 tap filter (tapIdx = `(priStr>>coeffShift)&1`, primary
  along `dir` + secondary along `(dir±2)&7`, `is_inside_filter_region` gating,
  min/max clamp, `(8 + sum - (sum<0)) >>> 4` sign-preserving rounding) reading a
  source frame into a Cdef frame; the `Div_Table` / `Cdef_Pri_Taps` /
  `Cdef_Sec_Taps` / `Cdef_Directions` / `Cdef_Uv_Dir` tables (one cached blob).
- **Tests** (`tests/av1_cdef.tcyr`, 20 assertions): `constrain` known-answers;
  the direction search on flat / horizontal-gradient / vertical-gradient /
  diagonal blocks (Python-referenced `yDir`,`var`); the filter deringing a gentle
  spike (132 amid flat 128 → pulled to 128, neighbours to 129) and a flat-block
  no-op — all cross-checked against the independent Python model.

### Fixed
- **`make lint` is green again.** A 123-char line in `tests/av1_frame.tcyr`
  (`fx_seq_full`'s signature, introduced 2026-07-10) had been failing the lint
  gate (`make lint` exits non-zero on any `warn`) since the entropy-decoder work
  — wrapped by renaming the `en_restoration` param to `en_lr` in the paired
  `fx_seq_full`/`fx_seq_reduced` fixtures. Also cleared two `cyrlint` deferral
  hits that were **not** real deferrals: `src/vpx_bool.cyr:104` was an RFC-6386
  quote ("have not yet shifted out any bits") the linter matched on "not yet"
  (rephrased); `src/h264_ps.cyr:59` was a permanent design-scope note
  ("FMO out of scope") reworded to "FMO/ASO unsupported by design". No behavior
  change — comments/param-name only.

### Notes
- `drishti_version()` → 729. CDEF is underway: kernels this bite, the block
  process + outer loop (7.15.1) + `CdefFrame`/`cdef_idx` wiring next (0.7.30).
- **Review finding 1 (tracked, driver precondition):** the kernels index the
  full MI grid (up to `MiCols*4 x MiRows*4`), which can exceed FrameWidth/Height
  by up to 7 on non-mult-of-8 frames; since `dr_frame` get/set are unchecked, the
  0.7.30 driver MUST supply MI-aligned planes or border >= 7 with populated
  padding. Documented as a precondition in `av1_cdef.cyr` + `roadmap.md`; not
  triggerable by the current (MI-aligned) tests.
- **Review finding 2 (systemic, not CDEF-specific):** the per-block scratch
  `alloc`s use the bump allocator with no per-call free — but this is the
  codebase-wide pattern (`av1_recon` allocs far more per transform block), so it
  is an arena-strategy question deferred to the audit arc (roadmap.md), not a
  CDEF defect.

## [0.7.28] - 2026-07-11

Completes the AV1 **deblocking loop filter**: the edge loop + main driver (spec
7.14.1/7.14.2) that walk a reconstructed frame's 4x4 boundaries and apply the
0.7.27 kernels, plus the `LoopfilterTxSizes` grid they consume. A whole
keyframe's block/transform boundaries are now deblocked in place. A 2-agent
adversarial spec review (edge-loop/driver fidelity, LoopfilterTxSizes write +
hostile-frame safety) confirmed it with **no findings**. **20,102 suite
assertions + 1,140 fuzz assertions, all green.**

### Added
- **AV1 deblocking edge loop + driver** (`src/av1_deblock.cyr`): `av1_lf_edge`
  (7.14.2) derives the edge geometry (dx/dy, onScreen, the `row|subY`/`col|subX`
  adjustment, xP/yP, prevRow/prevCol), the `isBlockEdge`/`isTxEdge`/`applyFilter`
  decision, the filter size + strength, and applies the sample filter to the
  edge's `MI_SIZE` samples; `av1_deblock` (7.14.1) is the main loop (all vertical
  boundaries then all horizontal, per plane) that modifies the `DrFrame` in place.
- **LoopfilterTxSizes grid** (`src/av1_residual.cyr`): 3 per-plane grids on the
  `Av1Tile` (allocated by `av1_tile_grids_new`, `av1_lftx_get/set`), written per
  tx block in `transform_block` (clamped to the plane extent) — the transform-size
  record the deblocker reads for the tx-edge / filter-size decisions.
- **Tests** (`tests/av1_deblock.tcyr`, +8 → 54 assertions): a whole-frame deblock —
  a vertical block boundary (100/140 step) is wide-filtered to the known result
  (125 / 105) across every row, with samples away from the edge and the frame-left
  boundary untouched; and a `loop_filter_level = 0 → no-op` case.

### Notes
- `drishti_version()` → 728. The deblocking filter is complete (kernels 0.7.27 +
  loop 0.7.28). Next in the in-loop filter layer: CDEF (7.15), then loop
  restoration (7.17); after that, inter prediction and conformance.

## [0.7.27] - 2026-07-11

Starts the AV1 **in-loop filter** layer (the first item toward AV1 100% after
the intra keyframe milestone): the **deblocking loop-filter kernels** (spec
7.14.3-7.14.6). A new `src/av1_deblock.cyr` implements the correctness-critical
pixel math — the filter-size / strength / limit derivations and the sample
filters (mask, narrow 4-tap, wide low-pass) that smooth block/transform-boundary
artifacts. During implementation an arithmetic-shift bug was caught and fixed
(the narrow filter's `filter1`/`filter2` must use the sign-preserving `>>>` — a
logical `>>` corrupts the frequently-negative intermediate when the q side is
darker); the 2-agent adversarial review independently flagged the same shift and
its verifier confirmed the fix in place, with no surviving findings. **20,094
suite assertions + 1,140 fuzz assertions, all green.**

### Added
- **AV1 deblocking filter kernels** (`src/av1_deblock.cyr`, new flat module):
  `av1_lf_filter_size` (7.14.3), `av1_lf_strength` (7.14.5 level selection —
  `loop_filter_level` + ref/mode deltas), `av1_lf_limits` (7.14.4 limit/blimit/
  thresh from lvl + sharpness), `av1_lf_mask` (7.14.6.2 hev/filter/flat/flat2
  masks), `av1_lf_narrow` (7.14.6.3 the 4-tap filter), `av1_lf_wide` (7.14.6.4
  the 8/14-tap low-pass), and `av1_lf_sample` (7.14.6.1 the mask → narrow/wide
  dispatch). All operate on a reconstructed `DrFrame` at (x,y) along a
  perpendicular direction (dx,dy).
- **Tests** (`tests/av1_deblock.tcyr`, 46 assertions): hand-computed
  known-answers for every kernel — the size/limits/strength arithmetic, a
  step-edge through the narrow filter (both `hev` values **and** a reversed
  darker-q step exercising the negative-`filter` arithmetic-shift path), the
  wide filter's DC-preserving unity gain + a step, the mask (flat / big-jump /
  high-variance) and the dispatch (narrow route + filterMask-0 no-op).

### Fixed
- **Logical→arithmetic shift in the narrow deblock filter** (caught during
  0.7.27 implementation, independently flagged by the review): `filter1`/`filter2`
  now use `>>>` (sign-preserving), matching spec 7.14.6.3's arithmetic `>>3` and
  the `av1_round2` convention.

### Notes
- `drishti_version()` → 727. Next (0.7.28): the deblocking edge loop + main driver
  (7.14.1/2) + the `LoopfilterTxSizes` grid, wiring these kernels into a
  whole-frame deblock; then CDEF and loop restoration.

## [0.7.26] - 2026-07-11

Closes the last correctness gap in the intra keyframe **prediction**: the intra
edge-filter type. `get_filter_type` (spec 7.11.2.8) is now derived from the
neighbour intra modes (the `YModes` / `UVModes` MI grids) and fed to the intra
edge-filter strength / upsample selection — previously it was hard-coded to 0, a
refinement deferred through the block-decode arc. A 2-agent adversarial spec
review (fidelity — incl. the chroma subsampling neighbour-position math — and
wiring/safety) confirmed it with **no findings**. **20,048 suite assertions +
1,140 fuzz assertions, all green.**

### Added
- **AV1 intra edge-filter type** (`av1_get_filter_type` / `av1_is_smooth_neighbour`
  in `src/av1_residual.cyr`, spec 7.11.2.8): returns 1 iff the block above or to
  the left uses a SMOOTH prediction mode (SMOOTH / SMOOTH_V / SMOOTH_H), reading
  the neighbour `YModes` (luma) / `UVModes` (chroma) grids with the correct
  chroma subsampling neighbour-position adjustments. `transform_block` now derives
  it per plane and passes it to `av1_intra_predict` (the `AV1BLK_FILTER_TYPE`
  block field is retired to reserved).
- **Tests** (`tests/av1_residual.tcyr`, +9 → 28 assertions): `get_filter_type`
  known-answers (luma above/left/neither/no-avail), a 420-chroma test asserting it
  reads the *subsampling-adjusted* neighbour position (not the raw one), and a
  proof that `filter_type` changes a directional (D67 + angle-delta) prediction —
  cross-checked against the edge-filter strength (`(8,8,0,20)=0` vs `(8,8,1,20)=1`).

### Notes
- `drishti_version()` → 726. The intra keyframe prediction is now
  conformance-faithful (no more hard-coded edge-filter type). Next toward AV1
  100%: the inter + in-loop-filter layer, conformance / 10-bit, and the
  encode-lane completion.

## [0.7.25] - 2026-07-11

**MILESTONE — the first fully decoded AV1 keyframe.** Bite 7 closes the AV1
**block/partition decode** arc (and the intra still-picture decode milestone):
a new `src/av1_tile.cyr` implements `decode_tile` (spec 5.11.2) + the
tile_group_obu CDF/symbol wiring, driving `decode_partition` over every 64x64
superblock of a tile into a `DrFrame`. Every 0.7.x AV1 primitive now composes —
entropy coder, adaptive CDF contexts, the partition tree, mode-info, tx-size,
and the residual driver (predict → coeffs → reconstruct) — so a keyframe tile
decodes **end-to-end to pixels**. A 4-agent adversarial spec review (SB loop,
CDF/symbol/qbucket wiring, clear-context, encode-symmetry + safety) confirmed it
with **no findings**. **20,039 suite assertions + 1,140 fuzz assertions, all
green.**

### Added
- **AV1 tile / frame loop** (`src/av1_tile.cyr`, new flat module): `av1_decode_tile`
  runs `clear_above_context`, then per superblock row `clear_left_context` and per
  superblock `clear_block_decoded_flags` + `decode_partition(BLOCK_64X64)`.
  `av1_decode_intra_tile` is the keyframe entry point — it builds the per-tile
  adaptive CDF contexts (`init_non_coeff_cdfs` / `init_coeff_cdfs` with the
  `base_q_idx` quantizer bucket via `av1_coeff_cdf_qbucket`) and the symbol
  decoder (`init_symbol`), runs `decode_tile`, and exits. The paired
  `av1_encode_tile` / `av1_encode_intra_tile` drive the encode lane so a keyframe
  tile round-trips.
- **Tests** (`tests/av1_tile.tcyr`, 20 assertions): `qbucket` + `clear_above/left`
  known-answers, and a **multi-superblock keyframe round-trip** — a 128x64 mono
  frame (2 superblocks; SB0 SPLIT into four 32x32, SB1 one 64x64; all skip DC)
  encoded then decoded through `decode_tile`, verifying the `MiSizes` grid matches
  the partition, the pixels, and encoder/decoder grid agreement, in **both**
  `disable_cdf_update` modes (proving frame-wide CDF adaptation in lockstep).

### Notes
- `drishti_version()` → 725. The **intra still-picture decode milestone is
  complete**: profile-0 keyframes decode to pixels. The block/partition decode
  arc (0.7.19-0.7.25) is closed. Next in 0.7.x: the inter + in-loop-filter layer
  (motion compensation, deblocking, CDEF, loop restoration, film grain) and the
  conformance / 10-bit / encode-lane completion toward AV1 100%.

## [0.7.24] - 2026-07-11

Bite 6 of the AV1 **block/partition decode** arc: the **partition tree**. A new
`src/av1_partition.cyr` implements `decode_partition` / `decode_block` (spec
5.11.4/5.11.5) — the recursive partition of a superblock into coding blocks,
and per block the orchestration mode_info → read_tx_size → residual() that ties
bites 2/3/5 together and writes the MI grids the neighbour contexts read — plus
the paired encode lane. A 5-agent adversarial spec review found **one real,
confirmed defect** — an unclamped MI-grid write that was an out-of-bounds heap
write for an edge coding block on a non-64-aligned frame — which is **fixed and
regression-tested** (the other 4 dimensions clean). **20,019 suite assertions +
1,140 fuzz assertions, all green.**

### Added
- **AV1 partition tree** (`src/av1_partition.cyr`, new flat module):
  `av1_decode_partition` reads the partition symbol (`av1_ncdf_partition_w8/16/32/64`
  by `bsl`, or the `split_or_horz` / `split_or_vert` binary CDF *synthesized*
  from the partition CDF) and recurses / dispatches all 10 partition types.
  `av1_decode_block` derives `HasChroma` + the availability flags, runs
  `intra_frame_mode_info` → `read_block_tx_size` → `residual()`, and writes the
  `MiSizes` / `YModes` / `Skips` / `InterTxSizes` grids. The paired
  `av1_encode_partition` / `av1_encode_block` (the block-orchestration entropy)
  make the tree round-trip. Tables: `Partition_Subsize[10][22]` (checksum-pinned);
  `is_inside`, the partition ctx, and `reset_block_context`. The `Av1Tile`
  context (`src/av1_residual.cyr`) grows the MI grids (`av1_tile_grids_new`).
- **Tests** (`tests/av1_partition.tcyr`, 216 assertions): `Partition_Subsize` /
  `is_inside` / partition-ctx known-answers; a **grid-write clamp regression**
  for the edge-overhang OOB; the partition + `split_or_horz/vert` symbol
  round-trips (all types / contexts); a single `decode_block` from a hand-built
  stream (verifying pixels + the MI grids); and a `decode_partition` round-trip
  on a 16x16 SPLIT → 4× 8x8 skip tree through the encode lane (grids agree,
  pixels are the flat DC value).

### Fixed
- **OOB heap write in the MI-grid write** (`av1_block_write_grids`, found by the
  0.7.24 adversarial review): a coding block that straddles the bottom/right edge
  of a non-superblock-aligned frame wrote past the `MiCols*MiRows` grids. The
  write is now clamped to the tile MI extent — spec-equivalent, since an overhang
  position is outside the frame and is never read as a neighbour (`is_inside` /
  the avail flags reject it), and it upholds the trust-no-input-byte rule.

### Notes
- `drishti_version()` → 724. The block/partition decode is complete end-to-end
  (a full partition tree round-trips). Next (bite 7, the arc's close): the
  tile/frame loop (`decode_tile` / tile_group) — clear_above/left, the superblock
  loop, the CDF-context init — driving into a `DrFrame` = the **first fully
  decoded keyframe**.

## [0.7.23] - 2026-07-11

Bite 5 of the AV1 **block/partition decode** arc — the composition milestone: a
transform block now decodes **end-to-end to pixels**. A new `src/av1_residual.cyr`
implements `residual()` / `transform_block()` (spec 5.11.34/36), driving
`predict_intra` → `coeffs()` → `reconstruct()` per transform block into a
`DrFrame`, with chroma-from-luma, the `BlockDecoded` availability grid, and the
`MaxLumaW/H` CfL extents. A 5-agent adversarial spec review (transform_block
orchestration, residual loop + get_tx_size, BlockDecoded + availability,
coordinate/subsampling math, hostile-input safety) confirmed it with **no
findings**. **19,803 suite assertions + 1,140 fuzz assertions, all green.**

### Added
- **AV1 residual driver** (`src/av1_residual.cyr`, new flat module): the intra
  keyframe residual composition. `av1_transform_block` predicts a tx block into
  the frame (`av1_intra_predict`, DC + `av1_predict_chroma_from_luma` for
  `UV_CFL_PRED`), then — unless `skip` — reads its coefficients (`av1_coeffs_decode`,
  which computes the `PlaneTxType` via the 0.7.22 seam) and, if `eob>0`, adds the
  reconstructed residual (`av1_reconstruct`). It manages the `BlockDecoded`
  availability grid (feeding `haveAboveRight`/`haveBelowLeft` to prediction) and
  the luma `MaxLumaW/H` that CfL reads. `av1_residual` drives `transform_block`
  over each plane's tx grid. `av1_get_tx_size` (spec 5.11.36) picks the per-plane
  tx size. The `Av1Tile` decode context (frame + entropy + per-tile constants +
  per-plane `BlockDecoded` / coeff level-context strips + reusable `Quant[]`
  scratch) and the `Av1Block` per-block record are populated by the tile/frame
  loop (bite 7).
- **Tests** (`tests/av1_residual.tcyr`, 19 assertions): `get_tx_size`
  known-answers; concrete checks — a DC-predicted skip block is all `2^(bd-1)`,
  the `BlockDecoded` grid + `MaxLumaW/H` are set, an all-zero (`eob 0`) block is
  prediction-only, a 3-plane 420 block predicts all planes, a CfL block on flat
  luma is a no-op; and a driver-vs-manual consistency check on the reconstruct
  path (predict + coeffs + reconstruct producing matching pixels, with a verified
  nonzero residual).

### Notes
- `drishti_version()` → 723. A transform block reconstructs to pixels through the
  driver. Next in the block-decode arc (bite 6): `decode_partition` / `decode_block`
  (5.11.4/5.11.5) — the partition symbol + split_or_horz/vert edge CDFs +
  `Partition_Subsize`, writing the `MiSizes` grid and calling mode-info →
  tx-size → residual per block; then the tile/frame loop = a decoded keyframe.

## [0.7.22] - 2026-07-11

Bite 4 of the AV1 **block/partition decode** arc — the trickiest seam: the
**transform-type derivation** (`compute_tx_type`) spliced INTO the coeffs loop.
A new `src/av1_txtype.cyr` reads the `intra_tx_type` symbol (between `all_zero`
and the eob position, for a luma block) and derives each transform block's
`PlaneTxType`, retiring it as a caller input to `av1_coeffs_decode`/`_encode`.
A 5-agent adversarial spec review (transform_type fidelity, compute_tx_type /
get_tx_set, per-value tables, the coeffs splice + Tx_Size_Sqr move, hostile-input
safety) confirmed the change with **no findings**. **19,784 suite assertions +
1,140 fuzz assertions, all green.**

### Added
- **AV1 transform-type derivation** (`src/av1_txtype.cyr`, new flat module):
  `av1_get_tx_set` (spec 5.11.48, intra + inter branches), `transform_type`
  decode + inverse encode (reads/writes `intra_tx_type` via the Set1/Set2 CDFs,
  ctx = `[Tx_Size_Sqr][intraDir]` where `intraDir` is the filter-intra dir or
  `YMode`), and `compute_tx_type` (spec 5.11.40: Lossless/large-tx → DCT_DCT,
  luma passthrough, chroma `Mode_To_Txfm[UVMode]` gated by set membership). New
  tables `Mode_To_Txfm` / `Tx_Type_Intra_Inv_Set1/2` / `Tx_Type_In_Set_Intra` /
  `Filter_Intra_Mode_To_Intra_Dir` (79-entry blob, checksum-pinned) + the
  `Av1TxTypeCtx` per-block record.
- **Tests** (`tests/av1_txtype.tcyr`, 142 assertions): tables, `get_tx_set`
  known-answers (intra/inter/reduced), `compute_tx_type` (luma/chroma/lossless/
  large-tx/not-in-set gating), and `transform_type` decode/encode round-trips
  over every Set1 (7) and Set2 (5) tx type — with both raw-`YMode` and
  filter-intra `intraDir` — in both `disable_cdf_update` modes, plus an adaptive
  multi-block round-trip.

### Changed
- **coeffs seam** (`src/av1_coeffs.cyr`): `av1_coeffs_decode`/`_encode` no longer
  take `PlaneTxType` — decode reads `transform_type` (a luma block) + derives
  the tx type via `compute_tx_type` and returns it via an out pointer; encode
  takes the target luma tx type and writes the matching `intra_tx_type`. Both now
  take the non-coeff CDF context (`ncc`, for `intra_tx_type`) alongside `cc` and
  an `Av1TxTypeCtx`. Downstream coefficient reading is unchanged; the existing
  round-trips hold (DCT_DCT blocks with `base_q_idx = 0` produce a byte-identical
  stream). The V_DCT case is now a genuine `intra_tx_type` round-trip.
- **Tx_Size_Sqr tables** moved from `av1_coeffs.cyr` to `av1_txsize.cyr`
  (`av1_tx_size_sqr` / `_up` / `_ctx`) — they are tx-size properties and
  `get_tx_set` needs them. The include order now places `av1_txtype` before
  `av1_coeffs`.

### Notes
- `drishti_version()` → 722. A transform block now decodes with its **own**
  computed transform type. Next in the block-decode arc (bite 5): the residual
  driver (`residual()` / `transform_block()`, 5.11.34/35) — per tx block:
  predict_intra → coeffs() → reconstruct() — then the partition tree and the
  tile/frame loop toward a decoded keyframe.

## [0.7.21] - 2026-07-11

Bite 3 of the AV1 **block/partition decode** arc: the intra **transform-size
read**. A new `src/av1_txsize.cyr` implements `read_tx_size` (spec 5.11.15) —
the `tx_depth` symbol that splits a keyframe block's `Max_Tx_Size_Rect` down
toward `TX_4X4` — as a decode function AND its exact-inverse encoder,
round-trip tested through the symbol coder. A 4-agent adversarial spec review
(read_tx_size fidelity, the tx_depth ctx + cdf-family dispatch, per-value
table diff, hostile-input safety) confirmed it with **no findings**. **19,635
suite assertions + 1,140 fuzz assertions, all green.**

### Added
- **AV1 intra transform-size read** (`src/av1_txsize.cyr`, new flat module):
  `av1_read_tx_size` returns a keyframe block's luma `TxSize` — `Lossless`
  forces `TX_4X4`; otherwise it starts at `Max_Tx_Size_Rect[MiSize]` and, when
  `MiSize > BLOCK_4X4 && allowSelect && TxMode == TX_MODE_SELECT`, reads
  `tx_depth` and applies `Split_Tx_Size` that many times. The `tx_depth`
  CDF-selection context (`av1_tx_depth_ctx`, `(aboveW>=maxTxW)+(leftH>=maxTxH)`
  from the neighbour tx widths/heights) and the `maxTxDepth → Tx8/16/32/64`
  cdf-family dispatch (spec 9.3) consume the 0.7.19 tx-size CDFs. Paired
  `av1_write_tx_size` derives `tx_depth` back from the target `TxSize` (exact
  inverse). The inter `read_var_tx_size` tree and the `InterTxSizes` grid write
  are deferred to later bites — `read_tx_size` returns the `TxSize`; the caller
  fills the grid.
- **AV1 tx-size tables** (same module): `Max_Tx_Size_Rect[22]`,
  `Max_Tx_Depth[22]`, `Split_Tx_Size[19]` (63-entry blob, checksum-pinned) +
  `av1_tx_width`/`av1_tx_height` (from the `av1_itx` log2 tables).
- **Tests** (`tests/av1_txsize.tcyr`, 169 assertions): the table checksum +
  spot values, `tx_depth` ctx known-answers, `read_tx_size`/`write_tx_size`
  round-trips over every reachable `TxSize` across all four `maxTxDepth`
  categories (Tx8/16/32/64) and rectangular blocks in **both**
  `disable_cdf_update` modes, the no-symbol forced cases (lossless / 4x4 /
  non-select / no-allowSelect), and an adaptive multi-block round-trip.

### Notes
- `drishti_version()` → 721. Next in the block-decode arc (bite 4):
  `compute_tx_type` spliced into the coeffs decode/encode (reads `intra_tx_type`
  via the Set1/Set2 CDFs, `get_tx_set`, `Mode_To_Txfm`), then the residual
  driver, the partition tree, and the tile/frame loop.

## [0.7.20] - 2026-07-11

Bite 2 of the AV1 **block/partition decode** arc: the intra **mode-info
reads**. A new `src/av1_modeinfo.cyr` implements the intra branch of
`intra_frame_mode_info()` (spec 5.11.16) — the per-block mode syntax that
consumes the 0.7.19 non-coeff CDFs — as decode functions AND their
exact-inverse encoders, round-trip tested through the symbol coder. A
5-agent adversarial spec review (syntax/read-order fidelity, CDF-selection
contexts, per-value block-table diff, encode/decode inversion, hostile-input
safety — each cross-checked against the spec markdown) confirmed it with **no
findings**. **19,466 suite assertions + 1,140 fuzz assertions, all green.**

### Added
- **AV1 intra mode-info reads** (`src/av1_modeinfo.cyr`, new flat module):
  `read_skip`, `intra_frame_y_mode` (above/left `Intra_Mode_Context`
  neighbour ctx), `intra_angle_info_y`, `uv_mode` (the Lossless /
  `Max(BW,BH)<=32` CfL-allowed cdf selection), `read_cfl_alphas` (joint sign
  + per-sign magnitude), `intra_angle_info_uv`, and `filter_intra_mode_info`
  — each with its exact CDF-selection context (spec 9.3) and a paired encode
  function. The `av1_intra_frame_mode_info_decode` / `_encode` orchestrator
  drives them in spec read-order into an `Av1ModeInfo` record. Feature-gated
  reads (segmentation, cdef, delta-q/lf, intrabc, palette) are deferred to
  later bites and elided.
- **AV1 block-size conversion tables** (same module): `Mi_Width/Height_Log2`,
  `Num_4x4_Blocks_Wide/High`, `Block_Width/Height`, `Size_Group`,
  `Intra_Mode_Context`, and `Subsampled_Size` + `get_plane_residual_size`
  (211-entry blob, pinned by a position-weighted checksum) — the shared
  block-geometry lookups the tx-size / partition / residual-driver bites reuse.
- **Tests** (`tests/av1_modeinfo.tcyr`, 310 assertions): the block-table
  checksum + spot values, `get_plane_residual_size` / `cfl_allowed`
  known-answers, every CDF-selection context, seven mode-info round-trip
  scenarios (DC+CfL+filter-intra, directional Y/UV angle deltas, all valid
  CfL sign combinations, no-chroma, the 4x4 no-angle gate, allowed-but-unused
  filter-intra, CfL-not-allowed uv_mode) each in **both** `disable_cdf_update`
  modes, plus an adaptive multi-block round-trip sharing one CDF context.

### Notes
- `drishti_version()` → 720. Next in the block-decode arc (bite 3): the
  tx-size reads (`read_tx_size` / `tx_depth` + its ctx and the
  `Max_Tx_Size_Rect` / `Max_Tx_Depth` / `Split_Tx_Size` tables), then
  `compute_tx_type`, the residual driver, the partition tree, and the
  tile/frame loop — toward a fully decoded keyframe.

## [0.7.19] - 2026-07-11

Opens the AV1 **block/partition decode** arc (the final stretch to a
decoded keyframe) with its first, foundational bite: the default
non-coefficient CDF tables. A 7-bite decomposition of the block decode
was mapped by a multi-agent scoping pass; this is bite 1 — the data every
downstream read consumes. A 3-agent adversarial review (per-table diff,
accessor offsets, libaom cross-check) confirmed all values with no
defects. **19,156 suite assertions + 1,140 fuzz assertions, all green.**

### Added
- **AV1 default non-coefficient CDF tables** (`src/av1_noncoeffcdf.cyr`,
  new flat module): the 19 initial adaptive-CDF tables the intra-keyframe
  block decode reads — partition (W8/16/32/64), skip, intra-frame Y mode,
  UV mode (CfL-allowed + not-allowed), angle-delta, CfL sign/alpha,
  filter-intra (use + mode), tx-size (8/16/32/64), and intra tx-type
  (set1/set2) — **1,622 entries** in one lazily-built blob with per-family
  accessors. `av1_ncdf_new` copies the whole blob into a mutable per-tile
  context (no quantizer bucket, unlike the coeff CDFs). 1,820 assertions:
  a weighted blob checksum, a structural sweep validating every CDF via
  its accessor, an identity-copy check, known values, and offset
  arithmetic. (128x128-superblock / segment / delta-q / palette / intrabc
  CDFs are feature-gated for later bites.)

### Notes
- `drishti_version()` → 719. Next in the block-decode arc: the mode-info
  reads (intra y/uv/CfL/angle/filter-intra) that consume these CDFs, then
  tx-size/tx-type, the residual driver, the partition tree, and the
  tile/frame loop — toward a fully decoded keyframe.

## [0.7.18] - 2026-07-11

Adds the adaptive coefficient-CDF context, so the `coeffs()` decode now
works with CDF adaptation **on** (`disable_cdf_update = 0`, the common
case for real streams) — not just the read-only mode. A 3-agent
adversarial review (copy/accessor offsets, refactor completeness +
adaptation lockstep, libaom cross-check) confirmed it with no defects.
**17,336 suite assertions + 1,140 fuzz assertions, all green.**

### Added
- **Adaptive coeff-CDF context** (`src/av1_coeffs.cyr`): `av1_ccdf_new(q)`
  allocates a mutable per-tile buffer and copies one quantizer bucket's
  worth of all 7 default coefficient CDF families into it (mirroring
  `init_coeff_cdfs`), with `av1_ccdf_*` accessors. `av1_coeffs_decode` /
  `av1_coeffs_encode` now take this context (instead of a bare `q`) and
  hand its mutable CDF pointers to the symbol coder, which adapts them in
  place when adaptation is on. The read-only path (`disable_cdf_update = 1`)
  still works — it simply skips the in-place update. New assertions: a
  direct byte-for-byte check that a fresh context equals the defaults for
  all 4 buckets, an adaptive single-block round-trip, and an **adaptive
  multi-block round-trip** (two blocks sharing one context — block 2
  decodes correctly only because encode/decode adapt in lockstep).

### Notes
- `drishti_version()` → 718. Coefficient decode now handles both CDF
  modes. Next toward a decoded keyframe: the block/partition decode —
  mode-info reads (intra/uv/CfL modes + their CDFs), `compute_tx_type`,
  the partition tree, and the tile/frame wiring.

## [0.7.17] - 2026-07-11

**A transform block decodes end-to-end.** The AV1 `coeffs()` reading loop
(spec 5.11.39) in a new `src/av1_coeffs.cyr` module ties together the
scan orders, the level + txb_skip/dc_sign contexts, all seven default
CDFs, and the symbol coder — so encoded coefficient bytes now round-trip
to a `Quant[]` array. A 4-agent adversarial review (decode conformance,
encode symmetry, per-symbol CDF/context selection, libaom + edge cases)
surfaced one real DoS-hardening gap (an unbounded golomb length loop),
which is fixed. **13,920 suite assertions + 1,140 fuzz assertions, all
green.**

### Added
- **AV1 coefficient reading loop** (`src/av1_coeffs.cyr`, new flat
  module): `av1_coeffs_decode` reads one transform block's coefficients
  (all_zero, the eob position via `eob_pt` + `eob_extra`, the base levels,
  the `coeff_br` range extension, the signs, and the Exp-Golomb tail) from
  the symbol decoder into `Quant[]` and returns eob; `av1_coeffs_encode`
  is its exact inverse. Plus the remaining CDF-selection contexts
  (`av1_txb_skip_ctx`, `av1_dc_sign_ctx`), the `txSzCtx` derivation, and
  the `Tx_Size_Sqr` / `Tx_Size_Sqr_Up` tables. Scope: `PlaneTxType` is a
  caller input and the CDFs are read-only (`disable_cdf_update` mode); the
  adaptive per-tile CDF copy and `compute_tx_type` land in later bites.
  428 assertions: the contexts by hand-computed known-answers, and the
  decode/encode pair by **round-trip** across mixed 4x4 / 8x8 / 16x16 /
  chroma / 1D-transform blocks (base, br, golomb, signs, interior zeros,
  all-zero) plus a truncation-terminates check.

### Fixed
- **Unbounded Exp-Golomb length loop** in the coefficient decode: a
  truncated/hostile stream whose exhausted symbol reader returns padding
  without latching an error could loop forever. The unary length is now
  capped (a valid coefficient is <= 20 bits), matching libaom's guard —
  honouring the never-hang rule. Found by the adversarial review.

### Notes
- `drishti_version()` → 717. Next: the block/partition decode (mode info +
  `compute_tx_type` + the adaptive CDF context) that drives `coeffs()` +
  predict + reconstruct per block, toward a fully decoded keyframe.

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
