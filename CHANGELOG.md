# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.7.93] - 2026-07-17

**WARP ESTIMATION (local warp model).** The least-squares solve (spec 7.11.3.8) that turns the
`find_warp_samples` candidate list into a LOCAL warp model — the 6-parameter affine `LocalWarpParams[0..5]`
plus a `LocalValid` flag — for a LOCALWARP-motion inter block. This is the direct consumer of the warp-sample
leaves landed at 0.7.79, and the first half of the warp arc. Like `setup_global_mv`, it is a pure
DERIVATION (no bitstream symbol → no encoder inverse) and is not yet wired to the pixel path; LOCALWARP
motion stays gated until the warp-MC bite (which needs the warp-filter table). The bite also lands the
`resolve_divisor` (7.11.3.7) reciprocal primitive + the lazy `Div_Lut[257]` table it needs.

### Added

- **`av1_div_lut_tbl` + `av1_resolve_divisor`** (spec 7.11.3.7) in `av1_mv.cyr`: the 257-entry rounded-
  reciprocal `Div_Lut[i] = round(2^22 / (256+i))` (lazily generated — anchored on `Div_Lut[0]=16384=2^14`
  and `Div_Lut[256]=8192=2^13`, exact because no tie ever occurs), and `resolve_divisor(D)` returning
  `(divShift = FloorLog2(|D|)+14, divFactor = ±Div_Lut[f])` with `f ∈ [0,256]` bounds-guarded.
- **`av1_warp_estimation`** (spec 7.11.3.8): accumulates the symmetric 2×2 `A` matrix + `Bx`/`By` vectors
  over the samples (the `LS_SQUARE`/`LS_PRODUCT1`/`LS_PRODUCT2` Tikhonov-regularized macros — arithmetic
  `>>>` on the signed product numerators), rejects per-sample motion outliers via the `LS_MV_MAX` guard,
  and — when the determinant is non-zero (the sole `LocalValid=0` exit) — solves the 2×2 by Cramer scaled
  through `resolve_divisor`, clamping the diagonal params near `1<<16` and the off-diagonal near 0, then
  derives the translation `wmmat[0..1]` (anchored at the block center, `±2^23`-clamped). The CandList is
  already 1/8-pel, so no extra scaling is applied. **4-source reconciled** (spec + libaom + dav1d + a
  focused divisor pass → adjudication); the spec-literal oracle is `scripts/refs/warp_estimation_ref.py`.
- **`Av1WarpModel`** record (`av1_warp_model_new`/`_valid`/`_param`) carrying the valid flag + `wmmat[0..5]`.

**Deferred** (NOT implemented — un-witnessable by a self-consistent test, so deferred to a conformance-vector
bite per the project discipline, roadmap "warp"): the libaom `LS_MAT_MIN/MAX` accumulator clamp (existence
+ exact bounds unverified across sources) and the shear-realizability rejection (`get_shear_params`, a
SEPARATE process ~7.11.3.6 run AFTER estimation).

**Proofs** (`tests/av1_mv.tcyr`): `Div_Lut` pinned by 9 anchored spot values + a full 257-entry
sum/position-weighted-checksum digest (defeats a circular per-entry accessor test); `resolve_divisor`
driven over `2^n−1 / 2^n / 2^n+1` boundaries (witnessing `f=0`, `f=256`, and a negative `D`); and 13
`warp_estimation` KATs vs the ref port — identity/translation, a clean 4-distinct-param affine, the
`LS_MV_MAX` guard (both the horizontal AND vertical conjuncts), all four clamp bounds (diag 57345/73727,
non-diag ±8191), the `divShift<0` rescale branch (a `det=1` single sample), the ±2^23 translation clamp,
a single-sample and a small negative-product case (which cleanly witness the arithmetic shift + the signed
rounding), and `det==0 → invalid`. **Mutation-verified — 16 mutations killed** across the Div_Lut rounding,
the resolve_divisor shift/branch, every LS macro, the Cramer products, both clamp bounds, the guard, the
translation anchor, the invalidation, and the signed rounding; the lone survivor is a provably-equivalent
`>`-vs-`>=` at the `n=8` divisor branch (`e<<0 == Round2(e,0) == e`). A pitfall the mutation loop caught:
symmetric 4-sample vectors masked the arithmetic-shift + signed-rounding bugs via an i64-overflow
coincidence — added a single-sample + a small 2-sample case that witness them cleanly.

**The adversarial review (3 dimensions, worktree-isolated, patch-applied, every finding verified):** the
fixed-point math + memory-safety CLEAN — no correctness or bounds findings. Three MINOR test-coverage gaps
found + closed (all with the shipped code confirmed spec-correct): the `divShift<0` branch, the `LS_MV_MAX`
vertical conjunct, and the translation-clamp bound MAGNITUDE were each un-witnessed by the original KATs;
new KATs (K/CV/TC) now fail red under the corresponding mutation.

## [0.7.92] - 2026-07-17

**WEDGE INTER-INTRA PREDICTION.** The second (and final) interintra variant: a single-reference inter block
carrying the interintra flag with `wedge_interintra==1` now blends its inter motion-compensated prediction
with an INTRA prediction through a **wedge** mask drawn from the compound wedge codebook (0.7.90), rather than
the smooth mask (0.7.91). This completes the masked-interintra family — every AV1 interintra mode now decodes.
The delta over 0.7.91 is small and reuses verified machinery: the wedge codebook (`av1_wedge_mask_build`,
288-checksum-verified) and the final-precision interintra blend both stand unchanged.

### Added

- **The wedge branch of `av1_mc_pred_interintra`** (spec 7.11.3.11 mask, 7.11.3.13 blend), extended with
  `is_wedge`/`wedge_idx` params: WEDGE builds the codebook mask on **LUMA only** (plane 0) at the NOMINAL
  block size with `wedge_sign` forced 0 (interintra never signals a sign); **chroma SUBSAMPLES the plane-0
  mask** via `av1_diffwtd_mask_at` — exactly like compound wedge, and **unlike** SMOOTH interintra, which
  regenerates the mask at each plane's dims. The blend is the same FINAL-precision `Round2(m·intra +
  (64−m)·inter, 6)` — no `ib`, no `Clip1` — reused verbatim from 0.7.91. **3-source verified**
  (`interintra.md` §3).
- **The decode/encode un-gate**: both lanes now admit WEDGE interintra (the `wedge_interintra==0` rejection
  is removed from both gates); the frame-edge overhang + non-SIMPLE motion rejects stay, and the gates still
  mirror. The decode dispatch threads `av1_interintra_wedge` + `av1_interintra_wedge_idx` into the MC call
  (`wedge_idx` is entropy-bounded to [0,15] by a 16-symbol CDF → `shape·16 + wedge_idx ∈ [0,47]` never OOBs
  the 48-entry codebook).

**Proofs** (`tests/av1_mc_driver.tcyr`, `tests/av1_intertile.tcyr`): a LUMA orchestration test that builds
the wedge mask INDEPENDENTLY (`av1_wedge_mask_build`), MCs a gradient ref at integer MV 0, invokes
`av1_intra_predict` into a temp frame, and recomputes the blend — catching a wrong mask/shift/operand
without sharing the MC blend; a 4:2:0 CHROMA orchestration case whose oracle 2×2-averages the luma wedge mask
MANUALLY (independent of `av1_diffwtd_mask_at`), run over both a row-invariant VERTICAL wedge (idx6) AND an
OBLIQUE wedge (idx1 = O63, whose transition band crosses the bottom-right quadrant) so the `plane==0`
build-guard is witnessed; and a decode round-trip (32×32 via SPLIT, WEDGE idx0/idx6) equal to the oracle AND
differing from pure-inter. **Mutation-verified — 0 survivors**: the `is_wedge` mask-build branch, the
subsampled chroma read, the forced `wedge_sign`, the decode-dispatch wedge threading, and the `plane==0`
build guard each go red.

**The adversarial review (worktree-isolated, patch-applied):** the wedge-interintra delta CLEAN — the
mask-build/chroma-subsample branches match their read branches, plane-0-before-chroma ordering is guaranteed
by the decode plane loop (and `Av1_McMask` survives the intervening intra/inter calls), the gates mirror and
the codebook index is bounded, and SMOOTH interintra is unregressed. No correctness or memory-safety
findings. One mutation-coverage gap flagged and closed: the sole chroma case (idx6) is a row-invariant
wedge whose constant bottom-right quadrant lets an erroneously-rebuilt-at-chroma mask reproduce the correct
subsamples — the added oblique idx1 case makes the `plane==0` guard fail red under mutation.

## [0.7.91] - 2026-07-17

**SMOOTH INTER-INTRA PREDICTION.** A single-reference inter block carrying the interintra flag now blends
its inter motion-compensated prediction with an INTRA prediction of the same block, per pixel, through a
smooth mask. Unlike the compound modes (two inter predictions blended at intermediate precision), inter-intra
crosses the inter/intra boundary — the win is that drishti's keyframe intra predictor is invoked, unchanged,
from the inter tile path. Scope is SMOOTH interintra (the four `II_DC/V/H/SMOOTH` modes); WEDGE interintra
is deferred to 0.7.92, and a frame-edge overhang is refused (the intra predictor writes the nominal block).

### Added

- **The intra-mode variant (SMOOTH) mask** (spec 7.11.3.13) in `av1_mc.cyr`: `av1_ii_weight` (the 128-entry
  `Ii_Weights_1d` monotone 60..1 table, lazy) + `av1_ii_smooth_mask_build` — `sizeScale = 128/Max(w,h)`,
  per mode `II_DC`=flat 32, `II_V`=row-indexed `Ii_Weights[i·scale]`, `II_H`=col-indexed `[j·scale]`,
  `II_SMOOTH`=`[Min(i,j)·scale]`. The mask weights the INTRA prediction. **3-source verified**
  (`interintra.md`). **Chroma REGENERATES the mask at the chroma block size (not subsampled from luma)** —
  a cross-source discrepancy resolved by a numeric proof in favor of spec+libaom (a 4:2:0 32×32 V-mode
  chroma row-0 weight is 60, not the 56 an average would give).
- **`av1_mc_pred_interintra`**: one plane of an interintra block — the inter MC runs into `Av1_McOut` at
  FINAL pixel precision (`av1_mc_pred_core` with `compound=0`), `av1_intra_predict` writes the intra
  prediction into the frame (mode-mapped: `II_SMOOTH`→`SMOOTH_PRED`), then the blend reads the intra back
  and combines `Round2(m·intra + (64−m)·inter, 6)`. **No `ib` term, no `Clip1`** — both operands are already
  at pixel precision and a convex combination stays in range (this differs from the compound `ib+6`/`Clip1`
  combine — reusing it would corrupt every pixel).
- **The decode/encode un-gate**: both lanes now admit SMOOTH interintra (`ref1==INTRA` &&
  `wedge_interintra==0` && non-overhang); WEDGE interintra + non-SIMPLE motion stay refused.

**Proofs** (`tests/av1_mc_driver.tcyr`, `tests/av1_intertile.tcyr`): the smooth mask against a 28-checksum
pin over every size × mode vs the new spec-literal `scripts/refs/interintra_ref.py`; an orchestration test
that runs `av1_intra_predict` INDEPENDENTLY into a temp frame, MCs a gradient ref at integer MV 0
(inter == ref pixel), and recomputes the blend with the ref-verified mask — catching a wrong blend
shift/clip/operand-order without sharing `av1_mc_pred_interintra`'s blend; a 4:2:0 CHROMA orchestration
case witnessing regeneration (not subsampling); and a decode round-trip (32×32 via SPLIT, DC/V/SMOOTH) equal
to the oracle AND differing from pure-inter. **Mutation-verified — 0 survivors**: the blend shift, operand
order, mode remap, chroma regeneration, and the inter-precision (`compound=0`) die in the driver's
INDEPENDENT orchestration oracle (the round-trip shares `av1_mc_pred_interintra`); the decode dispatch dies
in the round-trip.

**The adversarial review (2 dimensions, worktree-isolated, patch-applied):** mask+blend+mode math CLEAN
(Ii_Weights + V/H orientation + chroma regeneration + blend precision + mode remap all verified against an
independent reference + mutation); intra-invocation + gate + memory-safety CLEAN (the `av1_intra_predict`
arg positions + neighbor-availability wiring correct, the intra-then-inter-then-blend ordering has no
clobber, the overhang gate proven sufficient incl. chroma, buffers bounded). One CONFIRMED finding fixed:
(F1) the encode gate mirrored the wedge + motion rejects but not the decode's OVERHANG reject — an
overhanging interintra block would encode but decode-reject; the encode gate now mirrors it in full.

## [0.7.90] - 2026-07-17

**COMPOUND WEDGE (MASKED) INTER PREDICTION.** The second masked compound mode: a two-reference block with
`comp_group_idx == 1` and `compound_type == COMPOUND_WEDGE` blends its two predictions through a per-pixel
mask drawn from a WEDGE CODEBOOK (an oriented soft boundary), indexed by block size + `wedge_index` +
`wedge_sign`. It reuses the 0.7.89 DIFFWTD mask-blend + chroma subsample unchanged; the new piece is the
mask codebook + its 2D generation. This closes the masked-compound family — both DIFFWTD and WEDGE are now
in scope; only inter-intra (a separate `ref1 == INTRA` path) remains gated.

### Added

- **The wedge master masks + codebook** (spec 7.11.3.11) in `av1_mc.cyr`: three 1-D master ramps
  (`av1_wm_odd/even/vert`, 0..64), lazily expanded into a `6 × 64 × 64` master blob (`av1_wedge_master_tbl`)
  — Stage 1 builds OBLIQUE63 + VERTICAL (the `shift`-per-two-rows slope), Stage 2 derives OBLIQUE27
  (transpose), OBLIQUE117/153 (hflip/transpose + `64−` complement) and HORIZONTAL; plus the `3 × 16`
  `Wedge_Codebook` (`av1_wedge_cb_tbl`, packed `dir·64 + xoff·8 + yoff`), shape = TALL/WIDE/SQUARE. **3-source
  verified** (spec + libaom + dav1d, `compound_wedge.md`).
- **`av1_wedge_mask_build`** (Stage 3): per block, `xoff/yoff = 32 − ((off·dim)>>3)`, a perimeter-average
  `flipSign` canonicalization, and `Mask = raw` or `64−raw` per `inv = wedge_sign XOR flipSign`. Geometry
  uses the NOMINAL block dims (`av1_block_width/height`), the fill uses the edge-clamped extent — so a
  frame-edge wedge block gets the top-left subregion of the nominal mask, not a mask computed from clamped
  dims. Fills `Av1_McMask`, then the DIFFWTD blend/chroma path runs unchanged (`comp_mode == 2`).
- **The decode/encode un-gate**: both lanes now admit `type == COMPOUND_WEDGE`.

**Proofs** (`tests/av1_mc_driver.tcyr`, `tests/av1_intertile.tcyr`): a COMPREHENSIVE 288-checksum test —
every eligible size × 16 indices × 2 signs — position-weight-checksummed against the new spec-literal
`scripts/refs/wedge_ref.py`, catching any codebook / master / oblique-generation / `flipSign` / shape-class
error on any index/size/direction; two HAND-COMPUTABLE anchors (KAT-A VERTICAL, KAT-B HORIZONTAL) that pin
the ref port itself to spec-derived values; a clamped-fill witness for the nominal-vs-clamped geometry; and
a WEDGE round-trip (32×32 via SPLIT, both signs) EXHAUSTIVELY equal to the `av1_mc_pred_compound(comp_mode=2)`
oracle AND differing from AVERAGE. **Mutation-verified — 0 survivors** except the two provably-equivalent
transformations the spec's sign-convention analysis predicts (dropping the O117/O153 complement is exactly
cancelled by `flipSign`; an offset on a direction's invariant axis is a no-op) — a real transpose/generation
error in those same planes IS caught. The decode mode-threading + both gate lanes die in the round-trips.

**The adversarial review (2 dimensions, worktree-isolated, patch-applied):** mask-generation math CLEAN
(288 checksums + hand-derived anchors + Stage-2 transpose mutation-verified); wiring + bounds CLEAN (gate
mirror, `comp_mode` exclusivity, `Av1_WedgeMaster` reads bounded to `[8,55] ⊂ [0,64)` for every codebook
entry, `wedge_index` entropy-bounded to `[0,15]`). Two CONFIRMED findings, both fixed: (F1) `av1_wedge_mask_build`
checked the master-table OOM but not the codebook-table — a wild read on a specific OOM, now guarded
symmetrically; (F2) the nominal-vs-clamped geometry split had no test (mutating to clamped dims shipped
green) — now closed by the clamped-fill witness, mutation-verified.

## [0.7.89] - 2026-07-17

**COMPOUND DIFFWTD (MASKED) INTER PREDICTION.** A two-reference block with `comp_group_idx == 1` and
`compound_type == COMPOUND_DIFFWTD` now blends its two predictions through a PER-PIXEL difference mask —
where the two predictions disagree most, the mask leans toward one reference. This is the first MASKED
compound mode and reuses the 0.7.87/0.7.88 prep intermediates. Scope stays exactly here: WEDGE (the other
masked mode, `type == COMPOUND_WEDGE`) still needs a mask codebook and remains a later bite, refused on
both lanes.

### Added

- **The difference-weight mask** (spec 7.11.3.12): `av1_diffwtd_mask_build` fills a new per-luma-pixel
  `Av1_McMask` — `m = Clip3(0, 64, 38 + (Round2(Abs(t0-t1), (BitDepth-8)+ib) >> 4))`, inverted to `64-m`
  when `mask_type != 0`. Base 38, DIFF_FACTOR 16, AOM_BLEND_A64_MAX_ALPHA 64. The diff-normalization shift
  is bit-depth dependent (4 @8-bit, 6 @10/12-bit) — a naive hardcode passes 8-bit and silently fails
  ≥10-bit, so ≥10-bit KATs ship. **3-source verified** (`compound_diffwtd.md`).
- **The mask blend** (spec 7.11.3.14, `av1_mc_pred_compound` extended with `comp_mode`/`mask_type`):
  `Clip1(Round2(tmp0*m + tmp1*(64-m), ib+6))` — the `6` is AOM_BLEND_A64_ROUND_BITS (log2 of the mask-sum
  64). The AVERAGE/DISTANCE scalar path (`comp_mode == 0`) is untouched.
- **Chroma mask subsampling** (`av1_diffwtd_mask_at`): the mask is built ONCE on luma, then read subsampled
  for chroma — 4:2:0 = `Round2(2×2 luma-mask sum, 2)`, 4:2:2 / vertical = `Round2(2×1 sum, 1)`. Luma read
  indices are edge-clamped (defense-in-depth; a conformant decode never overhangs).
- **The decode/encode un-gate**: both lanes now admit `comp_group_idx == 1` when `type == COMPOUND_DIFFWTD`;
  the reject narrows to WEDGE only.

**Proofs** (`tests/av1_mc_driver.tcyr`, `tests/av1_intertile.tcyr`): the mask+blend against an INDEPENDENT
integer-MV oracle `(p0*m + p1*(64-m) + 32) >> 6` with `m` recomputed from the spec formula (8/10/12-bit,
both mask_type polarities, the mask proven to vary per-pixel, and DIFFWTD-differs-from-AVERAGE); a 4:2:0
CHROMA oracle that recomputes the luma mask + 2×2 average (witnessing both the subsample math and that the
mask is sourced from LUMA); Python-independent known-answers pinned from the new spec-literal
`scripts/refs/diffwtd_ref.py` (a third derivation, defeating a shared impl/inline-oracle error); and a
DIFFWTD round-trip (both mask_types) EXHAUSTIVELY equal to the `av1_mc_pred_compound(comp_mode=1)` oracle
AND differing from AVERAGE. **Mutation-verified — 0 survivors**: the combine shift, the diff-norm
bit-depth shift, the base/divisor/Abs/inversion, and the chroma subsample die in the driver's INDEPENDENT
oracle (the round-trip shares `av1_mc_pred_compound`, so it can't see combine-internal bugs); the decode
mode-threading and both gate lanes die in the round-trips.

**The adversarial review (3 dimensions, worktree-isolated, patch-applied):** mask+combine math CLEAN
(ref-port-matched, every witness bites); memory-safety CLEAN (the top-risk chroma-subsample × edge-clamp
proven safe at odd luma dims down to 1×1, no `Av1_McMask` overflow, no overflow/infinite-loop). One
CONFIRMED coverage finding — the DECODE-side WEDGE reject had no witness (a 64×64 block can't carry a wedge
symbol) — now CLOSED with a 32×32-via-SPLIT fixture that mints a WEDGE stream and drives it through the
decoder as the LAST sub-block (so mis-admission yields `DR_OK`, not a truncation error), mutation-verified.
A latent `av1_diffwtd_mask_at` `lw==0` negative-index read (unreachable via bitstream) was hardened with a
guard.

## [0.7.88] - 2026-07-17

**COMPOUND DISTANCE (jnt) INTER PREDICTION.** A two-reference block whose `compound_idx == 0` now blends
its two predictions with ORDER-HINT DISTANCE WEIGHTS instead of a straight average — the closer reference
gets more weight. This is the direct extension of 0.7.87 AVERAGE: identical prep intermediates, a weighted
combine. Scope stays `comp_group_idx == 0` (AVERAGE + DISTANCE); only masked wedge/diffwtd
(`comp_group_idx == 1`) remains refused `DR_ERR_UNSUPPORTED` on both lanes.

### Added

- **The distance-weight process** (spec 7.11.3.15): `av1_dist_wtd_fwd(s, fh, ref0, ref1)` returns FwdWeight
  (applied to ref0; BckWeight = 16 - FwdWeight to ref1) from the two clamped absolute order-hint distances —
  `d0 = dist1`, `d1 = dist0` (the spec's swap), `order = (d0 <= d1)`, then a 3-row ratio-search over
  `Quant_Dist_Weight = [2,3, 2,5, 2,7, 1,31]` selecting from `Quant_Dist_Lookup = [9,7, 11,5, 12,4, 13,3]`
  (every row sums to 16 = DIST_PRECISION). `av1_ref_dist` (`src/av1_frame.cyr`) =
  `Clip3(0, 31, Abs(get_relative_dist(OrderHints[ref], OrderHint)))`, reusing the existing 5.9.4
  `av1_get_relative_dist`. **3-source verified** (spec + libaom + dav1d, `compound_distance.md`) — NOT the
  hallucinated `{8,8},{7,9},{6,10}` an early web fetch produced (which also sums to 16 — the tables are
  pinned by EXACT pair, not sum).
- **The weighted combine** (`av1_mc_pred_compound`, generalized): `Clip1(Round2(tmp0*fwd + tmp1*bck,
  ib + 4))`. The `4` is DIST_PRECISION_BITS (weight-sum log2), not `ib`. AVERAGE is now the `fwd = bck = 8`
  special case, which is BIT-EXACT with the old `Round2(tmp0 + tmp1, ib + 1)` (`8·(t0+t1) >> (ib+4)` ≡
  `(t0+t1) >> (ib+1)`, proven + regression-witnessed). The decode dispatch computes the weights once per
  block from `seq`/`fh`/`ref0`/`ref1` (8/8 unless `compound_idx == 0`) and threads them per plane.
- **The decode/encode un-gate**: both lanes now admit `compound_idx == 0`; the reject narrows to masked
  compound only.

**Proofs** (`tests/av1_mc_driver.tcyr`, `tests/av1_intertile.tcyr`): the weighted combine against an
INDEPENDENT integer-MV oracle `(ref0*Fwd + ref1*Bck + 8) >> 4` (1024 px, incl. the `8/8`-equals-AVERAGE
bit-exact witness + a DISTANCE-differs-from-AVERAGE assertion); the weight procedure + `av1_ref_dist`
against the new spec-literal `scripts/refs/dist_wtd_ref.py` (equal → 7/9, the ref0/ref1 SWAP witness → 13
vs 3, the order boundary, the zero-distance / order-hint-off degenerate → Lookup[3]); the Quant tables
pinned to EXACT values; and a jnt DISTANCE round-trip (unequal-distance refs, Fwd=13) with decoded pixels
EXHAUSTIVELY equal to the `av1_mc_pred_compound(Fwd=13)` oracle AND differing from the AVERAGE oracle
(proving the decode threaded distance weights). **Mutation-verified — 0 survivors**: the combine shift and
weight pairing die in the driver's INDEPENDENT oracle (the round-trip can't see combine-internal bugs — it
shares `av1_mc_pred_compound`); the d0/d1 swap, the `order` boundary, and the table values die in the weight
tests; the decode weight threading dies in the round-trip. The complementary decomposition (independent
combine oracle + round-trip wiring witness) leaves no gap.

**The adversarial review (3 dimensions, worktree-isolated, patch-applied):** weight-math CLEAN (loop /
tables / swap / combine / AVERAGE bit-exactness all mutation-verified + Python-oracle-matched);
memory-safety CLEAN (`OrderHints[ref]` cannot OOB — every path guarantees `ref ∈ [1,7]` via ref-parse
validation + the compound guard + the belt-and-suspenders `ref1 != INTRA` check; no combine overflow; the
ratio search always terminates; order-hints-off is handled). A review-flagged addition — the `fwd_eq_bck`
compound_idx CDF-context fix (5.11.29) — was found UN-witnessable in this pre-conformance arc (it shifts a
single binary symbol's context, which a self-consistent round-trip cannot see fail, and empirically does
not change the coded bytes) and was **deferred with conformance testing** rather than shipped untested;
the compound_idx context stays `fwd_eq_bck = 0` (unchanged since 0.7.87), which is correct for drishti's own
round-trips and only matters against external jnt streams.

## [0.7.87] - 2026-07-17

**COMPOUND AVERAGE INTER PREDICTION.** A two-reference inter block now predicts from BOTH references
and averages them — the first compound mode. Scope is `COMPOUND_AVERAGE` only (`comp_group_idx == 0 &&
compound_idx == 1`); distance-weighted (jnt), wedge, diffwtd, inter-intra and non-SIMPLE motion stay
cleanly refused with `DR_ERR_UNSUPPORTED` on both lanes.

### Added

- **The compound (prep) precision path in `av1_mc_put_8tap`** (spec 7.11.3.2 InterRound / dav1d
  `prep_8tap`): a new `compound` flag makes each MC pass keep `ib` extra intermediate bits and SKIP
  `Clip1` — `ib = 4` (8/10-bit) / `2` (12-bit). Per path: 2D vertical round `>>6` (not `6+ib`); H-only
  or V-only 1D `>>(6-ib)`; integer (no-subpel) `<< ib`. The single-ref (`compound=0`) path is byte-for-byte
  unchanged. **3-source verified** (spec + libaom + dav1d).
- **`av1_mc_pred_compound`** — predicts ref0 into a new `Av1_McTmp` scratch and ref1 into `Av1_McOut`
  (each at `bit_depth+ib` precision via the prep path), then combines `Clip1(Round2(tmp0 + tmp1, ib+1))`
  (dav1d `avg_c`, PREP_BIAS = 0 — drishti carries signed i64 intermediates). `av1_mc_pred_block` was
  refactored into `av1_mc_pred_core(out, dst, ref, …, compound)` (validation + gather + emu-edge +
  `put_8tap` → `out`) with a thin single-ref wrapper, so the compound driver reuses the exact same
  gather/edge/kernel path twice.
- **The decode/encode un-gate** (`av1_intertile.cyr`): a compound block dispatches to
  `av1_mc_pred_compound` (ref0/mv0 + ref1/mv1) when `comp_group_idx == 0 && compound_idx == 1`, else the
  mirror gate on each lane latches `DR_ERR_UNSUPPORTED`. Compound requires `reference_select`. A block
  naming an unpopulated DPB slot for ref1 is refused `DR_ERR_BOUNDS` before any dereference (the
  `av1_mc_pred_core` `ref == 0` guard is the real backstop).

**Proofs** (`tests/av1_mc_driver.tcyr`, `tests/av1_intertile.tcyr`): the AVERAGE math against an
INTEGER-MV exhaustive oracle `(ref0 + ref1 + 1) >> 1` (1024 px, two distinct gradient refs, edge-clamped)
plus a subpel self-average sanity across all three prep paths (2D / H-only / V-only, each within 1 of the
single-ref prediction); a round-trip (skip=1 compound `NEW_NEWMV`, dual-ref DPB LAST→slot0 / ALTREF→slot6,
distinct gradients) with decoded pixels EXHAUSTIVELY equal to an INDEPENDENT `av1_mc_pred_compound` oracle
(4096 px); an adversarial missing-ref case (empty ALTREF slot → `DR_ERR_BOUNDS`, no OOB); and the
scope-gate reject on BOTH lanes for DISTANCE (`compound_idx=0`, enable_jnt_comp) and DIFFWTD
(`comp_group_idx=1`, enable_masked_compound) — minted by finishing the symbol encoder by hand after the
encode gate discards, then driven straight into the decode gate. **Mutation-verified — 0 survivors**: the
four prep shift widths + the combine shift, the decode dispatch / ref1 source / mv1 source, and both gate
clauses on both lanes (`||→&&`, and each clause dropped independently; DISTANCE witnesses `compound_idx`,
DIFFWTD witnesses `comp_group_idx`).

**The adversarial review (3 dimensions, worktree-isolated, patch-applied):** precision CLEAN (all four
paths + combine mutation-verified, plus an independent hardcoded-tap Python oracle matching all 64 px of a
2D-subpel interior block); memory-safety CLEAN (`Av1_McTmp` sizing / stride, no scratch aliasing — tmp0
survives the second prediction, overflow, missing-ref and hostile-dims all double-guarded and probe-verified
at 128×128). One CONFIRMED finding — the scope-gate REJECT path had zero test coverage on both lanes
(mutating `||→&&` shipped green) — now closed by the DISTANCE/DIFFWTD gate-reject tests above and
mutation-verified.

### Fixed

- **`av1_reset_block_context` (5.11.5) indexed the coeff-context strips ABSOLUTE, the rest of the
  path tile-relative** (the 0.7.84 review's recorded note, pre-existing intra-lane). The per-tile
  Above/Left level+DC strips are tile-relative everywhere else (the 0.7.50 `av1_coeff_ctx_col/row`
  rebase in coeffs, the 5.11.2 whole-strip clears), but the skip-block reset transcribed the spec's
  frame-absolute `MiCol >> subX` literally: on any non-first tile it cleared the WRONG slots (a
  prior block's stale levels survive to poison the next block's coeff contexts), and once
  MiColStart exceeded extent+pad it overran the tile-sized strip — an OOB heap write. Now rebased
  by the tile's plane origin (`- (MiColStart >> subX)`), one convention throughout. Inert in every
  shipping fixture (tile 0 rebases to identity; the all-skip inter scope never reads levels) —
  fixed ahead of the non-skip inter residual bite that would have made it live.
  Witnessed in `tests/av1_partition.tcyr` by (a) a poisoned-sentinel convention pin on a windowed
  4:2:0 tile — both candidate slot ranges sentineled, rebased must clear, absolute must survive,
  chroma subsampled rebase live — and (b) a decode-level windowed-tile test: a non-skip block's
  coeffs organically write culLevel/dcCategory at rebased slots, the skip block below must clear
  exactly those. Mutation-verified: the above and left loops each flipped back to absolute
  independently — 12 and 11 assertions red respectively; restore byte-identical, 27106/27106 green.

- **`use_128x128_superblock` was read but never gated — a 128-SB stream was silently mis-parsed,
  not rejected** (the 0.7.85 review's recorded note, pre-existing, codebase-wide; affects both intra
  and inter, since they share the SB loop). `av1_seq_use_128x128` (`src/av1_seq.cyr`) parses the
  flag, but the tile superblock loop (`av1_decode_tile`) hardcodes 64x64 SBs — it steps by `AV1_SB4`,
  calls `av1_decode_partition` with `BLOCK_64X64`, and `av1_residual` uses `sbMask=15` — so a sequence
  signalling `use_128x128_superblock=1` decoded only the top-left 64x64 of each superblock (wrong
  partition tree / positions, arithmetic-decoder desync) and returned `DR_OK` on garbage rather than
  rejecting the stream — a "trust no input byte" violation (CLAUDE.md). Now latched
  `DR_ERR_UNSUPPORTED` in `av1_frame_dec_new`, the one chokepoint every decode path shares
  (`av1_decode_frame`/`_ref`, `av1_decode_obus`, `av1_decode_stream`), before any tile runs.
  Witnessed in `tests/av1_decode.tcyr` (`test_frame_decode_sb128_rejected`): the valid `_plain`
  keyframe payload with `SB128=1` set now rejects `DR_ERR_UNSUPPORTED` (frame 0, no crash/garbage),
  while the byte-identical payload with `SB128=0` still decodes `DR_OK` — the flag is the sole gate
  input. Mutation-verified: removing the gate flips the test `UNSUPPORTED → DR_OK` (the 64x64
  mis-parse ships green); restore byte-identical, 195/195.

## [0.7.86] - 2026-07-17

**THE VAR-TX INTER RESIDUAL.** TX_MODE_SELECT non-skip inter blocks now decode — the luma transform
partition (`txfm_split`) is read and each leaf transform is reconstructed onto the MC prediction. This
un-gates the last tx-mode path (0.7.85 covered only TX_MODE_LARGEST / uniform tx).

- **`read_var_tx_size`** (spec 5.11.37) + the **`txfm_split` context** (spec 9.3): `av1_txfm_split_ctx`
  (`(Tx_Size_Sqr_Up != maxTxSz)*3 + (TX_SIZES-1-maxTxSz)*6 + above + left`) with `av1_get_above_tx_width`
  / `av1_get_left_tx_height` reading the frame **InterTxSizes / Skips / IsInters / MiSizes grids** — the
  spec keeps NO separate txfm strips; writing InterTxSizes per leaf IS the ctx update. New
  `Default_Txfm_Partition_Cdf` (21 binary contexts, spec §10, **3-source verified** vs libaom + dav1d) in
  `av1_noncoeffcdf.cyr`, absolute-offset pinned.
- **`transform_tree`** (spec 5.11.36): the luma leaf walk (recurse halving the longer side / quadrant when
  square until (w,h) fits the recorded `InterTxSizes` leaf, then `find_tx_size` + transform_block).
- **A per-4×4 `TxTypes` grid** (`AV1TILE_TXTYPES`, mirroring InterTxSizes): a var-tx block has MANY luma
  leaves each with its own `inter_tx_type`, so 0.7.85's single-scalar chroma co-location shortcut is
  replaced — each luma leaf broadcasts its TxType into the grid, chroma reads the co-located cell.
- **The encode inverse**: `av1_write_var_tx_size` (reproduces a target InterTxSizes layout) +
  `av1_transform_tree_encode` (per-leaf coeffs via the new `AV1FB_VARTX` plan). `av1_block_write_grids`
  gained a `write_intertx` flag so a var-tx block's per-leaf InterTxSizes survive the store (neighbour
  txfm_split ctx reads them). The decode/encode **un-gate**: `skip==0 && TX_MODE_SELECT && sub_size>BLOCK_4X4
  && base_q!=0`. `Av1Tile` 544→552, `Av1BlockInfo` 232→240 (layout-guard test updated).

**Proofs** (`tests/av1_intertile.tcyr`): the `txfm_split` ctx verified against the new spec-literal
`scripts/refs/var_tx_ref.py` (11 known answers across all context groups); round-trip (encode→decode) with
pixels compared EXHAUSTIVELY against an INDEPENDENT per-leaf oracle (MC + per-leaf `av1_reconstruct` with
each leaf's own tx type) — mono 16×16→4×TX_8X8, **4:2:0** (chroma co-locates the top-left leaf's type via
the grid), **mixed-depth** (8×8→4×TX_4X4, the depth-2 path), **32×32→16×TX_8X8** (depth-2 forced 8×8 leaf,
the depth-gate not the TX_4X4 gate), and an **InterTxSizes grid witness** (the per-leaf tx sizes survive the
store — a conformance detail the self-consistent round-trip can't see). All **mutation-verified — 8
mutations, 0 survivors**: the ctx group multiplier / neighbour polarity / sub-split term, the leaf-boundary
condition, the forced-leaf depth gate, the read ctx, the chroma co-location, and the InterTxSizes
suppression (the last two each needed a dedicated test the round-trip missed). The obsolete 0.7.85
non-skip-gated tests were removed (their premise — non-skip rejected — is gone); a null-vplan encode is
refused, not crashed.

**The adversarial review (15 agents, 4 dimensions, worktree-isolated) confirmed 10 findings — all fixed:**

- **A CRITICAL OOB heap write (reproduced)**: `read_var_tx_size` (and its encode twin `write_var_tx_size`)
  filled InterTxSizes across the full tx footprint with NO ROW_END/COL_END clamp — a var-tx block
  overhanging a non-64-aligned frame edge overran the frame-sized MI grid (heap overflow + neighbour
  InterTxSizes corruption), reachable from a legal/hostile bitstream. Fixed: clamp both fills to the tile
  window (mirroring `av1_block_write_grids`); witnessed by an edge-overhang canary test (mutation-verified).
  A "trust no input byte" violation caught before it shipped.
- **Two "dead code" test-adequacy gaps** (code correct, mutations survived): the `get_above/left_tx_width`
  **skip-inter neighbour** branch (`Block_Width`↔`Block_Height` survived — no test reached a block edge with
  a skipped-inter neighbour) and `transform_tree`'s **non-square (w>h / w<h)** recursion (every fixture was
  square). Closed with a direct skip-inter ctx test (non-square neighbour blocks pin width-vs-height) and a
  **16×8** var-tx round-trip; both mutation-verified.
- **Robustness (defensive)**: `av1_transform_tree_encode` now bounds the leaf cursor against the plan count;
  `av1_encode_block_inter` mirrors the decode compound / inter-intra / non-SIMPLE-motion scope gates.
- Deferred (documented, inert while deblock is off): var-tx luma `LoopfilterTxSizes` is written uniformly,
  not per-leaf; and the chroma co-location `Max()`/subsampling is exercised only at a plane origin.

Final: **38 suites / 27,420 assertions / 0 failed**; inter suite → 405.

## [0.7.85] - 2026-07-17

**THE NON-SKIP INTER RESIDUAL (uniform-tx).** A genuine non-skip inter block now decodes with the
reconstructed residual **added onto the motion-compensated prediction** — the first inter path that
codes coefficients. Scope: the UNIFORM-tx case (TX_MODE_LARGEST / ONLY_4X4, one uniform tx per plane, no
`txfm_split`); var-tx (TX_MODE_SELECT recursion) stays a cleanly-gated later bite.

- **Inter transform-type reads** — the missing piece, since the coeff loop was otherwise inter-ready.
  `av1_transform_type_decode/encode` gained the `is_inter` branch (reads/writes `inter_tx_type`), placed
  BEFORE the set dispatch because the tx-set enum collides (`AV1_TX_SET_INTER_1 == AV1_TX_SET_INTRA_1`).
  New `Default_Inter_Tx_Type_Set1/2/3` CDFs (spec §10, 3-source verified vs libaom `default_inter_ext_tx_cdf`
  + dav1d) into `av1_noncoeffcdf.cyr`'s TWO-tier blob (static builder + the `av1_ncdf_new` copy both grown);
  the `Tx_Type_Inter_Inv_Set1/2/3` + `Tx_Type_In_Set_Inter[4][16]` tables + accessors into `av1_txtype.cyr`.
- **`compute_tx_type` inter chroma** co-locates the luma TxType (uniform tx: the block's single luma type,
  threaded via a new `AV1TTC_LUMA_TXTYPE` slot), gated by `Tx_Type_In_Set_Inter`.
- **The inter residual driver** (`av1_intertile.cyr`): `av1_transform_block_inter` + `av1_residual_inter`
  (NO intra prediction — MC already wrote the pixels; `av1_coeffs_decode` with `is_inter=1` then
  `av1_reconstruct` ADDS residual onto the MC prediction), the paired encode lane
  (`av1_residual_inter_encode` reading a per-block residual plan via the new `AV1FB_RESID` slot), wired into
  `av1_decode/encode_block_inter` behind the **var-tx gate** (`skip==0 && TX_MODE_SELECT && sub_size>BLOCK_4X4
  && base_q!=0 → DR_ERR_UNSUPPORTED`, mirrored on both lanes). `AV1TILE_TX_MODE` is threaded in
  `av1_tile_set_inter_ctx`.

**Proofs** (`tests/av1_intertile.tcyr`, 98 → 166 assertions): non-skip inter blocks round-trip
(encode→decode) with pixels compared EXHAUSTIVELY against an INDEPENDENT oracle (MC via `av1_mc_pred_block`
+ residual via `av1_reconstruct`, both already reference-verified, composed with the KNOWN planted coeffs +
tx types) — per tx SET (INTER_1 8×8, INTER_2 16×16, INTER_3 32×32 IDTX), MONO + 4:2:0 (three-plane chroma
co-location), and the zero-residual (`all_zero`) non-skip path == pure MC. The 4:2:0 case caught a real
tx-type-vs-tx-size confusion in the test oracle (the decoder was correct) — the decoder path is sharp. Plus:
inter tx-type round-trip across all three sets, `compute_tx_type` chroma matching `scripts/refs/inter_residual_ref.py`
(spec-literal), absolute-offset CDF/table pins, and the var-tx scope gate (both lanes refuse). All
**mutation-verified — 11 mutations, 11 killed, 0 survivors**: symbol-count/dispatch per set, inverse-map +
membership transcription, the two-tier CDF allocation trap, the `AV1TTC_LUMA_TXTYPE` thread, `is_inter`
routing, the residual/reconstruct calls, and the var-tx gate. A `Av1BlockInfo` layout-guard test caught the
struct growth (224→232) — updated.

**The adversarial review (14 agents, 4 dimensions, worktree-isolated) confirmed 5 findings + 2 uncertain,
all folded in:**
- **THE MAJOR (test-adequacy, the [[cdf-blob-tests-must-pin-absolute-offsets]] lesson): round-trip
  circularity.** Wrong interior inter-tx CDF values, a flipped membership entry, and an inverse-map swap
  all SURVIVED the suite — every test round-trips through drishti's OWN encoder with the SAME table, so a
  symbol survives any monotonic CDF. Fixed with FULL absolute-offset pins: all 59 CDF entries + 30 inverse
  entries + 64 membership entries checked against `scripts/refs/inter_residual_ref.py` (now emitting the
  authoritative values). The three previously-surviving mutants are now killed.
- **A real encode/decode desync** (minor, malformed-plan robustness): the encode lane derived the chroma
  tx type from the plan's luma type UNCONDITIONALLY, but when the luma tx is all-zero NO `transform_type`
  symbol is written — the decoder derives DCT_DCT. Fixed: the encoder now uses the effective luma type
  (DCT_DCT when luma `eob==0`). Witnessed by a deterministic byte-comparison (a 1D-scan-class plan luma
  type must produce byte-identical output to DCT_DCT).
- **Lossless chroma LoopfilterTxSizes** recorded the uv max-rect tx instead of TX_4X4 (intra/spec
  divergence, harmless today — deblocking is off under coded_lossless). Fixed to clamp TX_4X4 for every
  plane when lossless; witnessed.
- **Coverage** added: `reduced_tx_set` (routes 16×16 inter → INTER_3) and rectangular tx-set selection
  (TX_16X8/8X16 → INTER_1, TX_16X32 → INTER_3, round-tripped); the one-luma-tx-per-≤64×64-block invariant
  (the chroma co-location precondition) pinned. `reduced_tx_set` is now threaded from the frame header in
  `av1_tile_set_inter_ctx` (a latent fix — the inter path previously took it only from `av1_tile_new`).
- Spawned (pre-existing, codebase-wide, out of this bite's scope): `use_128x128_superblock` is read but
  never rejected — a 128-SB stream is silently mis-parsed (the SB loop is 64×64-only). Flagged for a
  frame-level UNSUPPORTED gate.

Final: **38 suites / 27,352 assertions / 0 failed**; inter suite 166 → 343.

## [0.7.84] - 2026-07-16

**THE INTER TILE DECODE — the milestone of the inter arc.** A genuine AV1 inter frame decodes
end-to-end: raw entropy-coded bytes → the complete mode-info decode (0.7.62–0.7.83) →
motion-compensated pixels from a DPB reference, through `decode_block`/`decode_tile` and
`av1_decode_stream`.

- **New module `src/av1_intertile.cyr`** (after av1_dpb, per the enum-visibility rule; the block/tile
  dispatchers forward into it): `av1_tile_set_inter_ctx` (frame handles + shared frame-addressed MV +
  SkipModes grids + reusable scan records + the cdef bundle), `av1_decode_block_inter` (the 5.11.15
  driver → the skip scope gate → `compute_prediction` per plane via `av1_mc_pred_block` from
  `av1_dpb_ref_frame` → the 5.11.4 storage loops + SkipModes + LoopfilterTxSizes), the paired
  `av1_encode_block_inter`, and the `av1_decode/encode_inter_tile` drivers (intra contexts + the four
  per-tile adaptive inter CDF families). Scope gates reject `DR_ERR_UNSUPPORTED`, each roadmap-tracked:
  the non-skip inter residual, compound averaging, inter-intra blending, OBMC/warp, scaled refs.
- **`Av1Tile` grew 424 → 544** (the inter context + `AV1TILE_IERR`, a STICKY inter-lane error latch —
  the partition walk discards block returns, so gate/scope errors latch per block and the tile driver
  surfaces them; later blocks no-op once latched). `av1_tile_share_grids` shares the new grids.
- **Frame/stream wiring**: `Av1FrameDec` carries DPB + refs (`av1_frame_dec_set_inter`);
  `av1_frame_dec_group` routes non-intra frames to the inter tile (UNSUPPORTED without a DPB — never
  silent garbage); `av1_decode_frame_ref` threads the state; `av1_decode_stream` feeds its DPB + refs
  into both the FRAME-OBU and TILE_GROUP paths.

**The milestone proof** (`tests/av1_intertile.tcyr`, 58 assertions): a gradient reference
(`(x + 2y) & 255`, distinct at every shift) in the DPB; all-skip NEWMV tiles decode and the pixels are
compared EXHAUSTIVELY against an INDEPENDENT `av1_mc_pred_block` computation (no shared code above the
MC driver itself) — integer MV (4096 px), sub-pel (8-tap taps live), dual-filter (SMOOTH-x/SHARP-y,
`en_dual`), and a 2×2-superblock 128×128 frame with four distinct MVs (16384 px; per-block scan-ctx
reconfiguration + both neighbour-threading directions + per-quadrant MI-grid values). The spot KAs
initially had the MV sign backwards — the exhaustive oracle overruled the author, per design. Plus: the
frame-level route equals the tile-level decode; no-DPB rejects UNSUPPORTED; a leaf-built non-skip
payload is REJECTED at the scope gate (never mispredicted); the SkipModes store pinned via a planted
sentinel; MI/Skips grid population asserted.

**The byte-stream layer**: a bit-exact NON-still sequence header + KEY and INTER frame-header builders
(every field's packing commented, verified by parse-back — every built byte consumed, 13 field pins),
then TD + SEQ + KEY(fh+tile) + INTER(fh+tile) through `av1_decode_stream`: two frames decode from pure
bytes, the inter frame is the output, the DPB updates. (The intra encode lane is skip-only, so the
in-stream reference is flat — this layer pins parse → threading → routing; pixel strength lives in the
gradient record-level tests. A content-bearing stream E2E arrives with the non-skip encode lane,
roadmap.md.)

All **mutation-verified — 13 mutations, 11 killed, 2 tracked residuals**: MV row/col swap → 6 failures,
filt swap → 1 (after the dual-filter case), ref-slot swap → crash caught, plane-origin swap → 1 (after
the multi-SB case), the skip scope gate dropped → 1, the inter dispatch dropped → 14, MI store dropped →
crash caught, the sticky latch unsurfaced → 1, SkipModes store dropped → 1 (after the sentinel), plus
the null-`plan_tx` crash found live during development. TRACKED RESIDUALS (roadmap.md): the skip-ctx
neighbour THREADING is mutation-resistant while every block is skip=1 (all candidate CDF rows favor
skip; becomes killable with mixed skip patterns in the non-skip bite), and the in-tile skip-mode ctx is
exercised only at zero (skip_mode needs compound refs).

**The adversarial review (36 agents, 4 slices) confirmed 16 findings — all folded in:**

- **THE MAJOR (a real spec deviation the mono-fixture monoculture hid): sub-8×8 chroma.** For a block
  whose chroma unit SPANS SIBLING blocks (bw4 or bh4 = 1 under subsampling), spec `compute_prediction`
  predicts the FULL even-aligned unit at the HasChroma block using the SIBLINGS' MVs from the MI grid —
  the per-block footprint MC emitted stale frame contents as chroma (reproduced: 12 of 16 U pixels never
  written, decode accepted DR_OK). Fixed per the "never silent garbage" convention: a **geometry gate on
  BOTH lanes** rejects sibling-span chroma blocks `DR_ERR_UNSUPPORTED` BEFORE any symbol work (the
  sibling-MV chroma loop is its own bite, roadmap.md). Witnessed decode-side by a LEAF-BUILT 4:2:0
  8×8 VERT payload and write-side by the mirrored plan refusal.
- **Lossless TxSize**: skip-inter blocks now honor `read_tx_size`'s Lossless early-out (base_q 0 →
  TX_4X4, both lanes) instead of max-rect — the recorded InterTxSizes/LoopfilterTxSizes were wrong for
  lossless streams.
- **The ICDEF cdef-plan slot**: now COPIED from `set_cdef_ctx` (it was hard-zeroed with a comment
  promising "the encode lane sets it" — nothing did), and a cdef-wired encode tile WITHOUT a plan is
  refused up front instead of null-dereffing in `av1_write_cdef` on a non-skip block.
- **Test-adequacy repairs** (each review-confirmed survivable, each now mutation-killed): 4:2:0
  three-plane two-SB E2E with per-plane exhaustive oracles (chroma had ZERO coverage; two SBs because at
  the origin the extent clamps mask a dropped subsampling shift); reference-frame SELECTION pinned
  (GOLDEN → DPB slot 3 with a DIFFERENT frame in slot 0 — hardcoding LAST or slot 0 was
  oracle-invisible); a NON-SB-aligned 48×48 frame pins the visible-extent clamps (exhaustive + raw
  border-zero probes — deleting both clamps had survived); tile-window availability pinned DIRECTLY on
  `av1_inter_block_setup` (frame-absolute `r>0/c>0` had survived); `share_grids`' MVGRID/SKIPMODES
  entries pinned structurally (incl. set_inter_ctx preservation); encode-lane IERR surfacing witnessed
  (buffer 0 + out_len 0); the write-side LFTX store pinned; the KEY header gets its own parse-back (9
  field pins) and the INTER parse-back pins frame_height.
- **13 more mutations, ALL killed** (after two test-strengthening rounds the campaign itself forced):
  both chroma-span gates, both lossless overrides, ref-hardcode at the lookup AND slot-hardcode in the
  DPB, both clamps, frame-absolute avail, the share entries, the ICDEF copy, the encode IERR surface,
  chroma-never-predicted (paired), chroma-shift-dropped (paired).
- Recorded, not in this cut: `reset_block_context`'s absolute-vs-rebased strip indexing (pre-existing on
  the intra lane, inert in the all-skip scope — flagged for the non-skip bite); square-fixture geometry
  and byte-granular tail consumption in the header parse-backs (note-level; heights now pinned).

Suite: `tests/av1_intertile.tcyr` 58 → 98 assertions.

## [0.7.83] - 2026-07-16

**Inter prediction — `inter_frame_mode_info` (spec 5.11.15), the OUTER DISPATCH.** The last mode-info
layer before the inter tile decode: neighbour preamble → `inter_segment_id(1)` → `read_skip_mode` →
skip → `inter_segment_id(0)` → the cdef splice → the delta positions → `read_is_inter` → the
inter/intra fork.

- **`Skip_Mode` CDF** (§10 `Default_Skip_Mode_Cdf[3]`) — refcdf blob 168 → 177, rows pinned per-value
  at absolute offsets in the layout test.
- **`av1_read_skip_mode(_sym)`** (5.11.11) — the full six-condition gate (three segment features /
  `!skip_mode_present` / either dimension < 8 → forced 0, NO symbol); ctx (0..2) is
  AboveSkipMode + LeftSkipMode, caller-derived until the tile bite (roadmap.md).
- **`av1_read_is_inter`** — the 5.11.15 four-way selection over the 0.7.68 leaf (renamed
  `av1_read_is_inter_sym`): skip_mode → 1; seg REF_FRAME → its parse-clipped datum ≠ INTRA; seg
  GLOBALMV → 1; else `@@is_inter` at the derived ctx.
- **`Av1BlockInfo`** + **`av1_inter_frame_mode_info`** — the outer driver: builds the 5.11.15 neighbour
  cache (`av1_nbctx_setup`) at the spec's preamble position, then dispatches into the 0.7.82
  orchestrator. Deferred features gate hard as `DR_ERR_UNSUPPORTED` **consuming nothing** —
  segmentation reads, delta-q/lf, and the intra fork (each roadmap-tracked); the cdef splice mirrors
  the intra path's 0.7.32 record. Paired **`av1_write_inter_frame_mode_info`** inverse.

Verified against a new committed spec-literal port (`scripts/refs/inter_frame_ref.py` — the 5.11.11
gate table, the is_inter selection, five outer schedules). Tests: leaf round-trips at every ctx +
per-value §10 pins; the gate driven both ways per condition; dispatch conformance (leaf-written
fall-through); four full outer round-trips (plain inter / skip_mode / present-off / size-closed)
behind the `0xA5` marker; UNSUPPORTED gates proven to consume **nothing** via marker-only streams —
a mutation showed plain return-code asserts are blind here (a dropped gate lands on UNSUPPORTED via
the downstream intra fork by accident); hostile nulls + mi_size boundaries.

All **mutation-verified — 25 mutations, 0 survivors** (14 author + 11 review-driven): each 5.11.11 gate
condition dropped/shifted → 1/1, the skip forcing dropped → 2, the is_inter skip_mode forcing dropped →
2 and the datum test inverted → 2, the nbctx preamble crippled → 6, the skip ctx hardcoded → 3, each
UNSUPPORTED gate dropped → 2/2/1 (killed only after the marker-only hardening — two initially SURVIVED
the return-code asserts), the skip_mode CDF base shifted → 6, and a WRITER-only present-check drop → 2.
Two harness patterns initially aliased into the writer's identical gate block — caught as PATTERN ERRORs
by the unique-anchor discipline. Review-driven: the cdef splice scrambled → 2 and deleted → 2, each
seg-feature gate condition deleted → 2/2/2, the is_inter branch swap → 1, skip_mode ctx hardcoded in
BOTH drivers → 3, the skip threading zeroed in both → 4, mi_size hardcoded into both skip_mode calls →
1, the Av1BlockInfo layout shrunk → 2, and the unrepresentable-record guard reverted → 6.

4-slice adversarial review (isolated worktrees, `sawCode` tripwires, reproduce-in-worktree refuters,
new-mutant discipline; the workflow itself survived an API-outage marathon — six all-529 void
completions were correctly discarded as non-reviews before the seventh ran 38 agents): **17 findings
confirmed (7 major), 0 refuted — all closed in-cut**:
- **Code**: the writer silently desynced on records the 5.11.11/5.11.15 gates cannot code —
  `av1_write_skip_mode` now surfaces a closed-gate `skip_mode = 1` as `DR_ERR_BOUNDS`,
  `av1_write_is_inter` checks every forced path AGREES with the record, and the driver rejects the
  inconsistent `skip_mode = 1 / skip = 0` coupling (the unrepresentable-input convention, third time
  it has caught a writer).
- **Tests**: the cdef splice was completely unexercised in BOTH drivers (now driven with a live ctx —
  the decoded index must LAND in the reader's grid, and a skip = 1 block must leave it untouched); the
  three seg-feature closures were **falsely verified** — their asserts ran after the marker was already
  consumed, and even per-case trailing literals passed by arithmetic-coder luck on a single
  high-probability binary symbol (measured: three deletion mutants survived twice) — the deterministic
  fix plants a `skip_mode` SYMBOL with value 1 right after the gated call so a wrongly-consuming gate
  fails by VALUE; the 5.11.15 REF_FRAME-beats-GLOBALMV priority pinned with both features active;
  write-side forced-path agreement asserts; leaf-built OUTER conformance streams (the skip-mode form at
  a nonzero ctx; the ref port's F5 at 4x8 with threaded neighbour-skip ctx) killing the symmetric
  ctx/size/threading mutants; the `Av1BlockInfo` layout pinned absolutely.

## [0.7.82] - 2026-07-16

**Inter prediction — `inter_block_mode_info` (spec 5.11.23), THE ORCHESTRATOR.** Every inter mode-info
subsystem built across 0.7.62–0.7.81 now composes into the complete per-block decode, in the spec's exact
read order: `read_ref_frames` → `isCompound` → `find_mv_stack` → YMode (skip_mode fixed
`NEAREST_NEARESTMV` / seg SKIP|GLOBALMV fixed `GLOBALMV` / `@@compound_mode` / the
`@@new_mv`–`@@zero_mv`–`@@ref_mv` chain) → the DRL loops → `assign_mv` → `read_interintra_mode` (with its
`RefFrame[1] = INTRA_FRAME` side-effect applied between stages) → `read_motion_mode` (which sees the
POST-interintra `RefFrame[1]`) → `read_compound_type` → the interp-filter tail.

- **`Av1InterBlock`** (`src/av1_intermode.cyr`) — the block-level output record: refs / isCompound /
  YMode / RefMvIdx / Mv[0..1] / motion_mode / interp_filter[0..1] + embedded interintra and
  compound-type records; layout pinned absolutely (II ends at CT, CT ends at SIZE).
- **`av1_inter_block_mode_info`** — the driver. The block's refs and GLOBAL-MV candidates are installed
  into the scan ctx HERE (they depend on the just-decoded refs — `setup_global_mv` per ref, `GmType`
  guarded for the post-interintra `INTRA_FRAME`/`NONE`); `find_mv_stack` then runs on the configured ctx.
  Persistent 2×`Av1Mv` scratch (`av1_ibmi_scratch`). Hostile guards: null out/ctx/ws, and a seg
  REF_FRAME datum of 0 (INTRA) reaching the inter path → `DR_ERR_BOUNDS` (5.11.15 derives `is_inter = 0`
  from it, so a conformant stream cannot get here).
- **`av1_write_inter_block_mode_info`** + the **`av1_write_assign_mv_*`** family — the full encoder
  inverse; `write_assign_mv_list` mirrors the reader's predictor derivation and emits the NEWMV diff.
- Four new seq accessors (`av1_seq_enable_interintra_compound` / `_masked_compound` / `_dual_filter` /
  `_jnt_comp`).

### Fixed
- **Development-caught writer bug** (by the interintra test case's marker, before any review): the
  inverse applied the 5.11.28 `RefFrame[1]` side-effect by checking `SETREF1` — a READER output the
  source record never carries — so writer and reader diverged on `ref1` and desynced from
  `read_motion_mode` onward. The spec assigns `RefFrame[1]` inside `if (interintra)`: the writer now
  keys on the interintra flag itself, gated `!isCompound && !skip_mode`.

Verified against a new committed spec-literal port (`scripts/refs/inter_block_ref.py` — the 5.11.23
SYMBOL SCHEDULE: group order/presence, `get_mode`, `has_nearmv`, the DRL read-count model, 11 labeled
schedules). Tests: 12 full-path round-trips through driver + inverse behind the `0xA5` literal marker —
single NEWMV/NEARESTMV/NEARMV+DRL/GLOBALMV(IDENTITY and TRANSLATION with a real (1,2) global vector) /
LOCALWARP / fixed-filter; compound NEAREST_NEARESTMV / NEW_NEWMV+two-DRL+two-MV; skip_mode (a
marker-only stream — not one symbol coded); skip-beats-seg priority; interintra (the
`ref1 → INTRA_FRAME → motion_mode forced SIMPLE` interaction end-to-end); seg GLOBALMV; hostile nulls +
the INTRA-datum reject; record-layout pins.

All **mutation-verified — 20 mutations, 0 survivors** (12 author + 8 review-driven): set_refs dropped →
40 failures, the global-MV install zeroed → 2, skip-vs-seg order → 4, compound/single mode-reads
swapped → 47, DRL forced 0 → 7, compound assign lists swapped → 4, the interintra side-effect dropped →
4, motion_mode handed the pre-ii ref1 → 3, compound_type handed interintra=0 → 1, the interp tail
handed SIMPLE → 1, the skip YMode default corrupted → 2, single assign routed through list 1 → 6;
review-driven: reader-only mv_ctx=1 → 2, the setup_global_mv position swap (paired AND reader-only) →
2/2, set_global reordered after find_mv_stack → 1, the writer ref1 guard reverted → 2, en_dual
wired from en_jnt → 6, force_int threading dropped → 3, mi_size hardcoded → 6.

4-slice adversarial review (isolated worktrees, `sawCode` tripwires, reproduce-in-worktree refuters,
new-mutant discipline): **15 findings confirmed (4 major), 1 refuted — all closed in-cut** with one code
fix, one reference-port fix, and a hardening package whose 8 mutant classes all now die:
- **Code**: the writer's interintra `RefFrame[1]` side-effect lacked the full 5.11.28 coding gate — an
  uncodable interintra record (enable off, or a block outside 8x8..32x32) silently desynced; now
  surfaced as `DR_ERR_BOUNDS` (the unrepresentable-input convention).
- **Reference port**: the reviewers caught THREE WRONG ROWS in `inter_block_ref.py` (cases 4/8/10 had
  `needs_interp`/motion-branch inputs copied across rows instead of derived) — the known-answer source
  itself was buggy; fixed and re-derived per-case.
- **Tests**: the global-MV threading was dead wiring (square fixtures + IDENTITY/TRANSLATION models) —
  killed by a ROTZOOM fixture at an ASYMMETRIC position with a mv_ref.py-derived value pin (col 11) and
  a GLOBALMV-neighbour substitution case; the `mv_ctx=0` wiring was round-trip-invisible (identical
  default CDFs adapt in lockstep) — pinned by asserting the adaptation COUNT lands in ctx 0 and not
  ctx 1; seq-enable separation (en_dual, en_ii, all-off compound), force_int/allow_hp variation,
  mi_size variation (8x8/64x64), the II-wedge and CT-group-1 paths, a leaf-built conformance schedule
  (kills paired wiring bugs), and the b7 `CT_TYPE=0`-aliases-WEDGE fixture accident.

## [0.7.81] - 2026-07-16

**Inter prediction — `read_ref_frames` (spec 5.11.25), the reference dispatcher +
`seg_feature_active` (5.11.14).** The next orchestrator toward `inter_block_mode_info`: RefFrame[0..1]
now resolves through the full spec dispatch.

- **`av1_seg_feature_active`** (`src/av1_frame.cyr`) — 5.11.14: `segmentation_enabled &&
  FeatureEnabled[segment_id][feature]`, plus the missing `SEG_LVL_SKIP = 6` / `SEG_LVL_GLOBALMV = 7`
  constants. Defensive: out-of-range segment/feature indices read nothing and report inactive (callers
  wanting a hard error validate first — the driver does).
- **`av1_read_ref_frames`** (`src/av1_intermode.cyr`) — the dispatcher. Three no-symbol paths, in spec
  order: `skip_mode` → the frame header's `SkipModeFrame` pair (5.9.23); an active `SEG_LVL_REF_FRAME` →
  its parse-clipped (5.9.14) `FeatureData` ref verbatim (including the 0 = INTRA datum) + `NONE`; an
  active `SEG_LVL_SKIP` or `SEG_LVL_GLOBALMV` → `(LAST, NONE)`. Otherwise `@@comp_mode` is coded only
  when `reference_select && min(bw4, bh4) >= 2` (else forced SINGLE, no symbol) and the 0.7.69 compound /
  0.7.68 single tree runs with its 0.7.75/0.7.76-derived contexts. Hostile guards (segment_id, MiSize)
  reject before any symbol is consumed. The ctx records fill a lazily-allocated **persistent scratch**
  (`av1_rrf_scratch`) — a per-call arena alloc in a per-block path would grow without bound (the 0.7.60
  lesson).
- **`av1_write_ref_frames`** — the gate-replaying encoder inverse; `is_comp` derives from
  `r1 > INTRA_FRAME` (NONE = -1 and INTRA_FRAME = 0 both classify single, matching 5.11.23's isCompound).

Verified against a new committed spec-literal port (`scripts/refs/ref_frames_ref.py`: the dispatch +
`seg_feature_active`, 15 labeled cases including both priority orderings — skip_mode beats seg
REF_FRAME, REF_FRAME beats SKIP on the same segment). Tests: every dispatch path round-tripped both
ways behind the 8-bit `0xA5` literal marker; decode-side conformance streams hand-built with the LEAF
writers (pinning that the forced-SINGLE gate codes **no** comp_mode symbol at 4x8/8x4 and codes it at
the exact 8x8 boundary); the parse-clip boundary data values 0 and 7 land verbatim; guard boundaries
pinned at BOTH edges (segment_id −1/0/7/8, MiSize −1/21/22/25 — the 0.7.80 review lesson); an
adaptive-CDF lockstep case; writer-side guard parity.

All **mutation-verified — 28 mutations, 0 survivors** (17 author + 11 review-driven): each dispatch path
dropped (skip_mode → 4 failures, SEG_REF → 7, SKIP-term → 1, GLOBALMV-term → 1), the wrong feature's
data → 3, the reference_select gate dropped → 3, the min gate `>=2`→`>=1` → 4 and `>=2`→`>=3` → 5, the
comp_mode dispatch inverted → 34, the single path fed the compound ctx filler → 18 **and its mirror**
(the compound path fed the single filler) → 6, the skip-pair index swap → 2, the WRITER dropping
SEG_REF → 3, a **paired** reader+writer SEG_REF drop → 4 (the ref-port-pinned expectations catch it — a
round-trip alone cannot), both index guards weakened → 2/2, and `seg_feature_active` ignoring
`segmentation_enabled` → 2. One harness pattern initially aliased into the motion-mode pair's identical
guard+skip sequence — caught as a PATTERN ERROR by the unique-anchor discipline (0.7.80's lesson paying
for itself), re-anchored, killed.

4-slice adversarial review (isolated worktrees, `sawCode` tripwires, reproduce-in-worktree refuters,
instructed to invent NEW mutant classes rather than re-run the author's list): **9 findings confirmed
(2 major, 7 minor), 0 wrong decodes on valid streams — all closed in-cut** with one code change and a
hardening test whose 11 mutants all now die: the writer's comp_mode gate was entirely unpinned through
the paired round-trip (closed/boundary states never driven; writer-only gate mutants survived → three
paired cases at 8x8 / 4x8 / ref_select-off); a single shared nb fixture made `comp_mode_ctx` = 0
everywhere (a hardcoded-ctx mutant survived → a provably nonzero-ctx fixture, pinned `== 1`, + a
leaf-built conformance case); the SEG_LVL_SKIP/GLOBALMV constant values were circular through the
constants themselves (→ absolute-slot pins at literal 6/7, the CDF-blob offset rule applied to
segmentation); a **precondition violation in the writer produced DR_OK + an unparseable stream** (a
compound pair with the gate closed emitted the compound tree the reader never parses — now surfaced as
`DR_ERR_BOUNDS`); the `r1 == INTRA_FRAME` single-classification boundary, the writer's negative-edge
guards, and the first-invalid `seg_feature_active` probes were vacuous (planted-alias + boundary cases
added); the persistent-scratch layout contract is now pinned (`AV1CCTX_SIZE == 72`, last slot ends at
size; residual documented: an alloc-site literal shrink is invisible — the arena has no red zones).
One earlier notification for this review carried a plausible but **unverifiable** result (empty output
file, journal mid-run) whose central claim failed live reproduction — discarded; only the journal-backed
completion was recorded. Details in `docs/development/state.md`.

## [0.7.80] - 2026-07-16

**Inter prediction — `read_motion_mode` (spec 5.11.27), the full gating driver + `is_scaled`.** The last
gating orchestrator: composes the 0.7.71 leaf reads (`av1_read_motion_mode_sym` / `av1_read_use_obmc`) with
the 0.7.79 warp-sample leaves into the complete 5.11.27 decision.

- **`av1_is_scaled`** (`src/av1_frame.cyr`) — does a reference frame use scaling? The stored ref's
  `RefUpscaledWidth` / `RefFrameHeight` are compared against the current `FrameWidth` / `FrameHeight` as
  14-bit ratios (`REF_SCALE_SHIFT = 14`), rounded with `+ FrameWidth/2`; "unscaled" is exactly `1 << 14` on
  **both** axes. The width/height asymmetry is the spec's: the ref contributes its *upscaled* width
  (superres never changes height). Hostile guards: a refFrame outside LAST..ALTREF, a lying
  `ref_frame_idx` slot, or zero frame dims report "scaled" instead of reading OOB — conservative, since
  scaled-ref MC is rejected anyway.
- **`av1_read_motion_mode`** (`src/av1_intermode.cyr`) — the driver. Early SIMPLE **without a symbol** on:
  `skip_mode` / `!is_motion_mode_switchable` / `min(w, h) < 8` / a GLOBALMV-family block whose global model
  is beyond TRANSLATION (only tested when `!force_integer_mv`) / compound / inter-intra
  (`RefFrame[1] == INTRA_FRAME`) / no overlappable inter neighbour. Then `find_warp_samples` runs
  (NumSamples also feeds `warp_estimation` later), and
  `force_integer_mv || NumSamples == 0 || !allow_warped_motion || is_scaled(RefFrame[0])` picks
  `@@use_obmc` (OBMC/SIMPLE) over `@@motion_mode` (3-symbol). The paired `av1_write_motion_mode` replays
  the gate and emits exactly the symbols the reader consumes.
- The 0.7.71 leaves take the `_sym` suffix (`av1_read/write_motion_mode_sym`) so the driver owns the plain
  name — the leaf = `_sym` / driver = plain convention (cyrius silently shadows duplicate fn names).

Verified against a new committed spec-literal port (`scripts/refs/motion_mode_ref.py`: the 5.11.27 branch
decision + `is_scaled`). Tests: per-gate round-trips driven **both** ways ending in an 8-bit `0xA5` literal
marker; decode-side **conformance** cases whose symbol streams are hand-built with the *leaf* writers — a
gate bug shared by the driver and its inverse round-trips cleanly, and these cases are what catch it;
driver side-effects (ws zeroed on gated paths, filled on the warp branch) + hostile inputs
(ref0 / MiSize / null out|ws → bounds error, no symbol consumed).

All **mutation-verified — 21 mutations, 0 survivors**: each of the 7 early gates dropped (skip_mode → 6
failures), `<8` → `<=8` → 2, GmType `>` → `>=` → 2, the global gate ignoring force_integer_mv → 5, each of
the isCompound/ref1/overlappable terms → 4/2/4, find_warp_samples skipped → 14, each of the 4 OBMC triggers
dropped → 5/5/4/4, use_obmc mapping inverted → 10, the warp branch reading the wrong symbol → 13, the
writer inverse against SIMPLE → 6, a **paired** reader+writer is_scaled drop → 2 (killed only by the
conformance tests — the round-trip alone is blind to it), the is_scaled rounding dropped → 2,
FRAME_W-for-UPSCALED_W → 11, the y-denominator swap → 3, and both index guards → 1/1 (made observable by
planting matching dims at the exact aliased offsets an unguarded read hits).

### Fixed
- Two mutants initially survived — both **test** weaknesses, not code defects: (1) a single binary marker
  symbol can decode correctly by luck after a one-symbol desync — replaced with an 8-bit `0xA5` literal
  (1/256 survival); (2) the slot `-1` guard-alias test planted its y-axis value at the wrong offset
  (`UPSCALED_W[7]` instead of `FRAME_H - 8` = `FRAME_W[7]`), so the unguarded read returned "scaled" anyway
  and the guard was unfalsifiable. Both fixed and re-run to kills.
- The first mutation-harness pattern for the skip_mode gate silently matched `av1_write_compound_type`'s
  identical line earlier in the file (first-occurrence replace) — mutations must be anchored on unique
  context. The accident exposed a real pre-existing gap: the compound-type **writer's** skip gate had no
  killing test (0.7.73 scope). **Closed in this cut** via a spawned follow-up session, merged back in:
  `ct_marker_rt` / `test_comptype_nosym_marker` trail the compound-type write with the 0xA5 literal marker
  in both CDF modes for both no-symbol gates (skip_mode and !is_compound) — the reader consumes zero
  symbols on those paths regardless, so only a marker can prove the writer leaked nothing.
  Mutation-verified: the original surviving mutant now fails 2 assertions.

4-slice adversarial review (isolated worktrees with the uncommitted bite copied in, `sawCode` tripwires,
every finding verified by two reproduce-in-worktree refute agents): **6 findings, 5 confirmed — all fixed
in this cut.** A mid-review-stale `dist/` (regenerated + re-verified); **two majors in test adequacy** —
the global gate's y_mode restriction was untested (an `if (1)` mutant for the GLOBALMV-family check
survived the whole suite; closed with NEWMV + ROTZOOM/AFFINE warp-branch cases) and the hostile guards'
boundaries were unpinned (three off-by-one mutants survived together; closed with ALTREF / MiSize 21 / 22 /
negative / slot-7 boundary cases); a minor (the divide-by-zero backstop had zero coverage — its deletion
now crashes the suite red); and a stale marker comment. The one refuted finding died to the best kind of
evidence: the refute agent fetched the spec's own YMode table, proving the ref port's numbering is
spec-faithful. All five review mutants re-run post-fix and killed (4 / 3 / 1 / 1 / SIGFPE), 0 survivors.
Also folded in as self-hardening: the test scan-ctx now carries the compound ref pair for compound cases
(`NONE` otherwise — faithful to `find_mv_stack` running before 5.11.28's `RefFrame[1]` mutation).
Details in `docs/development/state.md`.

## [0.7.79] - 2026-07-14

**Inter prediction — the warp-sample leaves (spec 7.10.4 `find_warp_samples` / `add_sample`, and
`has_overlappable_candidates`).** `read_motion_mode` (5.11.27) gates on both: OBMC needs an overlappable
neighbour, LOCALWARP needs `NumSamples > 0`. Extends `src/av1_mv.cyr` with:

- **`av1_has_overlappable_candidates`** — is there an inter block above or left? Checked at 8×8 granularity
  (the `+= 2` step with an `x4 | 1` odd-column probe) and clipped to the **frame**, not the tile.
- **`av1_warp_add_sample`** (7.10.4.2) — considers one neighbour: skipped unless inside, written this frame,
  sharing `RefFrame[0]`, and single-ref. It snaps to the candidate **block's** top-left, computes the block
  centre, and validates the MV delta against `Clip3(16, 112, Max(Block_Width, Block_Height))`. An invalid
  sample is kept only if it is the *first* scanned — the spec's "if no small motion vectors are found, return
  the first large one".
- **`av1_find_warp_samples`** (7.10.4.1) — scans the above row and left column (one sample if the neighbour
  is at least as large, else stepping across smaller ones), then the top-left and top-right corners, and
  applies the `NumSamples = 1` special case.
- The `Av1WarpSamples` record (`CandList[8][4]` + `NumSamples` + `NumSamplesScanned`).

Verified against a new committed spec-literal port (`scripts/refs/warp_samples_ref.py`), with the fixture
grid laid down by the **real `av1_mi_store_mode`** rather than poked by hand — which matters, because
`add_sample` reads `Mvs` at the candidate block's *top-left*, a cell that only exists if the whole footprint
was written. (My first hand-built fixture got this wrong and reported 4 valid samples for MVs 900 apart; the
tell was a candidate whose source and destination were identical.)

All **mutation-verified** (0 at baseline): inverting the compound test → 12 failures; removing the `candRow`
snap → 3; removing the first-large special case → 2; removing the `NumSamples = 1` case → 1; `>` → `>=` in
the overlappable probe → 1; the 8×8 step 2 → 1 → 1; the threshold's 112 clamp → 999 → 1; the top-right
`w4` → `h4` → 2.

### Fixed
- **Three mutations initially survived, all from one cause: a uniform, square fixture** — the same aliasing
  lesson as 0.7.76/0.7.77. A 16×16 block has `w4 == h4`, so the top-right probe's `w4` was
  indistinguishable from `h4`; it never reaches the threshold's 112 clamp; and at an *even* `MiCol` the
  `x4 | 1` probe maps both `x` and `x+1` to the same column, so the 8×8 step is unobservable. Closed with a
  non-square block (`BLOCK_8X16`) asserting the **top-right** candidate slot specifically, a 128×128 block
  with an MV delta of 120 (strictly between the clamped 112 and an unclamped 128), and an **odd** `MiCol`
  case where only column 9 carries an inter block.
- Guarded every `MiSizes` read before it indexes the 22-entry `Num_4x4_Blocks_*` tables (the grid's writer
  guards `MiSize`, but the reader shouldn't rely on that alone), and documented that the spec's
  `& ~(candH4 - 1)` is transcribed as `& (0 - candH4)` — equal in two's complement, verified exhaustively.

### Added
- **`src/av1_mv.cyr`**: `av1_has_overlappable_candidates`; `av1_warp_add_sample`; `av1_find_warp_samples`;
  the `Av1WarpSamples` record + accessors; `AV1_LEAST_SQUARES_SAMPLES_MAX`.
- **`tests/av1_mv.tcyr`**: `test_has_overlappable_candidates`, `test_find_warp_samples`,
  `test_warp_samples_badargs`, `test_warp_nonsquare_and_clamp`, `test_overlappable_granularity`.
- **`scripts/refs/warp_samples_ref.py`** — the spec-literal port.

### Scope / deferred
- The samples themselves; `warp_estimation` (7.11.3.8) — turning `CandList` into a warp model — is a later
  bite. Next: `read_motion_mode`'s full 5.11.27 gating (these leaves + `is_scaled`), then `read_ref_frames`
  and the `inter_block_mode_info` orchestrator (roadmap.md).

## [0.7.78] - 2026-07-14

**Inter prediction — the gating orchestrators (spec 5.11.28 `read_interintra_mode` + the 5.11.23
`interp_filter` tail).** 0.7.71 and 0.7.72 landed these symbols' *leaf* reads and left the gating that
decides whether each is coded "the caller's concern". This is that caller — the first bite of the
`inter_block_mode_info` arc.

- **`av1_read_interintra_mode`** — the full 5.11.28 function. The gate is `!skip_mode &&
  enable_interintra_compound && !isCompound && BLOCK_8X8 <= MiSize <= BLOCK_32X32`; outside it `interintra`
  is 0 and **nothing** is read. Inside, it composes the four leaf reads and surfaces the spec's block-level
  side-effects (`RefFrame[1] = INTRA_FRAME`, `AngleDeltaY/UV = 0`, `use_filter_intra = 0`) via an
  `Av1InterIntraRec`, since this layer owns no block record yet. `wedge_sign` is forced to 0 per the spec.
- **`av1_needs_interp_filter`** — `skip_mode` or `LOCALWARP` suppress the filter; a *large* block in
  `GLOBALMV`/`GLOBAL_GLOBALMV` needs one only when the global model is a plain `TRANSLATION` (a warp model
  carries its own filtering); everything else needs one.
- **`av1_read_interp_filters`** — the per-direction loop: a non-`SWITCHABLE` frame gives both directions the
  frame's filter with nothing coded; `SWITCHABLE` codes `enable_dual_filter ? 2 : 1` directions, each gated
  by `needs_interp_filter` (an ungated direction is `EIGHTTAP`), and without dual filter direction 1 mirrors
  direction 0.
- Paired encoder-inverses for both.

Verified by 75 new assertions. Every gated round-trip writes a **marker symbol after the gated block**, so a
reader/writer disagreement about *how many* symbols a closed gate consumes fails loudly rather than silently
desyncing. Coverage: all five gate-closing conditions and both `MiSize` bounds (`BLOCK_8X8` and `BLOCK_32X32`
are *in* the gate); `needs_interp_filter` across `skip_mode`/`LOCALWARP`/both global modes/either `GmType`
being `TRANSLATION`/the `>= 8` large boundary (incl. a small block where the `large` guard means `GLOBALMV`
*still* needs a filter); and the filter loop across non-switchable, switchable+dual, switchable+mirror, and
both suppression paths. Mutation-verified (0 at baseline): the interintra gate's `>`→`>=` → 3 failures;
inverting `isCompound` → 18; forcing `wedge_sign` to 1 → 2; `LOCALWARP`→`OBMC` → 1; `TRANSLATION`→`IDENTITY`
→ 2; `large >= 8`→`> 8` → 1; inverting the dual mirror → 3; inverting the needs gate → 13.

### Fixed
- **A duplicate function name.** The new 5.11.28 driver collided with 0.7.72's leaf `av1_read_interintra_mode`
  — and Cyrius *silently shadows* duplicate names (last-def-wins, warn-only), so this would have swapped one
  for the other without an error. The leaf is renamed `av1_read_interintra_mode_sym`, matching the
  `av1_read_compound_type_sym` precedent (leaf = `_sym`, driver = plain name).
- **A stale deferral comment** claiming the compound-reference CDF contexts are "a caller input here" — untrue
  since 0.7.76, when `av1_comp_ref_ctxs` began deriving them. (Surfaced by `make lint`, which flags an
  untracked deferral; the comment was wrong, not merely unreferenced.)

### Added
- **`src/av1_intermode.cyr`**: `av1_read_interintra_mode` / `av1_write_interintra_mode` + the
  `Av1InterIntraRec` record and accessors; `av1_needs_interp_filter`; `av1_read_interp_filters` /
  `av1_write_interp_filters`; the `AV1_BLOCK_8X8` / `AV1_BLOCK_32X32` / `AV1_EIGHTTAP` constants.
- **`tests/av1_intermode.tcyr`**: `test_read_interintra_mode_gate`, `test_needs_interp_filter`,
  `test_read_interp_filters`.

### Scope / deferred
- `read_motion_mode`'s full gating (5.11.27) still waits on `find_warp_samples` (7.10.4) and
  `has_overlappable_candidates` — its own bite. Then `read_ref_frames` + the `inter_block_mode_info`
  orchestrator, `inter_frame_mode_info`, and the inter tile decode (roadmap.md).

## [0.7.77] - 2026-07-14

**Inter prediction — the last three CDF contexts (spec §9) and the grid fields they need. Every inter
context is now derived.** `comp_group_idx` / `compound_idx` / `interp_filter` outlived the other
un-deferrals because they read per-cell state the MI record did not carry. This bite adds the fields, writes
them, and derives the contexts.

- **`Av1MiRec` grew 80 → 112** — `CompGroupIdxs`, `CompoundIdxs`, `InterpFilters[0..1]` — and
  **`av1_mi_store_mode`** now writes them exactly where spec 5.11.4 loop 1 does: `CompGroupIdxs`/
  `CompoundIdxs` inside `if (!use_intrabc)` inside `if (is_inter)`, but `InterpFilters` inside `if (is_inter)`
  and *outside* the intrabc guard — an intrabc block is inter with no compound signalling.
- **`Av1NbCtx` grew 80 → 144**, caching those neighbour values in `av1_nbctx_setup`. The spec re-reads the
  grid at ctx time; caching keeps every context a pure function of the record (as 0.7.75/0.7.76 established)
  and is equivalent, since every read is `Avail`-guarded.
- **`av1_comp_group_idx_ctx`** — a compound neighbour contributes its own `comp_group_idx`, a single
  neighbour contributes 3 only when its `RefFrame[0]` is `ALTREF`; clamped to 5.
- **`av1_compound_idx_ctx`** — the same neighbour shape, but the ALTREF bump is **1, not 3**, and there is
  **no clamp**: the spec relies on the maximum falling out at 5 (3 + 1 + 1). `fwd_eq_bck` (the order-hint
  distance comparison) stays a caller input — frame state, not neighbour state.
- **`av1_interp_filter_ctx`** — a 4-wide bank chosen by `(dir, is-compound)`, offset by the neighbours'
  agreed filter type, where a neighbour only counts if it shares this block's `RefFrame[0]` in **either** of
  its own reference slots, and 3 means "no usable neighbour".

Verified against the committed spec-literal port (`scripts/refs/nbctx_ref.py`, extended): the cache
(including the unavailable path proving the cell is *not* consulted); 10 + 6 + 13 branch-covering known
answers — the `3+3=6 → clamped to 5` case, the no-clamp max-5 case, all four `interp_filter` bank bases,
sharing via the neighbour's *second* ref slot, and every rung of the resolution ladder; a **314,928-combo
enumeration** matched to the port's digests and proving no context leaves `[0,6)`; the derived contexts
driving the real reads end-to-end; and the storage fields across the whole footprint, the `use_intrabc` gate,
the intra case, and dir independence.

All **mutation-verified** (0 at baseline): dropping the `Min(5)` clamp → 3 failures; `comp_group_idx`'s
ALTREF bump 3→1 → 4; `compound_idx`'s base 3→1 → 4; its ALTREF bump 1→3 → 4; `interp_filter`'s base `*4`→`*2`
→ 4; a wrong rung in the ladder → 2; dropping the ref1-slot share → 1; defeating the `use_intrabc` gate → 2.
`test_nbctx_layout` also caught the `Av1NbCtx` growth itself — its "last field ends at `AV1NB_SIZE`"
assertion failed until updated, which is exactly what it exists for.

### Fixed
- **`av1_nbctx_setup` was not idempotent.** The eight cached grid values were written only *inside* the
  `avail_u`/`avail_l` branches, so a **reused** record — which the inter tile decode will hold, one per block
  — let an unavailable neighbour inherit the *previous* block's values. They are now written unconditionally,
  like the reference fields already were. `test_nbctx_setup_reuse` pins it (8 failures without the fix).
- **`CompGroupIdxs` and `CompoundIdxs` were aliased in every test** — the context cases, the enumeration,
  every `av1_mi_store_mode` call site, *and* the reference port all passed the two planes equal, so reading
  the **wrong plane** was invisible in both the readers and the writer (found by the adversarial review;
  three such mutations survived the whole suite). Each context case now **poisons** the plane it must not
  read, and the store payloads are distinct: the reader swaps fail 5/2 and the store-payload swap 8. Note the
  enumeration digest cannot catch this even de-aliased — sweeping both planes over {0,1} leaves the sum
  invariant — so the poisoned known answers carry it.
- **`InterpFilters[0]`/`[1]` were aliased** in every `interp_filter` case, hiding a dir-indexing bug; the
  other direction is now poisoned (6 failures).
- **`ref1 == INTRA_FRAME` was never exercised** — the only input separating the spec's `RefFrame[1] >
  INTRA_FRAME` from `>=`, and a live one: 5.11.28 sets `RefFrame[1] = INTRA_FRAME` on an interintra block and
  `interp_filter` is read after it, which is exactly *why* the spec writes `>`. The slip silently selected a
  wrong 4-wide CDF bank; three vectors added (3 failures).
- An overclaiming test comment (`interp_filter indexes [16]`) on an enumeration that never enumerated
  `interp_filter` — narrowed to what the body actually covers.

### Added
- **`src/av1_mv.cyr`**: the four `Av1MiRec` inter fields; `av1_mi_store_mode`'s five new parameters.
- **`src/av1_intermode.cyr`**: the eight `Av1NbCtx` cache fields + their accessors;
  `av1_comp_group_idx_ctx`; `av1_compound_idx_ctx`; `av1_interp_filter_ctx`.
- **`tests/av1_intermode.tcyr`**: `test_nbctx_caches_grid_fields`, `test_comp_group_idx_ctx`,
  `test_compound_idx_ctx`, `test_interp_filter_ctx`, `test_last_ctx_enumeration`,
  `test_last_ctxs_feed_the_reads`.
- **`tests/av1_mv.tcyr`**: `test_mi_store_inter_fields`.
- **`scripts/refs/nbctx_ref.py`** (extended): the three derivations + their exhaustive digests.

### Scope / deferred
- **Every inter CDF context is now derived from the grid.** What the caller still supplies is frame-level
  state the spec also treats that way: `AvailU`/`AvailL` (`decode_block` computes them) and the order-hint
  distances behind `fwd_eq_bck`. Next is the **inter tile decode** — wiring the read layer, the contexts, the
  MI grid and the MC driver into a genuine inter frame — then the temporal scan (roadmap.md).

## [0.7.76] - 2026-07-14

**Inter prediction — the reference-context family (spec §9), completing the un-deferral of the reference
reads.** Fifteen symbols, but the spec defines only **eight** derivations and wires the rest up as aliases
("ctx is computed as in the CDF selection process for X"). Extends `src/av1_intermode.cyr` with:

- **seven `ref_count_ctx` derivations** — `av1_comp_ref_ctx` (LAST+LAST2 vs LAST3+GOLDEN),
  `av1_comp_ref_p1_ctx` (LAST vs LAST2), `av1_comp_ref_p2_ctx` (LAST3 vs GOLDEN), `av1_comp_bwdref_ctx`
  (BWDREF+ALTREF2 vs ALTREF), `av1_comp_bwdref_p1_ctx` (BWDREF vs ALTREF2), `av1_single_ref_p1_ctx`
  (all forward vs all backward), `av1_uni_comp_ref_p1_ctx` (LAST2 vs LAST3+GOLDEN);
- **`av1_is_samedir_ref_pair`** + **`av1_comp_ref_type_ctx`** — the eighth, and the only one that is not a
  count comparison: a deeply nested block over `aboveCompInter` / `leftCompInter` / `aboveUniComp` /
  `leftUniComp`, whose innermost case compares against `BWDREF_FRAME` *exactly* rather than reusing
  `is_samedir_ref_pair`;
- **`av1_single_ref_ctxs`** / **`av1_comp_ref_ctxs`** — the payoff: these fill the six-slot `refctx` and
  nine-slot `Av1CompCtxIdx` records that `av1_read_single_ref` (0.7.68) and `av1_read_compound_ref` (0.7.69)
  already take, which were caller inputs *only* because the MI grid was empty until 0.7.74. The aliases are
  expressed by **calling** the aliased function rather than duplicating its body, so the spec's "same as" is
  structural and cannot drift.

Verified against the committed spec-literal port (`scripts/refs/nbctx_ref.py`, extended with the family):
per-pair known answers isolating each context's compared frames; an alias check over 81 neighbourhoods; a
**26,244-combo exhaustive enumeration** (every `(AvailU, AvailL, aref0, aref1, lref0, lref1)` over **every**
ref value) matched to the port's per-context sum digests and proving no context ever leaves its CDF's range;
and the derived contexts driving `av1_read_single_ref` / `av1_read_compound_ref` end-to-end.

### Fixed
- **The exhaustive digest was blind to a swapped count pair.** `ref_count_ctx(a,b)` maps `a<b`/`a==b`/`a>b`
  to 0/1/2, so swapping a context's pair inverts 0↔2 — and four of these contexts have a **symmetric**
  histogram (`comp_ref` `[6208,13828,6208]`; `comp_ref_p1`/`p2`/`comp_bwdref_p1` `[4213,17818,4213]`), which
  leaves the sum *and* the per-value histogram unchanged. Mutation proved `comp_ref`'s and `comp_ref_p2`'s
  pair swaps passed the **entire suite**. `test_ref_family_direction` now drives every count context to both
  0 and 2, asserting the pair *order*; all four swaps now fail (2/2/4/3).
- **The enumeration's ref set was inadequate** — `{-1,0,1,4,5,7}` omitted `LAST2`(2), `LAST3`(3) and
  `ALTREF2`(6), exactly the frames `comp_ref_p1` / `comp_ref_p2` / `comp_bwdref_p1` / `uni_comp_ref_p1`
  discriminate, so those contexts had **unreachable values** under it (`comp_ref_p1`'s histogram was
  `[0, 3721, 1463]`). Widened to all nine values (5184 → 26,244 combos); the 0.7.75 digests were refreshed
  accordingly.

### Added
- **`src/av1_intermode.cyr`** (extended): the seven count-based ctx derivations; `av1_is_samedir_ref_pair`;
  `av1_comp_ref_type_ctx`; `av1_single_ref_ctxs`; `av1_comp_ref_ctxs`.
- **`tests/av1_intermode.tcyr`** (extended): `test_is_samedir_ref_pair`, `test_ref_family_pairs`,
  `test_ref_family_direction`, `test_ref_family_aliases`, `test_ref_family_enumeration`,
  `test_ref_ctxs_feed_the_reads`.
- **`scripts/refs/nbctx_ref.py`** (extended): the family's derivations + exhaustive per-context digests.

### Scope / deferred
- Still caller inputs: `comp_group_idx` / `compound_idx` (need `CompGroupIdxs` / `CompoundIdxs` in the grid,
  plus order-hint distances) and `interp_filter` (needs `InterpFilters`) — the next bite adds those grid
  fields. `AvailU`/`AvailL` remain the caller's, as in the spec. Then the inter tile decode (roadmap.md).

## [0.7.75] - 2026-07-14

**Inter prediction — the neighbour CDF contexts (spec 5.11.15 preamble + §9 CDF selection). The first
un-deferral.** Every inter CDF context is derived from the ABOVE and LEFT neighbours' reference frames. Those
were caller *inputs* from 0.7.68 onward because the MI grid held no decoded data; 0.7.74's storage loops
changed that, so the derivations land for real. Extends `src/av1_intermode.cyr` with:

- **`av1_nbctx_setup`** (spec 5.11.15) — snapshots the eight neighbour values from the MI grid:
  `Above`/`LeftRefFrame[0..1]`, `Above`/`LeftIntra`, `Above`/`LeftSingle`. The unavailable-neighbour defaults
  are **asymmetric**: `RefFrame[0]` falls back to `INTRA_FRAME` (so an unavailable neighbour reads as intra)
  but `RefFrame[1]` falls back to `NONE` (so it reads as single) — both are `<= INTRA_FRAME` tests, which is
  exactly why `NONE = -1` works for Single while `INTRA_FRAME = 0` works for Intra;
- **`av1_check_backward`** / **`av1_count_refs`** / **`av1_ref_count_ctx`** (§9) — the leaves the `single_ref`
  / `comp_ref` context family will compose;
- **`av1_is_inter_ctx`** — now feeds `av1_read_is_inter` (0.7.68) for real;
- **`av1_comp_mode_ctx`** — now feeds `av1_read_comp_mode` (0.7.69) for real.

Verified by 138 new assertions whose expected values come from a **spec-literal Python port**
(`scripts/refs/nbctx_ref.py`) transcribed from the spec *text*, never from the Cyrius — so the ground truth is
independent of the code under test rather than a restatement of it. Coverage: the `setup` preamble (incl. the
unavailable path proving the grid is *not* consulted, since those cells hold different values);
`check_backward` across every ref value with both boundaries (`GOLDEN` = 4 is not backward, `BWDREF` = 5 is,
`ALTREF` = 7 is, 8 is not); `count_refs` + `ref_count_ctx`; **20 branch-covering known answers**; a **full
5184-combo enumeration** of every `(AvailU, AvailL, aref0, aref1, lref0, lref1)` over a ref set spanning
NONE/INTRA/forward/backward, checked against the port's exhaustive digest (sums 2736 / 10672 plus per-value
histograms) and proving no context ever leaves `[0,4)` / `[0,5)` — an out-of-range context would index the
`Is_Inter[4]` / `Comp_Mode[5]` CDF blob out of bounds; and a derived context driving `av1_read_is_inter`
end-to-end.

Every test is **mutation-verified**: `is_inter` both-intra 3→2 → 5 failures; `comp_mode` XOR→OR → 4;
unavailable `aref1` NONE→INTRA → 1; `check_backward` `>=`→`>` → 10; the `<= INTRA_FRAME` Single test →`<` → 6;
`ref_count_ctx` `<`→`<=` → 2; `comp_mode` neither-avail 1→0 → 4 (all 0 at baseline).

### Added
- **`src/av1_intermode.cyr`** (extended): the `Av1NbCtx` record + `av1_nbctx_new` / `av1_nbctx_setup` and its
  accessors; `av1_check_backward`; `av1_count_refs`; `av1_ref_count_ctx`; `av1_is_inter_ctx`;
  `av1_comp_mode_ctx`.
- **`tests/av1_intermode.tcyr`** (extended): `test_nbctx_layout`, `test_nbctx_setup`, `test_check_backward`,
  `test_count_refs`, `test_nbctx_known_answers`, `test_nbctx_full_enumeration`, `test_nbctx_feeds_the_read`.
- **`scripts/refs/`** (new): committed spec-literal reference ports + a README on why they belong in the repo.
  `nbctx_ref.py` is the first. Reference ports were previously written to a temporary scratch path that is
  wiped between sessions — so the eight ports cited across `CHANGELOG.md` / `docs/sources.md`
  (`mvscan_ref.py`, `mvdriver_ref.py`, `mv_ref.py`, `mc_driver_ref.py`, `emu_edge.py`, `mc_put8tap.py`,
  `resize_ref.py`, `upscale_geom.py`) no longer exist and those citations are dead. The AV1 spec remains the
  actual oracle and the known answers stay re-derivable from it (the 0.7.75 review demonstrated this by
  re-deriving all 11 digest constants from the spec without the port), but the dead citations are a doc-claim
  defect — flagged for the 0.7.x doc-claim audit.

### Fixed
- **The `Av1NbCtx` record's field offsets were unpinned** — the same circularity class as the 0.7.73 CDF-blob
  finding: `av1_nbctx_setup` stores through the same `AV1NB_*` symbols the accessors read back, so a
  self-consistent offset error cancels out. `test_nbctx_layout` now pins every offset absolutely, pins the
  last field's end to `AV1NB_SIZE` (so a field added past the record cannot silently overflow the alloc), and
  proves no two fields overlap. Mutation-verified: `AV1NB_LSINGLE` overlapping `AV1NB_ASINGLE` → 23 failures,
  `AV1NB_SIZE` 80→72 → 1, the `aref` list-stride 8→16 → 7 (all 0 before).

### Scope / deferred
- The two contexts whose inputs the grid already carries. Still caller inputs: the `single_ref` /
  `comp_ref` / `comp_ref_type` / `uni_comp_ref` / `comp_bwdref` family (derivable now via `count_refs`, a
  later bite), and the contexts needing grid fields drishti does not carry yet — `comp_group_idx` /
  `compound_idx` (`CompGroupIdxs` / `CompoundIdxs` + order hints) and `interp_filter` (`InterpFilters`).
  `AvailU`/`AvailL` remain the caller's, as in the spec (`decode_block` computes them). Then the inter tile
  decode (roadmap.md).

## [0.7.74] - 2026-07-14

**Inter prediction — the MI-grid population (spec 5.11.4 `decode_block` storage loops). This closes the
producer→consumer loop.** The MV-prediction scans (0.7.64) read a per-4×4 `Av1MiRec` grid; until now that
grid was caller/test-built. These write a *decoded* block's mode info across its `bw4 × bh4` footprint, so
the next block's scans see the previous block's decoded values — the premise spatial MV prediction rests on.
Extends `src/av1_mv.cyr` with:

- **`av1_mi_store_mode`** — the spec's first storage loop (post-`mode_info`): `YModes` / `RefFrames` /
  `Mvs` across the footprint. `Mvs` are stored only for an inter block, and `Mvs[..][1]` only when compound
  (the spec's `refList < 1 + isCompound`, `isCompound = RefFrame[1] > INTRA_FRAME`);
- **`av1_mi_store_final`** — the spec's second storage loop (post-`residual`): `IsInters` / `MiSizes`, plus
  drishti's own `avail` marker (the per-cell "decoded this frame" flag the scan-point check reads), which
  belongs here rather than in loop 1 because it is only true once the block is fully decoded.

The two loops are transcribed faithfully rather than merged: the fields the grid carries happen to be
disjoint across them, so merging would be equivalent today, but keeping them apart lets the inter tile decode
place each exactly where the spec does once `compute_prediction`/OBMC lands between them.

Writes are **clipped** to the grid: an AV1 block may legitimately extend past the frame edge (the frame is
padded to superblock multiples) and the spec's arrays are sized for that, but drishti's grid is frame-sized.
The overhanging cells are never read back — `is_inside` gates every scan read to the tile. The clip, plus a
`MiSize` range guard placed before the 22-entry `Num_4x4_Blocks_*` table load, is what keeps a hostile
`MiSize`/`MiRow` from writing out of bounds.

Verified by 1,210 new assertions (946 → 1,465 in the suite), each **mutation-verified** rather than assumed.
`test_mi_grid_addressing` pins `av1_mv_grid_cell`'s absolute mapping (base, column stride, row stride =
`fmi_cols` cells, last cell ending exactly at the grid end) so the footprint tests built on it are not
circular. `test_mi_store_footprint` and `test_mi_store_mode_footprint` walk **every** grid cell asserting the
touched set is exactly the expected rectangle — separately for each storage loop, and for a square block *and*
a non-square 2×4 one, so width/height cannot be transposed undetected. Plus field-mapping (incl. the real
single-ref `RefFrame[1] = NONE = -1`, not just the `INTRA_FRAME = 0` boundary), clipping (incl. no row-wrap),
bad-arg rejection, and **`test_mi_store_closes_the_loop`** — store a decoded neighbour through the real
storage loops, run `av1_mv_scan_row`, and assert the scan finds the stored MV.

Measured mutation results against the 1,465-assertion baseline: transposing `bw4`/`bh4` in both loops → **18**
failures; in `av1_mi_store_mode` only → **10**; dropping the column clip → **2**; dropping the `MiSize` guard
→ **1**; changing `isCompound` from `ref1 > INTRA_FRAME` to `!= INTRA_FRAME` → **2**. The last two were each
**0** before the review-driven tests were added — i.e. `av1_mi_store_mode`'s footprint and the `NONE`-vs-
`INTRA_FRAME` distinction were genuinely unverified until then.

### Added
- **`src/av1_mv.cyr`** (extended): `av1_mi_store_mode` / `av1_mi_store_final`; the `AV1_MV_BLOCK_SIZES`
  constant (this module is wired before `av1_intermode.cyr`, which carries its own `AV1_BLOCK_SIZES`).
- **`tests/av1_mv.tcyr`** (extended): `test_mi_grid_addressing`, `test_mi_store_footprint`,
  `test_mi_store_mode_footprint`, `test_mi_store_fields`, `test_mi_store_clip`, `test_mi_store_badargs`,
  `test_mi_store_closes_the_loop` — 1,465 assertions total.

### Scope / deferred
- The grid carries the scan-consumed subset only. The spec's `UVModes` / `CompGroupIdxs` / `CompoundIdxs` /
  `InterpFilters` (loop 1) and `Skips` / `SkipModes` / `TxSizes` / `SegmentIds` / `Palette*` / `DeltaLFs`
  (loop 2) are not carried yet — `CompGroupIdxs`/`CompoundIdxs`/`InterpFilters` are exactly what the deferred
  neighbour CDF contexts (spec 8.3/9) need, so wiring them is the natural next step, followed by the inter
  tile decode (roadmap.md).

## [0.7.73] - 2026-07-14

**Inter prediction — `read_compound_type` (spec 5.11.29), completing the inter mode-info read layer.** How a
compound block's two predictors are BLENDED. Unlike the preceding leaf-read bites this is the full spec
**driver**: it composes three new symbols with 0.7.72's shared `@@wedge_index` and two `L(1)` literals, and
resolves `compound_type` across every branch. Extends `src/av1_intermode.cyr` with:

- **`av1_read_comp_group_idx`** / **`av1_read_compound_idx`** (binary, 6 contexts each) +
  **`av1_read_compound_type_sym`** (binary — `COMPOUND_TYPES` is 2, and the symbol value *is* the enum:
  `COMPOUND_WEDGE` = 0 / `COMPOUND_DIFFWTD` = 1, no remap), `MiSize`-indexed;
- **`av1_read_compound_type`** — the driver: `skip_mode` → `COMPOUND_AVERAGE` with nothing coded; the
  `isCompound` path reads `comp_group_idx` (when `enable_masked_compound`), then either the jnt-comp branch
  (`compound_idx` → `COMPOUND_AVERAGE` / `COMPOUND_DISTANCE`) or the masked branch
  (`Wedge_Bits[MiSize] == 0` **forces** `COMPOUND_DIFFWTD`, else the `compound_type` symbol), then
  `wedge_index` + `wedge_sign` for `COMPOUND_WEDGE` or `mask_type` for `COMPOUND_DIFFWTD`; the **non-compound**
  path reads *no symbol at all* — `compound_type` falls out of `interintra` / `wedge_interintra`
  (`COMPOUND_WEDGE` / `COMPOUND_INTRA` / `COMPOUND_AVERAGE`), and notably does **not** re-read
  `wedge_index`/`wedge_sign` (5.11.28 already read them — the spec's wedge block nests inside `isCompound`);
- **`Wedge_Bits[22]`** (§10) + the `av1_comptype_*` output record (`compound_type`, `comp_group_idx`,
  `compound_idx`, `wedge_index`, `wedge_sign`, `mask_type`);
- the `av1_iicdf` blob grew **464 → 566** — `comp_group_idx` `[464,482)`, `compound_idx` `[482,500)`,
  `compound_type` `[500,566)` — exactly filling `AV1IICDF_SIZE`;
- the paired `av1_write_compound_type` encoder-inverse (emits exactly the symbols the reader consumes, in
  the same order).

Verified by 1,343 new assertions: an **exhaustive** per-row §10 diff of all three new tables (6 + 6 + 22)
plus a check that the pre-existing `[0,464)` inter-intra region is byte-for-byte unchanged, the full
`Wedge_Bits` table, and a **round-trip over every driver branch** — `skip_mode`; the three non-compound
outcomes (incl. the wedge-fields-stay-0 case); the `comp_group_idx == 0` branch (jnt on/off, both
`compound_idx` values, `!enable_masked_compound`); the `comp_group_idx == 1` branch (`WEDGE` → index+sign,
`DIFFWTD` → both `mask_type` values, and the `n == 0` forced-`DIFFWTD` case); plus a sweep over **all 9
wedge-capable `MiSize` × all 16 `wedge_index` values** — each static + adaptive. A **record-reuse** test
decodes into a deliberately dirtied record and asserts the spec's `comp_group_idx = 0` / `compound_idx = 1`
initialization and every not-written field are reset, so no state leaks between blocks.

### Added
- **`src/av1_intermode.cyr`** (extended): `av1_read_compound_type` / `av1_write_compound_type` +
  `av1_read_comp_group_idx` / `av1_read_compound_idx` / `av1_read_compound_type_sym` + paired writers; the
  `av1_iicdf_groupidx` / `compidx` / `comptype` accessors; `av1_wedge_bits`; the `av1_comptype_new` record +
  `av1_comptype_type`/`group_idx`/`comp_idx`/`wedge_idx`/`wedge_sign`/`mask_type` accessors; the
  `AV1_COMPOUND_TYPES` / `AV1_COMP_GROUP_IDX_CONTEXTS` / `AV1_COMPOUND_IDX_CONTEXTS` / `AV1_COMPOUND_*` /
  `AV1_UNIFORM_45*` constants.
- **`tests/av1_intermode.tcyr`** (extended): `test_comptype_cdf`, `test_wedge_bits`, `test_comptype_nosym`,
  `test_comptype_group0`, `test_comptype_group1`, `test_comptype_wedge_sweep`.

### Fixed
- **CDF-blob verification was circular** (found by the 0.7.73 adversarial review, which *proved* it by
  mutation rather than argument). `av1_*cdf_fill` writes each row through the same accessor the "exhaustive
  per-row §10 diff" reads it back through, so any self-consistent base/stride error cancelled out exactly;
  and the row-checkers asserted only `c0` + the terminator, never the adaptation-count slot — which is
  precisely the slot an ascending fill clobbers when rows overlap. Two shipping-breaking mutations
  (`av1_iicdf_compidx` and `av1_iicdf_comptype` stride 3→2) left the **entire suite green**. This silently
  weakened the per-row verification claimed since 0.7.71. Fixed by (a) asserting the trailing count slot in
  every row-checker (`av1_t_chk2`/`chk3`/`chk4`/`chk16`), making row overlap destructive and therefore
  detectable, and (b) adding `test_iicdf_layout` / `test_imcdf_layout` / `test_refcdf_layout`, which pin each
  group's **absolute** byte offset, stride, and row count — derived from the documented layout, not from the
  accessors — with each group's end pinned to the next group's base and the final group's end pinned to
  `AV1*CDF_SIZE`. Verified by re-running the mutations: `compidx` stride → 7 failures, `comptype` stride → 23,
  `av1_imcdf_motionmode` stride → 23, `av1_refcdf_singleref` base → 2, `av1_iicdf_wedgeidx` stride → 23
  (all previously 0). The hole is closed retroactively for the `av1_imcdf` (0.7.71), `av1_refcdf` (0.7.68)
  and `av1_iicdf` (0.7.72) blobs, not just this bite's.
- An `Av1CompTypeRec` field comment overclaimed: `wedge_index`/`wedge_sign` are valid only when
  `isCompound && compound_type == COMPOUND_WEDGE` — a *non*-compound block can also resolve to
  `COMPOUND_WEDGE` (via `wedge_interintra`) and there both stay 0, since 5.11.28 already read the interintra
  wedge. Since 0 is a legal `wedge_index`, the unqualified comment was a trap for the MC stage that will
  consume this record.

### Scope / deferred
- The `comp_group_idx` / `compound_idx` CDF contexts (spec 9 — neighbour + order-hint derived) remain caller
  inputs, as with the single-ref / compound-ref neighbour counts (0.7.68/0.7.69). **With this the inter
  mode-info bitstream-read layer is COMPLETE**; next is the MI-grid population (writing the decoded
  RefFrames/Mvs/YModes/MiSizes/IsInter into the grid the MV scans read), then the inter tile decode
  (roadmap.md).

## [0.7.72] - 2026-07-14

**Inter prediction — the inter-intra reads (spec 5.11.28 `read_interintra_mode`).** The inter-intra
prediction signalling: a single-prediction inter block (`BLOCK_8X8`..`BLOCK_32X32`) may additionally blend
with an INTRA predictor. Adds the four entropy-coded reads to `src/av1_intermode.cyr`:

- **`av1_read_interintra`** — the binary `@@interintra` symbol (blend with intra or not), CDF
  `Inter_Intra[Size_Group[MiSize]-1]`;
- **`av1_read_interintra_mode`** — the 4-symbol `@@interintra_mode` (`II_DC_PRED` / `II_V_PRED` /
  `II_H_PRED` / `II_SMOOTH_PRED`), CDF `Inter_Intra_Mode[Size_Group[MiSize]-1]`;
- **`av1_read_wedge_interintra`** — the binary `@@wedge_interintra` (wedge vs intra blending), CDF
  `Wedge_Inter_Intra[MiSize]`;
- **`av1_read_wedge_index`** — the 16-symbol `@@wedge_index` (the wedge mask direction/offset), CDF
  `Wedge_Index[MiSize]` — shared with the compound_type wedge (5.11.29, a later bite);
- a **new CDF blob `av1_iicdf`** (464 i64) tiling the four §10 tables — `inter_intra` `[0,9)`,
  `inter_intra_mode` `[9,24)`, `wedge_interintra` `[24,90)`, `wedge_index` `[90,464)` — with the
  `av1_iicdf_interintra`/`iimode`/`wedgeii`/`wedgeidx` accessors, an `av1_iicdf_put16` 16-symbol filler +
  `av1_iicdf_wedge_unif` for the uniform default rows, reusing the existing `av1_size_group`
  ([av1_modeinfo.cyr](src/av1_modeinfo.cyr)) for the `Size_Group[MiSize]-1` context;
- the paired `av1_write_*` encoders.

Verified by exhaustive assertions: an **exhaustive** per-row §10 diff of all four tables
(`Default_Inter_Intra_Cdf` / `Default_Inter_Intra_Mode_Cdf` / `Default_Wedge_Inter_Intra_Cdf` /
`Default_Wedge_Index_Cdf`, incl. all 15 cumulative freqs of every `Wedge_Index` row), an
`interintra` + `interintra_mode` round-trip over **all 3 size groups** (`MiSize` 3/6/9 → ctx 0/1/2), a
`wedge_interintra` + `wedge_index` round-trip over **all 22 `MiSize` × every value** (16 wedge indices
each), and an adaptive-CDF round-trip.

### Added
- **`src/av1_intermode.cyr`** (extended): the `av1_iicdf` blob (`av1_iicdf_new`/`blob`/`fill` +
  `av1_iicdf_interintra`/`iimode`/`wedgeii`/`wedgeidx` + `av1_iicdf_put16` / `av1_iicdf_wedge_unif`);
  `av1_read_interintra` / `av1_read_interintra_mode` / `av1_read_wedge_interintra` /
  `av1_read_wedge_index` + their paired writers; the `AV1_INTERINTRA_MODES` / `AV1_BLOCK_SIZE_GROUPS` /
  `AV1_WEDGE_TYPES` / `AV1_II_*` constants.
- **`tests/av1_intermode.tcyr`** (extended): `test_interintra_cdf` (exhaustive per-row §10 diff via
  `av1_t_chk16` / `av1_t_chk4` / `av1_t_chk_wunif`), `test_interintra_rt`, `test_wedge_rt`,
  `test_interintra_adaptive`.

### Scope / deferred
- The four per-symbol inter-intra reads only. The gating (`!skip_mode && enable_interintra_compound &&
  !isCompound && BLOCK_8X8 <= MiSize <= BLOCK_32X32`) and the side-effects it drives
  (`RefFrame[1] = INTRA_FRAME`, `AngleDeltaY/UV = 0`, `wedge_sign = 0`) are caller-level. `read_compound_type`
  (5.11.29 — `comp_group_idx` / `compound_idx` / `compound_type` + `wedge_sign`/`mask_type` literals, which
  reuses the `Wedge_Index` CDF here) is the next bite; then MI-grid population + inter tile decode
  (roadmap.md).

## [0.7.71] - 2026-07-14

**Inter prediction — the remaining inter mode-info reads: `interp_filter` (spec 5.11.30) + `motion_mode`
(spec 5.11.27).** The last per-symbol reads of the inter mode-info block, closing out the read layer.
Extends `src/av1_intermode.cyr` with:

- **`Interp_Filter`** — the 3-symbol interpolation-filter CDF (`Interp_Filter[16][4]` from §10, indexed by
  the 16-way neighbour context) + `av1_read_interp_filter` / `av1_write_interp_filter`
  (`EIGHTTAP` / `EIGHTTAP_SMOOTH` / `EIGHTTAP_SHARP`);
- **`Motion_Mode`** + **`Use_Obmc`** — the motion-mode reads (spec 5.11.27), both `MiSize`-indexed:
  `av1_read_motion_mode` (the 3-symbol `SIMPLE` / `OBMC` / `LOCALWARP` on the warp-allowed path,
  `Motion_Mode[22][4]`) and `av1_read_use_obmc` (the binary `OBMC`-vs-`SIMPLE` on the warp-disabled path,
  `Use_Obmc[22][3]`), + their paired writers;
- the inter-mode CDF blob grew **123 → 341** entries — `interp` `[123,187)` (16×4), `motion_mode`
  `[187,275)` (22×4), `use_obmc` `[275,341)` (22×3) — exactly filling `AV1IMCDF_SIZE`, with the new
  `av1_imcdf_interp` / `av1_imcdf_motionmode` / `av1_imcdf_useobmc` accessors + the `av1_imcdf_put3`
  3-symbol filler.

Verified by 792 assertions (321 new): an **exhaustive** CDF-structure check — **every** row of all three
tables (16 `Interp_Filter` + 22 `Motion_Mode` + 22 `Use_Obmc`) diffed per-value against §10
(`Default_Interp_Filter_Cdf` / `Default_Motion_Mode_Cdf` / `Default_Use_Obmc_Cdf`), plus that the
pre-existing `[0,123)` region (`compound_mode[0]`, `new_mv[0]`) is byte-for-byte unchanged after the blob
grew — an `interp_filter` round-trip over **all 16 contexts × 3 filters**, a `use_obmc` + `motion_mode`
round-trip over **all 22 `MiSize` × every value**, and an adaptive-CDF round-trip. A **3-slice adversarial
spec review** (blob layout + accessor arithmetic / read semantics vs spec / test adequacy, each finding
adversarially verified) returned **no confirmed defects** — it confirmed the layout fills 341 slots with no
overlap or OOB, the symbol alphabets (3/2/3) and `AV1_MM_*` ordering match the spec; a refuted
test-coverage note (that a self-round-trip cannot catch a *shared* CDF value bug) was folded in anyway as
the exhaustive per-row §10 diff above. **22,246 suite assertions + 1,140 fuzz assertions, all green;
`make lint` + `make fmt-check` green.**

### Added
- **`src/av1_intermode.cyr`** (extended): the `Interp_Filter` / `Motion_Mode` / `Use_Obmc` CDFs
  (`av1_imcdf_interp` / `av1_imcdf_motionmode` / `av1_imcdf_useobmc` + `av1_imcdf_put3`);
  `av1_read_interp_filter` / `av1_read_use_obmc` / `av1_read_motion_mode` + their paired writers; the
  `AV1_INTERP_FILTERS` / `AV1_INTERP_FILTER_CONTEXTS` / `AV1_MOTION_MODES` / `AV1_BLOCK_SIZES` /
  `AV1_MM_SIMPLE` / `AV1_MM_OBMC` / `AV1_MM_LOCALWARP` constants.
- **`tests/av1_intermode.tcyr`** (extended): `test_interp_motion_cdf` (exhaustive per-row §10 diff via
  `av1_t_chk3` / `av1_t_chk2`), `test_interp_filter_rt`, `test_motion_mode_rt`,
  `test_interp_motion_adaptive` — 792 assertions total.

### Scope / deferred
- The per-symbol `interp_filter` + `motion_mode` / `use_obmc` reads only. The gating that decides whether
  each is coded (`interpolation_filter == SWITCHABLE` + `needs_interp_filter`; the warp/OBMC
  eligibility that selects the `motion_mode`-vs-`use_obmc` path) is caller-level. `compound_type` /
  interintra (5.11.28/5.11.29), then MI-grid population + inter tile decode, are later bites (roadmap.md).
  With this, the inter block's full mode + reference + MV + interp + motion-mode bitstream-read layer is
  complete.

## [0.7.70] - 2026-07-13

**Inter prediction — the compound mode path (spec 5.11.32), completing the inter mode + MV read.** The
compound analog of 0.7.67's single-prediction mode reads: decode a compound inter block's mode and *both*
motion vectors. Extends `src/av1_intermode.cyr` with:

- **`Compound_Mode`** — the 8-symbol mode CDF (from §10) added to the inter-mode CDF blob (grew 51→123),
  plus the `Compound_Mode_Ctx_Map[3][5]` table and `av1_compound_mode_ctx` (the CDF context from
  `RefMvContext>>1` × `Min(NewMvContext, COMP_NEWMV_CTXS-1)`);
- **`av1_read_compound_mode`** — the `compound_mode` symbol → `YMode = NEAREST_NEARESTMV + compound_mode`
  (one of the eight compound modes);
- **`av1_get_mode`** — the per-list mode split (a compound YMode → NEWMV / NEARESTMV / NEARMV / GLOBALMV
  for each reference list);
- **the `assign_mv` refactor** — a per-list `av1_assign_mv_list` (the predictor + `read_mv` for NEWMV,
  now indexing `RefStackMv[pos][list]` / `GlobalMvs[list]`), with `av1_assign_mv_single` delegating to it
  (behaviour-preserving) and a new `av1_assign_mv_compound` that fills both lists (the two NEWMV reads in
  list order);
- **`av1_has_nearmv`** + `read_drl_idx` / `write_drl_idx` extended to the compound modes (`NEW_NEWMV` in
  the NEWMV DRL loop, the `has_nearmv` modes in the NEAR loop);
- the paired `av1_write_compound_mode` encoder.

Verified by 471 assertions (75 new): a `Compound_Mode` CDF + ctx-map check, a `get_mode` truth-table over
every compound mode × both lists, and a full **compose round-trip** across **all 8 compound modes** (encode
`compound_mode` + DRL + the NEW MV diffs in list order → decode → assert YMode / RefMvIdx / `Mv[0]` /
`Mv[1]`), with the refactor confirmed by the still-passing 0.7.67 single-prediction tests. A **4-slice
adversarial spec review** (compound_mode CDF+ctx / get_mode / assign_mv+drl / tests + libaom-dav1d
cross-check, each finding adversarially verified) returned **no findings** — because a self-round-trip
cannot catch a *shared* encode/decode bug, reviewers byte-for-byte diffed the CDF against §10, built the
full `get_mode` truth table from the spec (asymmetric modes not list-swapped, cross-checked against
libaom's `compound_ref0/ref1_mode` LUTs), confirmed `assign_mv`'s per-list predictors + read order, and
proved the two DRL branches are mutually exclusive across all 12 modes (equivalent to the spec's else-if).
**21,925 suite assertions + 1,140 fuzz assertions, all green; `make lint` + `make fmt-check` green.**

### Added
- **`src/av1_intermode.cyr`** (extended): the `Compound_Mode` CDF (`av1_imcdf_compmode` + `av1_imcdf_put8`)
  + `av1_compmode_ctxmap` / `av1_compound_mode_ctx`; `av1_read_compound_mode` / `av1_write_compound_mode`;
  `av1_get_mode`; `av1_assign_mv_list` / `av1_assign_mv_compound`; `av1_has_nearmv`; the compound
  extension of `av1_read_drl_idx` / `av1_write_drl_idx`.
- **`tests/av1_intermode.tcyr`** (extended): `test_compound_mode_cdf`, `test_get_mode`,
  `test_compound_mode_rt` — 471 assertions total.

### Scope / deferred
- The compound MODE determination + `get_mode` + the two-list `assign_mv`. `use_intrabc`, the
  `skip_mode` / segment-forced YMode branches, motion mode, interp filter, and compound type are the
  caller's concern / later bites (roadmap.md). With this, the inter block's mode + reference + MV
  bitstream-read layer is complete; the remaining pieces feed the MI-grid population + inter tile decode.

## [0.7.69] - 2026-07-13

**Inter prediction — the compound reference path (spec 5.11.25).** The else-branch mirror of 0.7.68's
single-reference path: which *pair* of references a compound inter block uses. Extends
`src/av1_intermode.cyr` with:

- **the compound CDF families** — `Comp_Mode[5]`, `Comp_Ref_Type[5]`, `Comp_Ref[3][3]`,
  `Comp_Bwd_Ref[3][2]`, `Uni_Comp_Ref[3][3]`, transcribed per-value from §10 (the reference-CDF blob
  grew 66 → 168 entries, the +102 exactly the added families);
- **`av1_read_comp_mode`** — the `@@comp_mode` symbol (`SINGLE_REFERENCE` vs `COMPOUND_REFERENCE`);
- **`av1_read_compound_ref`** — `comp_ref_type` picks unidirectional vs bidirectional. Unidir yields one
  of four same-direction pairs (`LAST`+`LAST2`, `LAST`+`LAST3`, `LAST`+`GOLDEN`, `BWDREF`+`ALTREF`) via
  `uni_comp_ref`/`_p1`/`_p2`; bidir picks a forward `RefFrame[0]` (`comp_ref`/`_p1`/`_p2`) + a backward
  `RefFrame[1]` (`comp_bwdref`/`_p1`). Per-symbol CDF contexts are a caller input (the neighbour count,
  spec 8.3, is deferred as in the single-ref bite);
- the paired `av1_write_comp_mode` / `av1_write_compound_ref` encoders — the latter classifies unidir
  vs bidir from the `(RefFrame[0], RefFrame[1])` pair and emits the matching tree.

Verified by 396 assertions (74 new): a compound CDF-structure check against §10, a `comp_mode`
round-trip over every context, and a round-trip of **all 16 compound reference pairs** (4 unidirectional
+ 12 bidirectional), static and adaptive. A **3-slice adversarial spec review** (CDF tables + grown
layout / decode tree / encoder-inverse + comp_mode + tests + libaom-dav1d cross-check, each finding
adversarially verified) returned **no findings** — because a self-round-trip cannot catch a *shared*
encode/decode bug, reviewers byte-for-byte diffed all five CDF families against §10, confirmed the
66→168 blob bump tiles with no overlap or OOB, verified the decode tree for every leaf (p-senses not
inverted), and hand-traced the encoder's unidir/bidir classification — including the tricky (`LAST`,
`BWDREF`/`ALTREF2`/`ALTREF`) pairs, which are *bidir* (the forward `LAST` paired with a backward ref)
vs the *unidir* (`LAST`, `LAST2`/`LAST3`/`GOLDEN`) — and its inverse for all 16 pairs. **21,850 suite
assertions + 1,140 fuzz assertions, all green; `make lint` + `make fmt-check` green.**

### Added
- **`src/av1_intermode.cyr`** (extended): the `Comp_Mode` / `Comp_Ref_Type` / `Comp_Ref` /
  `Comp_Bwd_Ref` / `Uni_Comp_Ref` CDF families (`av1_refcdf_compmode` / `_comprftype` / `_compref` /
  `_compbwdref` / `_unicompref`); `av1_read_comp_mode` / `av1_read_compound_ref` (5.11.25) +
  `av1_write_comp_mode` / `av1_write_compound_ref`; the `Av1CompCtxIdx` context-slot layout.
- **`tests/av1_intermode.tcyr`** (extended): compound CDF-structure asserts, `test_comp_mode_rt`,
  `test_compound_ref_unidir` / `_bidir` / `_adaptive` — 396 assertions total.

### Scope / deferred
- The compound reference SELECTION tree + `comp_mode`. The `comp_mode` gate (`reference_select &&
  Min(bw4,bh4) >= 2`), the skip_mode / segment branches, and the neighbour-count CDF contexts (spec 8.3)
  are the caller's concern / caller inputs; the compound MODE path (`compound_mode` + the two-list
  `assign_mv`), motion mode, interp filter, and compound type are later bites (roadmap.md).

## [0.7.68] - 2026-07-13

**Inter prediction — the reference-selection reads (spec 5.11.30 + 5.11.25, single prediction).** The
inter block's reference layer: which references the block uses. Extends `src/av1_intermode.cyr` with:

- **the Is_Inter + Single_Ref CDFs** — transcribed per-value from the §10 defaults (`Is_Inter[4]`,
  `Single_Ref[3][6]`) into a 66-entry blob (`av1_refcdf_new` / `_blob` + accessors);
- **`av1_read_is_inter`** (5.11.30) — the `@@is_inter` symbol (intra vs inter) via `Is_Inter[ctx]`;
- **`av1_read_single_ref`** (5.11.25, the single-reference else-branch of `read_ref_frames`) — the
  `single_ref_p1..p6` binary tree decoding `RefFrame[0]` from the seven references (the four forward
  `LAST` / `LAST2` / `LAST3` / `GOLDEN` via `p1=0` then `p3`/`p4`/`p5`, the three backward `BWDREF` /
  `ALTREF2` / `ALTREF` via `p1=1` then `p2`/`p6`), writing `RefFrame[0..1]` (`[1]` = `NONE`);
- the paired `av1_write_is_inter` / `av1_write_single_ref` encoders.

Each of the six `single_ref_pN` symbols draws its CDF from `Single_Ref[ctx][N-1]` where `ctx` is a
count of the neighbours' reference usage (spec 8.3) — a caller input here (the neighbour count is
deferred, as the MV-prediction scans deferred their tile bounds). Verified by 322 assertions (56 new):
a CDF-structure check against §10, an `is_inter` round-trip over both symbol values × every context,
and a round-trip of **all seven single references** (each codes a unique `p1..p6` path), in both static
and adaptive CDF modes. A **3-slice adversarial spec review** (CDF tables + layout / the single_ref
tree + encoder-inverse / is_inter + safety + tests + libaom-dav1d cross-check, each finding
adversarially verified) returned **no findings** — because a self-round-trip cannot catch a *shared*
encode/decode bug, reviewers per-value-diffed all 22 CDF values against §10, verified the `p1..p6` →
RefFrame tree against the spec pseudocode, confirmed the §9 CDF-index mapping (`p1→j0 … p6→j5`)
independently, hand-traced the encoder inverse for all seven references, and cross-checked against
libaom/dav1d. **21,776 suite assertions + 1,140 fuzz assertions, all green; `make lint` + `make
fmt-check` green.**

### Added
- **`src/av1_intermode.cyr`** (extended): the `Is_Inter` / `Single_Ref` CDF family (`av1_refcdf_*`);
  `av1_read_is_inter` / `av1_read_single_ref` (5.11.30 / 5.11.25) + `av1_write_is_inter` /
  `av1_write_single_ref`; `AV1_REF_NONE`.
- **`tests/av1_intermode.tcyr`** (extended): `test_refcdf_structure`, `test_is_inter_rt`,
  `test_single_ref_rt` — 322 assertions total.

### Scope / deferred
- The SINGLE-reference path only. `is_inter`'s `skip_mode` / segment-forced branches are the caller's
  concern; the neighbour-count CDF contexts (spec 8.3) are caller inputs; and the COMPOUND reference
  path (`comp_mode` / `comp_ref_type` / `uni_comp_ref` / `comp_ref` / `comp_bwdref`) is a later bite
  (roadmap.md).

## [0.7.67] - 2026-07-13

**Inter prediction — the single-prediction inter mode reads (spec 5.11.32).** The bite where the
MV-prediction arc **composes**: given a `find_mv_stack` context (the entropy contexts + the candidate
stack + `GlobalMvs`, all from `av1_mv.cyr`), decode an inter block's mode and motion vector. Extends
`src/av1_intermode.cyr` with:

- **the inter-mode CDF family** — `New_Mv` / `Zero_Mv` / `Ref_Mv` / `Drl_Mode`, transcribed per-value
  from the §10 defaults into a 51-entry blob (`av1_imcdf_new` / `_blob` + accessors);
- **`av1_read_inter_mode`** — the single-prediction YMode: `new_mv` (→ NEWMV) else `zero_mv`
  (→ GLOBALMV) else `ref_mv` (→ NEARESTMV / NEARMV), each read with its `find_mv_stack` context
  (`NewMvContext` / `ZeroMvContext` / `RefMvContext`);
- **`av1_read_drl_idx`** — the DRL predictor index `RefMvIdx`: NEWMV scans `drl_mode` over idx 0..1,
  NEARMV starts at 1 and scans idx 1..2, each read only when `NumMvFound > idx + 1`, indexed by
  `DrlCtxStack[idx]`;
- **`av1_assign_mv_single`** — the block's `Mv`: `GLOBALMV` takes `GlobalMvs[0]`, else the predictor is
  `RefStackMv[pos][0]` (pos = 0 for NEARESTMV, `RefMvIdx` for NEARMV, `RefMvIdx`-or-0-if-`NumMvFound≤1`
  for NEWMV), and NEWMV adds the `read_mv` (0.7.66) difference — so `find_mv_stack` (0.7.65) and
  `read_mv` (0.7.66) compose into a decoded inter MV;
- the paired `av1_write_inter_mode` / `av1_write_drl_idx` encoders.

Verified by 266 assertions (74 new): a CDF-structure check against §10, plus a full **compose
round-trip** — build an `Av1MvCtx` carrying the contexts + a candidate stack + `GlobalMvs`, encode
(mode + DRL + the NEWMV difference), decode (mode → DRL → assign_mv), and assert YMode / RefMvIdx /
Mv — across all four modes, the DRL index over `NumMvFound`/`RefMvIdx` combinations (both the DRL-break
and DRL-advance branches at each idx), the single-candidate `pos = 0` path, and adaptive CDFs. A
**4-slice adversarial spec review** (read_inter_mode + CDFs / read_drl_idx / assign_mv + safety / tests
+ libaom-dav1d cross-check, each finding adversarially verified) returned **no findings** — because a
self-round-trip cannot catch a *shared* encode/decode bug, reviewers per-value-diffed the four CDF
families against §10, verified the decode against the 5.11.32 pseudocode independently, hand-traced the
DRL encoder-inverse pairs, and confirmed the `assign_mv` `pos` never OOBs (`RefMvIdx < NumMvFound`, and
`find_mv_stack` pads slots 0/1 with `GlobalMvs`). **21,720 suite assertions + 1,140 fuzz assertions,
all green; `make lint` + `make fmt-check` green.**

### Added
- **`src/av1_intermode.cyr`** (extended): the `New_Mv` / `Zero_Mv` / `Ref_Mv` / `Drl_Mode` CDF family
  (`av1_imcdf_*`); `av1_read_inter_mode` / `av1_read_drl_idx` / `av1_assign_mv_single` (5.11.32) +
  `av1_write_inter_mode` / `av1_write_drl_idx`.
- **`tests/av1_intermode.tcyr`** (extended): `test_imcdf_structure`, `test_inter_mode_rt`,
  `test_drl_idx_rt`, `test_drl_single_candidate`, `test_inter_mode_adaptive` — 266 assertions total.

### Scope / deferred
- SINGLE prediction only. COMPOUND prediction (`compound_mode` + `get_mode` + the two-list `assign_mv`),
  `use_intrabc` (intra block copy), and the `skip_mode` / segment-forced YMode branches are the caller's
  concern / later bites, as are `read_ref_frames` (which sets `RefFrame` / `isCompound`), motion mode,
  interp filter, and compound type (roadmap.md).

## [0.7.66] - 2026-07-13

**Inter prediction — the MV component decode (spec 5.11.32), the first inter mode-info bite.** The
bitstream-read layer for inter blocks begins: `src/av1_intermode.cyr` decodes a motion-vector
*difference* from the entropy stream and adds it to the predicted MV (`PredMv`, from `find_mv_stack`)
to form the block's `Mv`. The leaf-first entry:

- **the MV CDF family** — the nine motion-vector CDF tables (`mv_joint` / `mv_sign` / `mv_class` /
  `mv_class0_bit` / `mv_class0_fr` / `mv_class0_hp` / `mv_fr` / `mv_hp` / `mv_bit`), transcribed
  per-value from the spec §10 defaults into a 286-entry mutable `[MvCtx][comp]` runtime context
  (`av1_mvcdf_new` / `av1_mvcdf_blob` + accessors), with the exact CDF-selection dimensions from the §9
  parsing process;
- **`av1_read_mv`** / **`av1_read_mv_component`** (5.11.32) — decode `mv_joint` (which components are
  non-zero), then for each non-zero component a `mv_sign` + `mv_class` + magnitude split (class 0: a
  bit/fr/hp triple; class > 0: `mv_class` offset bits + fr/hp), honouring the `force_integer_mv`
  (fr = 3) and `!allow_high_precision_mv` (hp = 1) defaults, and add the result to `PredMv`;
- **`av1_write_mv`** / **`av1_write_mv_component`** — the paired encoder (the inverse decomposition:
  the `mv_class` from the magnitude's bit-length, then the bit/fr/hp fields) for round-trip testing,
  with a defensive `mv_class ≤ MV_CLASSES-1` clamp (a no-op for every representable difference — the
  decoder caps `|diff|` at 16384 — that hardens the encoder against an out-of-range future caller).

Verified by 192 assertions: a CDF-structure check against the §10 values, plus **round-trip through the
real symbol coder** (encode a difference → decode → equal) across every magnitude class, every
`mv_class` boundary (16/17/32/33/64/65/…), both precision modes, both CDF-adaptation modes, the intrabc
context, and the `PredMv` add. A **4-slice adversarial spec review** (CDF tables + layout / decode
fidelity / encoder-inverse / tests + libaom-dav1d cross-check + safety, each finding adversarially
verified) returned **no findings** — reviewers per-value-diffed all nine CDF families against §10,
proved the blob layout tiles `[0, 286)` with no overlap or OOB, and checked the decode against the
5.11.32 magnitude formula *independently of the round-trip* (a self-round-trip cannot catch a shared
formula bug). The one refuted finding — a latent encoder OOB for the unreachable `|diff| ≥ 16385` — was
hardened with the clamp above. **21,646 suite assertions + 1,140 fuzz assertions, all green; `make
lint` + `make fmt-check` green.**

### Added
- **`src/av1_intermode.cyr`** (new module, wired after `av1_mv.cyr`): the MV CDF family + `av1_read_mv`
  / `av1_read_mv_component` (5.11.32) + `av1_write_mv` / `av1_write_mv_component`.
- **`tests/av1_intermode.tcyr`**: `test_mvcdf_structure`, `test_mv_roundtrip_full` / `_classes` /
  `_precision`, `test_mv_predmv_add`, `test_mv_intrabc_ctx` — 192 assertions.

### Scope / deferred
- Only the MV component decode + its CDFs. The rest of inter mode-info — `is_inter`, the reference-frame
  reads (`read_ref_frames`), the inter mode reads (`new_mv` / `zero_mv` / `ref_mv` / `drl_mode`, which
  consume the `find_mv_stack` contexts), `assign_mv`, motion mode, interp filter, and compound type —
  are later bites (roadmap.md). `use_intrabc` is passed as the `MvCtx` by the caller.

## [0.7.65] - 2026-07-13

**Inter prediction — the `find_mv_stack` driver (spec 7.10.2).** The bite that ties the MV-prediction
arc together: the process that builds an inter block's complete ordered candidate MV list plus the
entropy contexts the mode reader consults. Extends `src/av1_mv.cyr` with the full `find_mv_stack`
process (temporal scan the sole deferral):

- **`av1_find_mv_stack`** — the driver: resets the stack, runs the spatial scan sequence (row/col at
  deltas −1/−3/−5 + the top-left and top-right corner points), tracks the above/left match flags into
  `CloseMatches`/`TotalMatches`, applies the `REF_CAT_LEVEL` weight bonus to the immediate-neighbourhood
  candidates, two-region-sorts the stack (`[0, numNearest)` then `[numNearest, NumMvFound)`), fills to
  2 via `extra_search`, and derives the contexts + clamps — all in the spec's exact ordered-step
  sequence (including the subtle `FoundMatch` reset points);
- **`av1_mv_extra_search`** + **`av1_add_extra_mv_candidate`** + **`av1_mv_store_combined`**
  (7.10.2.11/12) — the fill-to-2: the two-pass partial-match search of the row above / column left, the
  single-prediction sign-bias-adjusted dedup/append (weight 2, no lowering) + the global-motion fill
  (positions filled *without* incrementing `NumMvFound`, per the spec note), and the compound
  `RefIdMvs`/`RefDiffMvs`/`combinedMvs` combine machinery;
- **`av1_mv_context_and_clamping`** (7.10.2.14) — the `DrlCtxStack` (per-entry DRL context from the
  weight gap at `REF_CAT_LEVEL`), `NewMvContext`/`RefMvContext` (from `CloseMatches`/`TotalMatches`/
  `numNew`), `ZeroMvContext` (0 — temporal deferred), and the MV clamp;
- **`av1_clamp_mv_row`/`_col`** (spec 6) — clamp an MV so the referenced block stays within `MV_BORDER
  + block·8` of the frame edge;
- the extended `Av1MvCtx` (sign-bias pointer + the driver outputs + the extra-search scratch) with the
  `av1_mvctx_set_signbias` / output accessors (`_close_matches` / `_total_matches` / `_newmv_context` /
  `_refmv_context` / `_zero_context` / `_drl_context`).

Verified by 255 assertions (60 new) with known answers **independently computed by a spec-literal Python
port** (`scratchpad/mvdriver_ref.py`, no shared code): the above+left two-candidate case (weight bonus,
`NewMvContext`), the empty→global-fill and one→global-fill cases (the fills not counted toward
`NumMvFound`), the positive and negative MV clamps, `DrlCtxStack` `z=1` and `z=2` branches, all three
context branches, the compound `extra_search` combine, and single-prediction sign-bias negation + the
distinct-append path. A **5-slice adversarial spec review** (driver orchestration / extra_search+add_
extra / context+clamp / record-layout+OOB+hang safety / tests+libaom-dav1d cross-check, each finding
adversarially verified) returned **no findings** — reviewers traced the exact scan/`FoundMatch`
sequence, verified the extended-context offsets never overlap or OOB, and confirmed the sign-bias
negation, the global-fill-not-counted rule, and the clamp arithmetic against the spec. The four refuted
findings were coverage suggestions, all folded into the suite (the `z=2` DrlCtx, sign-bias negation,
negative clamp, and distinct-append cases). **21,454 suite assertions + 1,140 fuzz assertions, all
green; `make lint` + `make fmt-check` green.**

### Added
- **`src/av1_mv.cyr`** (extended): `av1_find_mv_stack` (7.10.2); `av1_mv_extra_search` /
  `av1_add_extra_mv_candidate` / `av1_mv_store_combined` (7.10.2.11/12); `av1_mv_context_and_clamping`
  (7.10.2.14); `av1_clamp_mv_row` / `_col` (spec 6); the extended `Av1MvCtx` + `av1_mvctx_set_signbias`
  / `_signbias` / `_set_use_ref_frame_mvs` + the output accessors.
- **`tests/av1_mv.tcyr`** (extended): `test_driver_*` D1–D10 (above/left, global fills, clamp ±, DrlCtx
  z=1/z=2, context branches, compound combine, sign-bias) — 255 assertions total.

### Scope / deferred
- The full `find_mv_stack` EXCEPT the **temporal scan** (7.10.2.5, step 11 `if use_ref_frame_mvs:
  temporal_scan`) — it needs the DPB's saved motion field (deferred with the DPB). The driver skips it
  and leaves `ZeroMvContext` at 0, which is correct for `use_ref_frame_mvs == 0`. The caller pre-sets
  `GlobalMvs` (`av1_setup_global_mv`); the MI grid is populated by inter mode-info (the next bite).

## [0.7.64] - 2026-07-13

**Inter prediction — the spatial neighbour scans (spec 7.10.2.2/3/4 + 7.10.2.7).** The third bite of
the MV-prediction arc, and the largest: the traversal that finds matching-reference neighbours (the
row above, the column to the left, the top-left/top-right corners) and feeds their motion vectors into
the candidate stack. Extends `src/av1_mv.cyr` with:

- the **per-4×4 MI grid** `Av1MiRec` — a cell holding `avail` (decoded-this-frame) / `is_inter` /
  `MiSize` / `YMode` / `RefFrames[2]` / `Mvs[2]`, frame-addressed, with `av1_mv_grid_new` / `_cell` /
  `_set`; populated by inter mode-info (a later bite) — here it's caller/test-built;
- the **scan context** `Av1MvCtx` bundling the grid + frame stride + tile bounds + current block
  (`MiRow`/`MiCol`/`MiSize`) + the block's `RefFrame[0..1]` + `GlobalMvs[0..1]` / `GmType` + the
  precision flags + `FoundMatch` + the candidate stack, with grouped setters, `av1_mvctx_is_inside`,
  and the `FoundMatch` accessors;
- **`av1_mv_scan_row`** / **`av1_mv_scan_col`** (7.10.2.2/3) — the neighbour traversal: the `end4`
  bound (`Min(Min(bw4, MiCols−MiCol), 16)`), the `deltaRow`/`deltaCol` parity adjustment for far rows/
  columns, the `len`-stepping (a wide neighbour is examined once, advancing by its covered extent),
  `useStep16` for ≥64-sample blocks, `weight = len·2`, and the `is_inside` tile-edge break;
- **`av1_mv_scan_point`** (7.10.2.4) — a single corner probe (weight 4) gated on `is_inside` AND the
  cell's `avail` (the top-right corner may be inside the tile but not yet decoded, so its stored MI
  would be stale);
- **`av1_add_ref_mv_candidate`** (7.10.2.7) + the **search-stack selection preambles**
  (`av1_mv_search_stack` / `av1_mv_compound_search_stack`, 7.10.2.8/9) — the `is_inter` gate, the
  single (each candidate list vs `RefFrame[0]`) / compound (both refs) dispatch, and the `GLOBALMV` /
  `GLOBAL_GLOBALMV` global-motion substitution (a `>TRANSLATION` model on a large block substitutes
  `GlobalMvs`) — then delegating the dedup/append/`NewMvCount` to the reviewed `av1_mv_stack_add`.

Verified by 195 assertions (62 new) with known answers **independently computed by a spec-literal
Python port** (`scratchpad/mvscan_ref.py`, no shared code): the basic scan, different-reference
rejection, `scan_row`/`scan_col` len-stepping, the `is_inside` tile-edge break, the `scan_point`
`avail` gate, the `GLOBALMV` substitution, `NewMvCount`, compound, both-lists-match, the `deltaRow`=-3
parity adjustment (even and odd `MiRow`/`MiCol`), the `scan_col` transpose parity, top-left
`scan_point`, `useStep16`, and the compound `GLOBAL_GLOBALMV` per-list substitution. A **4-slice
adversarial spec review** (scan_row/col geometry / scan_point+add_ref+selection / record-layout+OOB+
hang safety / tests+libaom-dav1d cross-check, each finding adversarially verified) returned **no
findings** — reviewers hand-traced the parity math, proved the `is_inside` gate before every grid read
prevents OOB (and that `len ≥ 1` prevents an infinite loop), and confirmed the single-dispatch checks
`RefFrame[0]` against BOTH neighbour lists (not the `REF1==REF1` bug). The four refuted findings were
coverage suggestions — the three parity/compound cases above were folded into the suite, and the
tile⊆grid caller invariant (the load-bearing OOB precondition) is now documented at
`av1_mvctx_set_tile`. **21,394 suite assertions + 1,140 fuzz assertions, all green; `make lint` +
`make fmt-check` green.**

### Added
- **`src/av1_mv.cyr`** (extended): `Av1MiRec` grid (`av1_mv_grid_new` / `_cell` / `_set`); `Av1MvCtx`
  (`av1_mvctx_new` + setters + `_is_inside` / `_cell` / `_found_match` / `_clear_found_match`);
  `av1_mv_search_stack`, `av1_mv_compound_search_stack`, `av1_add_ref_mv_candidate`, `av1_mv_scan_row`,
  `av1_mv_scan_col`, `av1_mv_scan_point`.
- **`tests/av1_mv.tcyr`** (extended): `test_mvctx_basics` + 16 scan scenarios (S1–S16) — 195 assertions.

### Scope / deferred
- The SPATIAL scans + selection + the grid/context. The MI grid is populated by inter mode-info
  (later). The TEMPORAL scan (7.10.2.5/6, needs the DPB's deferred saved MVs), the extra search
  (7.10.2.11), the context/clamping (7.10.2.14), and the `find_mv_stack` DRIVER (the scan ordering,
  the `REF_CAT_LEVEL` bonus, the foundAbove/Left tracking, the sorts) — plus the NewMv/RefMv/Zero/DRL
  entropy contexts — are the next bites (roadmap.md).

## [0.7.63] - 2026-07-13

**Inter prediction — the MV candidate stack (spec 7.10.2).** The second bite of the MV-prediction
arc: the ordered list of candidate MVs that `find_mv_stack` builds for an inter block, plus the two
operations that manage it. Extends `src/av1_mv.cyr` with:

- the **candidate-stack record** `Av1MvStack` — `RefStackMv[8][2][2]` (idx × list × row/col) +
  `WeightStack[8]` + `NumMvFound` / `NewMvCount`, with `av1_mv_stack_new` / `_reset` / `_num` /
  `_newmv_count` / `_weight` / `_row` / `_col`;
- **`av1_mv_stack_add`** — the dedup-or-append core shared by the search-stack (7.10.2.8, single) and
  compound search-stack (7.10.2.9) processes: it lowers the caller-selected candidate to the frame's
  MV precision, then either adds `weight` to a matching stack entry (single prediction matches list 0;
  compound requires BOTH lists) or appends it (capped at `MAX_REF_MV_STACK_SIZE` = 8; a full stack
  drops a new candidate but a match still accumulates weight), and increments `NewMvCount` per
  `has_newmv(cand_mode)` independent of the dedup outcome;
- **`av1_mv_stack_sort`** + `av1_mv_stack_swap` — the sorting process (7.10.2.13): a **stable**
  descending bubble sort by weight (the strict `<` keeps equal-weighted candidates in insertion
  order) with the `newEnd` early-out, over a caller-given sub-range so `find_mv_stack` can order the
  near and far halves separately;
- **`av1_has_newmv`** — the six NEWMV-carrying inter modes (`NEWMV`, `NEW_NEWMV`, `NEAR_NEWMV`,
  `NEW_NEARMV`, `NEAREST_NEWMV`, `NEW_NEARESTMV`);
- and a refactor extracting **`av1_lower_mv_comp`** (one MV component through 7.10.2.10) as the single
  source of truth, so the stack-add lowers raw components without allocating a temporary MV; the
  whole-MV `av1_lower_mv_precision` now delegates to it (behaviour-preserving, covered by the 0.7.62
  tests).

Verified by 133 assertions (79 new): single + compound dedup (incl. the both-lists-must-match
compound case), weight accumulation, `NewMvCount` incrementing even on a dedup, the full-stack drop,
`has_newmv` over all 12 inter modes, a stable descending sort whose equal-weight ordering is
hand-traced against the spec bubble sort, a sub-range sort leaving outside entries untouched, a
compound sort exercising the both-lists swap, and a dedup-after-lowering case (distinct raw
candidates that collapse to the same lowered MV). A **4-slice adversarial spec review** (add /
sort+swap / has_newmv+refactor+layout / tests+libaom-dav1d cross-check, each finding adversarially
verified) returned **no findings** — reviewers hand-traced the bubble sort for stability, verified the
`RefStackMv` flattening (`idx*4 + list*2 + comp`) never goes OOB, and confirmed the `lower_mv_comp`
refactor reproduces 7.10.2.10 component-for-component. The two refuted findings were coverage
suggestions, both folded into the suite (the compound-sort and dedup-after-lowering cases above).
**21,332 suite assertions + 1,140 fuzz assertions, all green; `make lint` + `make fmt-check` green.**

### Added
- **`src/av1_mv.cyr`** (extended): `Av1MvStack` + `av1_mv_stack_new` / `_reset` / `_num` /
  `_newmv_count` / `_weight` / `_row` / `_col`; `av1_mv_stack_add` (search stack 7.10.2.8/9);
  `av1_mv_stack_sort` + `av1_mv_stack_swap` (sorting 7.10.2.13); `av1_has_newmv`; `av1_lower_mv_comp`.
- **`tests/av1_mv.tcyr`** (extended): `test_has_newmv`, `test_stack_add_single`, `test_stack_full`,
  `test_stack_add_compound`, `test_stack_sort`, `test_stack_sort_subrange`, `test_stack_sort_compound`,
  `test_stack_dedup_after_lowering`, `test_stack_reset` — 133 assertions total.

### Scope / deferred
- Only the STACK MECHANICS. The neighbour scans (`scan_row` / `scan_col` / `scan_point` / temporal)
  that FEED candidates into the stack read the per-block MI grid (`RefFrames` / `Mvs` / `YModes` /
  `MiSizes`) that inter mode-info produces — not yet built — as does the caller-side global-MV
  substitution; the `find_mv_stack` driver, the `REF_CAT_LEVEL` bonus application, and the
  NewMv/RefMv/Zero/DRL entropy contexts are later bites (roadmap.md).

## [0.7.62] - 2026-07-13

**Inter prediction — the MV-prediction foundation (spec 7.10.2).** Motion-vector prediction
(`find_mv_stack`) is one of the largest AV1 subsystems; this is its **leaf-first first bite** — the
self-contained pieces the rest of the process composes. `src/av1_mv.cyr` adds:

- the **motion-vector representation** `Av1Mv` — a `(row, col)` pair in 1/8-luma-sample units
  (`mv[0]` = row, `mv[1]` = col, matching the spec's `mv[]` convention) with
  `av1_mv_new` / `av1_mv_row` / `av1_mv_col` / `av1_mv_set`;
- **`av1_lower_mv_precision`** (spec 7.10.2.10) — drops an MV to the frame's allowed precision:
  a no-op under `allow_high_precision_mv`, else clears the 1/8-pel bit toward zero, or snaps to whole
  luma samples under `force_integer_mv`;
- **`av1_setup_global_mv`** (spec 7.10.2.1) — the **global-motion MV candidate**: projects the
  block's central luma sample through the reference's warp model (`gm_type` + `gm_params`, already
  parsed into the frame header by `av1_global_motion_params`) and lowers it to the frame's precision.
  This is the `GLOBALMV` predictor and the default candidate `find_mv_stack` falls back to. The
  translation model shifts the stored translation from 1/2^16 warp precision to 1/8-pel (arithmetic
  `>>>`, since `gm_params` may be negative); the rotzoom/affine models project through the 2×3 affine
  matrix and round with `Round2Signed` (the symmetric variant, reusing `av1_round2_signed` from
  `av1_intra.cyr` — not the floor-only `av1_round2`).

Verified by 54 assertions with known answers **independently computed by a spec-literal Python port**
(`scratchpad/mv_ref.py`) that shares no code with the implementation — covering all model types
(identity / translation / rotzoom / affine), high/low precision, `force_integer_mv`, negative
projections, non-zero block origins, a full rotzoom exercising every `yc` term + the `mi_row→y`
wiring, and a negative projection that distinguishes `Round2Signed` from `Round2`. A **4-slice
adversarial spec review** (guards+translation / rotzoom-affine projection+overflow / lower_mv_precision
+ composition / tests+libaom-dav1d cross-check, each finding adversarially verified) returned **no
findings** — reviewers hand-recomputed the projection cases from the spec pseudocode and confirmed the
matrix indices, shift kinds (arithmetic vs logical), rounding kind (`Round2Signed`), and i64 overflow
bounds (worst-case products ≈ 2^41, far below 2^63). The two refuted findings were coverage
suggestions, both folded into the suite as the two extra cases above. **21,253 suite assertions +
1,140 fuzz assertions, all green; `make lint` + `make fmt-check` green.**

### Added
- **`src/av1_mv.cyr`**: `Av1Mv` (row, col) + `av1_mv_new` / `av1_mv_row` / `av1_mv_col` / `av1_mv_set`;
  `av1_lower_mv_precision` (7.10.2.10); `av1_setup_global_mv` (7.10.2.1).
- **`tests/av1_mv.tcyr`**: `test_mv_repr`, `test_round2_signed` (the Round2Signed contract av1_mv
  relies on), `test_lower_mv_precision`, `test_setup_global_mv` — 54 assertions.

### Scope / deferred
- Only these leaves. The MV candidate STACK — spatial scan (`scan_row` / `scan_col` /
  `add_ref_mv_candidate`), temporal scan (needs the DPB's saved MVs), `extra_search`, the sorting
  process, and the `NewMv` / `RefMv` / `Zero` / DRL contexts — plus the `find_mv_stack` driver, are
  the next bites of the MV-prediction arc (roadmap.md), building on the storage + global candidate this
  bite establishes.

## [0.7.61] - 2026-07-13

**Inter prediction — the reference-frame buffer / DPB (spec 7.20 + 7.21).** The decoded-picture
buffer: the ring of decoded reference frames that inter prediction reads from. `src/av1_dpb.cyr`
adds the eight-slot pixel `FrameStore` (`Av1Dpb`) and the two processes that drive it — the
**reference frame update process** (7.20) saves a decoded frame's pixels into every slot flagged by
`refresh_frame_flags`, and the **reference frame loading process** (7.21) serves a
`show_existing_frame` back from a slot. The per-slot *metadata* (dimensions, order hints, saved
global-motion) already lived in `Av1RefState` (`av1_frame_update_refs`); `av1_dpb_update` now runs
both halves so one call is the whole 7.20 process. Two things this unlocks:

- **The inter hook** — `av1_dpb_ref_frame(dpb, fh, refFrame)` maps a frame's `LAST_FRAME`..
  `ALTREF_FRAME` reference through `ref_frame_idx` to the stored `DrFrame` the MC driver
  (`av1_mc_pred_block`, 0.7.60) reads. This is the seam that will connect the DPB to motion
  compensation once inter mode-info lands.
- **Multi-frame decode** — `av1_decode_stream` walks a whole OBU stream, decodes **every** coded
  frame into the DPB (running the reference frame update after each so a later frame can reference
  an earlier one), and serves `show_existing_frame` from the ring — returning the last shown frame.
  `av1_decode_obus` stays the single-frame entry point (unchanged); this is its multi-frame
  superset.

Verified by 82 assertions: unit tests pin the exact slot semantics (the `(refresh_frame_flags >> i)
& 1` bit-to-slot mapping, the `frame_to_show_map_idx` load, the `refFrame - LAST_FRAME` ref
mapping — each with distinct dummy frames so an off-by-one is caught) plus a real end-to-end
multi-keyframe OBU stream through `av1_decode_stream`. A **5-slice adversarial spec review**
(reference-frame update 7.20 / loading 7.21 / inter-hook + walk / hostile-input safety /
tests + dav1d-libaom cross-check, each finding adversarially verified) returned **no findings** —
the reviewers confirmed the aliasing store is behaviorally identical to the spec's per-slot pixel
copy (every decode yields a fresh, never-mutated frame), the load/update ordering matches the
decode-frame-wrapup sequence, and the tests genuinely pin the mappings. **21,199 suite assertions +
1,140 fuzz assertions, all green; `make lint` + `make fmt-check` green.**

### Added
- **`src/av1_dpb.cyr`**: `Av1Dpb` (the 8-slot decoded-frame `FrameStore`) + `av1_dpb_new` /
  `av1_dpb_frame` / `av1_dpb_valid` / `av1_dpb_count`; `av1_dpb_store` (7.20 pixel half) +
  `av1_dpb_update` (full 7.20: pixel store + `av1_frame_update_refs`); `av1_dpb_load` (7.21);
  `av1_dpb_ref_frame` (the inter/MC hook); `av1_decode_stream` (the multi-frame OBU-stream driver).
- **`tests/av1_dpb.tcyr`**: `test_dpb_store_slots` / `_store_all` / `_store_reject` (7.20),
  `test_dpb_load` (7.21), `test_dpb_ref_frame` / `_accessors`, `test_dpb_update_full` (pixel +
  metadata), `test_stream_single` / `_two_frames` / `_reject` (`av1_decode_stream`) — 82 assertions.

### Scope / deferred
- Only the **pixel** `FrameStore` ring is new. The saved-CDF / saved-MV / saved-segment-id outputs
  of 7.20 and the full 7.21 metadata reload are inter-only decode state (later bites). Because the
  tile decoder is intra-only so far, `av1_decode_stream` fully decodes keyframe / intra-only streams
  and serves `show_existing`; a genuine inter frame's tile decode awaits the inter mode-info bite
  (roadmap.md).

## [0.7.60] - 2026-07-13

**Inter prediction — the MC driver (`av1_mc_pred_block`, spec 7.11.3.1 steps 10 + 13).**
The piece that composes the two reference-tested leaf kernels into block prediction: it
takes a motion vector and a same-sized reference frame, splits the MV into an integer
top-left + a 1/16-pel phase per axis, gathers the (possibly out-of-frame, edge-clamped)
padded reference block via `av1_mc_emu_edge`, filters it with `av1_mc_put_8tap`, and writes
the `Clip1`'d result into the destination `DrFrame`. Scoped to the base inter case — single
reference, translation-only (no warp), non-compound, **unscaled** (reference plane dims ==
current plane dims); BILINEAR, scaled references, compound, OBMC, and warp are cleanly
rejected as later bites. **Geometry**: for equal frame dimensions the full motion-vector
scaling process (spec 7.11.3.3) collapses exactly to `pos16 = (x << 4) + ((2*mv) >>> sub)`,
`integer = pos16 >>> 4`, `phase = pos16 & 15` (`xScale == 1<<14`, `stepX == 1024`, the
`halfSample`/`off` rounding terms cancel — proven against a literal port of the full
process, both MV signs). **Gather**: the driver copies the exact `Clip3`-clamped read
window and lets `emu_edge` replicate it outward, which is pixel-identical to the spec's
per-sample plane clamp. Verified against a **spec-literal Python reference**
(`scratchpad/mc_driver_ref.py`) whose `Subpel_Filters` table is parsed straight out of the
AV1-spec markdown, so it shares no table or kernel code with `src/av1_mc.cyr`: 18
known-answer cases (integer/H-only/V-only/H+V paths, each overhang direction, wholly-out MVs,
chroma with subsampled MV, the `w≤4`/`h≤4` 4-tap remap, mixed filter sets, extreme MVs both
signs, 8/10/12-bit) plus a full chroma-block pixel dump, write-confinement, and
border-independence checks. A **5-slice adversarial spec review** (geometry / gather /
filters / safety / tests-cross-impl, each with independent adversarial verification of every
finding) returned **3 confirmed findings, all fixed in this cut**:

- **[critical]** the block-inside-plane guard formed `x + w` as an i64 before comparing to
  the plane width, which **wraps for a hostile `x` near i64-max** and slips an unclamped
  coordinate into the write-back (`dr_frame_set` has no bounds check → OOB write). Fixed to
  the overflow-safe subtraction form `x > pw - w` (`pw - w`, `ph - h` cannot overflow given
  the validated `w,h ∈ [1,128]`, `pw,ph ∈ [1,16384]`), regression-tested with the i64-max
  `x`/`y` attack inputs.
- **[major]** the unscaled-reference gate compared only the *per-plane* dims, not the luma
  frame dims — subsampled chroma planes collide across different luma sizes (luma 24×18 and
  23×17 both give 12×9 chroma at 4:2:0), so a **scaled reference was silently accepted and
  emitted wrong chroma pixels**. Fixed to also require equal luma `FrameWidth`/`FrameHeight`
  (spec 7.11.3.3 derives scaledness from luma), regression-tested with the collision pair on
  both the luma and chroma plane.
- **[minor]** `av1_mc_put_8tap`'s 2-pass (H+V) path allocated its intermediate buffer per
  call from the arena allocator (never freed), so per-block invocation grew memory unbounded
  across a frame — the very pattern the driver's own persistent scratch exists to avoid.
  Fixed with a lazily-built persistent module-global mid scratch
  (`av1_mc_mid_scratch`, sized for the largest block once).

Two refuted findings were test-coverage suggestions (2×2 chroma blocks; a handful of
untested 12-bit 1D / SMOOTH-`w≤4` branches — all independently verified numerically correct
by the reviewers' own sweeps). **21,117 suite assertions + 1,140 fuzz assertions, all green;
`make lint` + `make fmt-check` green.**

### Added
- **`src/av1_mc.cyr`**: `av1_mc_pred_block(dst, ref, plane, x, y, w, h, mv_row, mv_col,
  filt_x, filt_y)` — the single-reference unscaled translation-only MC driver; `av1_mc_pos16`
  (the 7.11.3.3 unscaled 1/16-pel split); `av1_mc_drv_scratch` / `av1_mc_mid_scratch`
  (persistent gather/rect/out/mid scratch blobs) + the `Av1McDrv` size enum.
- **`tests/av1_mc_driver.tcyr`**: `test_mc_pos16` (geometry split incl. negative-MV floor +
  chroma halving), `test_mc_pred_known_answers` (18 spec-literal cases),
  `test_mc_pred_chroma_full`, `test_mc_pred_confinement`, `test_mc_pred_border_independent`,
  `test_mc_pred_rejects` (BILINEAR / scaled-ref incl. the chroma collision / i64-overflow /
  null / range) — 157 assertions.

### Fixed
- **[critical]** `av1_mc_pred_block` i64-overflow bypass of the block-inside-plane guard →
  OOB write; now the overflow-safe subtraction form.
- **[major]** `av1_mc_pred_block` accepted a scaled reference when subsampled chroma plane
  dims collided; now gates on the luma frame dims too.
- **[minor]** `av1_mc_put_8tap` H+V per-call arena allocation → unbounded growth across a
  frame; now a persistent module-global mid scratch.

### Scope / deferred
- The single-reference, unscaled, translation-only, non-compound base case only. The
  reference-frame buffer/DPB (needs multi-frame decode), MV prediction, inter mode-info, and
  compound/OBMC/warp/scaled-reference/BILINEAR prediction are the next bites of the inter
  arc (roadmap.md).

## [0.7.59] - 2026-07-13

**Inter prediction — the frame-boundary block fetch (`emu_edge`, spec 7.11.3.2).** A
faithful port of dav1d's `emu_edge_c` (`src/mc_tmpl.c`): `av1_mc_emu_edge` fetches a
`bw×bh` reference block at a source position `(x, y)` that may lie partly or wholly
outside the frame, **clamping out-of-bounds reads to the nearest edge pixel** (the AV1
frame-boundary MC rule). It copies the visible portion, then replicates the edge pixels
outward — left/right along each visible row, then the top rows from the first (already
edge-extended) visible row and the bottom rows from the previous written row, exactly as
dav1d does. This is the padded-block fetch that will feed `av1_mc_put_8tap` when a motion
vector points near or past a frame edge. Verified against a **Python port of `emu_edge_c`**
(`scratchpad/emu_edge.py`): a fully-inside block plus the four out-of-frame cases
(top-left, bottom-right, bottom-left overhangs, and a block wholly left of the frame — a
single visible column replicated across the whole block), matched via position-weighted
checksums + spot pixels. A 2-dimension adversarial review (extension-geometry +
index/bounds-safety) returned **no findings**. **20,960 suite assertions + 1,140 fuzz
assertions, all green; `make lint` green.**

### Added
- **`src/av1_mc.cyr`**: `av1_mc_emu_edge(bw, bh, iw, ih, x, y, dst, doff, dstride, ref,
  roff, rstride)` — the frame-boundary reference-block fetch with edge clamping.
- **`tests/av1_mc_emu_edge.tcyr`**: `test_emu_edge` — 5 cases (center no-extension + the
  four out-of-frame cases) against the dav1d `emu_edge_c` reference.

### Scope / deferred
- The `emu_edge` fetch only (operates on i64 sample arrays). The MC **driver** that splits a
  motion vector into integer + sub-pel parts, calls `emu_edge` to gather the padded reference
  block, and drives `put_8tap` into the `DrFrame` is the next bite; the reference-frame buffer
  (DPB, needs multi-frame decode), MV prediction, and inter mode-info follow.

## [0.7.58] - 2026-07-12

**Inter prediction — the `put_8tap` motion-compensation kernel (spec 7.11.3.2).** A
faithful port of dav1d's `put_8tap_c` (`src/mc_tmpl.c`): `av1_mc_put_8tap` predicts a w×h
block from reference samples via the sub-pel filters, with dav1d's intermediate precision.
Four branches — **integer** (copy), **H-only**, **V-only**, and **H+V** (the 2-pass path:
horizontal filter into a `(h+7)`-row mid buffer at shift `6−ib`, then vertical at `6+ib` +
`Clip1`; `ib` = 4 for 8/10-bit, 2 for 12-bit). Filter selection matches dav1d: set =
`filter_type&3` for `w/h>4`, the `w≤4` variant sets (3/4) otherwise; phase = `mx−1`/`my−1`.
Verified against a **Python port of `put_8tap_c`** across all four branches, both
filter-selection paths (8×8 → sets 0–2, 4×4 → the `w≤4` sets), REGULAR + SHARP, at 8-bit —
matched via position-weighted checksums + spot pixels. A 2-dimension adversarial review
(shifts/precision + filter-selection/edges) found **no correctness defects** (its one nit
— no in-kernel clamp on the mx/my sub-pel index — was refuted: dav1d doesn't clamp either;
the caller masks mx/my to 0..15 by construction, and the kernel matches dav1d across the
whole valid domain). **20,945 suite assertions + 1,140 fuzz assertions, all green; `make
lint` green.**

### Added
- **`src/av1_mc.cyr`**: `av1_mc_put_8tap(dst, doff, dstride, src, soff, sstride, w, h, mx,
  my, filter_type, bit_depth)` + `av1_mc_8tap` (8-tap dot product) + `av1_mc_subpel_row`.
- **`tests/av1_mc_kernel.tcyr`**: `test_put_8tap` — 6 cases (integer, H, V, H+V, `w≤4`
  H+V, SHARP H+V) against the dav1d `put_8tap_c` reference.

### Scope / deferred
- The `put_8tap` kernel only (operates on padded i64 sample arrays). The MC **driver**
  (predict a block into the frame from a reference frame + MV, with edge extension), the
  reference-frame buffer (DPB, needs multi-frame decode), MV prediction, and inter
  mode-info are the next bites. dav1d's `prep_8tap` / scaled MC / bilinear / warp variants
  are separate later concerns.

## [0.7.57] - 2026-07-12

**Inter prediction — sub-pel interpolation filter table (spec 7.11.3.2).** First bite of
the inter arc (the last of the four AV1-decode capabilities). New module `src/av1_mc.cyr`
lands the **`Subpel_Filters` table** — dav1d's `dav1d_mc_subpel_filters` (`src/tables.c`),
6 filter sets × 15 sub-pel phases × 8 taps: `0 REGULAR · 1 SMOOTH · 2 SHARP · 3 REGULAR(w≤4)
· 4 SMOOTH(w≤4) · 5 scaled-bilinear`. Stored in dav1d's convention (every phase row sums to
**64**, not the spec's 128 — dav1d carries an extra intermediate-precision bit through its
2-pass filter, so its coefficients are the spec's halved; the `put_8tap` kernel, a later
bite, will match dav1d's shifts to keep the two in one convention). Verified three ways so
a transcription/sign slip fails the build: every one of the 90 phase rows sums to 64;
mirror symmetry `Subpel_Filters[s][p] == reverse(Subpel_Filters[s][14−p])` holds in all 6
sets; and a per-(set,phase) cubic **position-weighted checksum** against 90 goldens
transcribed **independently** from dav1d (pins tap order). A 2-dimension adversarial
review (dav1d-vs-spec convention + table values/set-order) returned **no findings**.
**20,935 suite assertions + 1,140 fuzz assertions, all green; `make lint` green.**

### Added
- **`src/av1_mc.cyr`**: `av1_subpel_filters_blob` (lazy 6×15×8 table) + `av1_subpel_filter(set,
  phase, tap)`; `enum Av1Mc` (`SUBPEL_SETS=6`, `SUBPEL_PHASES=15`, `SUBPEL_TAPS=8`).
- **`tests/av1_mc.tcyr`**: `test_subpel_invariants` (row-sums, symmetry, spot values) +
  `test_subpel_checksum` (90 position checksums vs the independent transcription).

### Scope / deferred
- The table only. The `put_8tap` 8-tap MC kernel (2-pass H/V filtering with dav1d's
  intermediate precision), the MC driver, the reference-frame buffer (DPB), MV prediction,
  and inter mode-info are the next bites — all table-free now (the dav1d `mc_tmpl.c` /
  `decode.c` references are in hand). Inter is the last of the four AV1-decode tracks;
  multi-tile, 10-bit, and superres are complete.

## [0.7.56] - 2026-07-12

**Superres decodes end-to-end — the superres track is complete (spec 7.16).** The upscale
is now wired into the in-loop pipeline: **deblock → CDEF → superres → loop restoration**.
`av1_apply_loop_filters` inserts an upscale stage after CDEF — when `use_superres` is set
it lifts the reconstruction from `FrameWidth` to `UpscaledWidth` (`av1_superres_upscale_new`
→ a fresh upscaled-width frame). Loop restoration then runs at the upscaled width (its
params already carry `UpscaledWidth`); since LR reads **both** the deblocked (`curr`) and
CDEF frames across the full upscaled width, both are upscaled (they alias when CDEF is
off). The reconstruction frame is still built + decoded at `FrameWidth` (downscaled); only
the post-CDEF output changes width. The `av1_decode_frame` / `av1_frame_dec_new`
`use_superres` reject is **lifted**. A `use_superres` keyframe now decodes to the display
width — verified end-to-end: an all-skip 128→256 (2×) keyframe decodes to a 256-wide
flat-128 frame, with and without CDEF (the separate up-CDEF path). Non-superres decode is
unchanged (`use_superres == 0` ⇒ the new stage is a no-op). A 2-dimension adversarial review (frame-lifecycle across the
superres × CDEF × LR combinations + non-superres regression) returned **no findings**.
**20,748 suite assertions + 1,140 fuzz assertions, all green; `make lint` green.**

### Added / changed
- **`src/av1_superres.cyr`**: `av1_superres_upscale_new(down, up_w, out_err)` — allocate a
  fresh `UpscaledWidth` frame and upscale `down` into it.
- **`src/av1_decode.cyr`**: `av1_apply_loop_filters` gains the superres stage between CDEF
  and LR (upscales the deblocked + CDEF frames; LR at the upscaled width). `av1_frame_dec_new`
  drops the `use_superres` reject.
- **`tests/av1_decode.tcyr`**: `test_frame_decode_superres` (replaces the old
  `_rejected` test) — a `use_superres` 128→256 keyframe decodes to a 256-wide flat-128
  frame at the correct dims + unchanged height, with and without CDEF.

### Scope / deferred
- Superres is exercised end-to-end for **all-skip** content (the encode lane's reach). A
  superres + loop-restoration end-to-end test (both frames upscaled, LR at the upscaled
  width) awaits a richer test harness; the both-upscaled LR path is covered by inspection
  + the adversarial review. This closes track 2 (superres) of the four AV1-decode
  capabilities — **inter** is the last, and its tables + `mc` reference are already in hand.

## [0.7.55] - 2026-07-12

**Superres upscaling — per-plane frame upscale (spec 7.16).** `av1_superres_upscale_frame`
horizontally upscales a whole downscaled reconstruction frame (each plane at `FrameWidth`)
into an upscaled frame (each plane at `UpscaledWidth`), one row at a time via the 0.7.52–54
kernel stack. Superres scales **only horizontally**, so plane heights are unchanged; the
per-plane widths come straight off the `DrFrame`s (chroma already carries the subsampled
`(w+subx)>>subx` widths, matching dav1d's `in_cw`/`out_cw`), and each plane gets its own
`dx`/`mx0`. Verified against a dav1d Python reference for mono (`8→16`) and a 4:2:0 frame
(luma `8→16` + chroma `4→8` — the subsampled-width path). A 2-dimension adversarial
review (plane-loop + chroma-correctness) returned **no findings**. **20,742 suite
assertions + 1,140 fuzz assertions, all green; `make lint` green.**

### Added
- **`src/av1_superres.cyr`**: `av1_superres_upscale_frame(down, up, bit_depth)` — the
  per-plane / per-row upscale loop (reads `dr_frame_plane_width/height`, allocates one
  src/dst row scratch per plane, `DR_OK` / `DR_ERR_OOM`).
- **`tests/av1_superres.tcyr`**: `test_superres_upscale_frame` — mono 8×3→16×3 and a
  4:2:0 3-plane 8×4→16×4 (chroma 4×2→8×2), each row checked against the dav1d reference.

### Scope / deferred
- The standalone frame-upscale function. The **pipeline wiring** — inserting it between
  CDEF and loop restoration (deblock → CDEF → **superres** → LR), running LR at the
  upscaled width, and lifting the `av1_decode_frame` `use_superres` reject — is the next
  bite, at which point a superres keyframe decodes end-to-end.

## [0.7.54] - 2026-07-12

**Superres upscaling — geometry (spec 7.16), reference-confirmed against dav1d.** The
horizontal upscale is now correct end-to-end. `av1_superres_step(down_w, up_w)` and
`av1_superres_x0(down_w, up_w, step)` compute the per-plane subpel step `dx` and initial
fractional offset `mx0` that `av1_superres_upscale_row` consumes — exact ports of dav1d's
`scale_fac` + `get_upscale_x0` (`src/decode.c`, user-provided): `dx = ((down_w<<14) +
up_w/2)/up_w`; `err = up_w·dx − (down_w<<14)`; `x0 = (−((up_w−down_w)<<13) + up_w/2)/up_w
+ 128 − err/2`, then `& 0x3fff`. All integer divisions are C-truncating (toward zero,
matching dav1d, incl. the negative numerator in `x0`), and the final mask keeps the low
14 bits when `x0` is negative pre-mask. Verified by 12 `step`/`x0` known-answers (all
matching a Python port of dav1d — e.g. `8→16` → `8192`/`12417`, `8→12` → `10923`/`13780`)
plus two **end-to-end** upscales (geometry → row driver → the reference upscaled row).
A 2-dimension adversarial review (formula-vs-dav1d + edge/overflow) returned **no
findings**. **20,737 suite assertions + 1,140 fuzz assertions, all green; `make lint`
green.**

### Added
- **`src/av1_superres.cyr`**: `av1_superres_step` / `av1_superres_x0` (spec 7.16 / dav1d
  `scale_fac` + `get_upscale_x0`).
- **`tests/av1_superres.tcyr`**: `test_superres_geometry` — 12 `step`/`x0` known-answers
  + two full geometry→driver upscales (`8→16`, `8→12`) against the dav1d reference.

### Scope / deferred
- Geometry only (per-plane widths supplied by the caller — luma uses `FrameWidth →
  UpscaledWidth`, chroma the subsampled widths). The per-plane loop (upscale every row of
  every plane into a new frame) + pipeline wiring (CDEF → superres → LR, LR geometry under
  the upscaled width, and lifting the `av1_decode_frame` `use_superres` reject) are the
  next bites — at which point superres decodes end-to-end.

## [0.7.53] - 2026-07-12

**Superres upscaling — row driver (spec 7.16), reference-confirmed against dav1d.**
`av1_superres_upscale_row(src, src_w, dst, dst_w, dx, mx0, bit_depth)` upscales one plane
row: a single subpel accumulator starts at `mx0 − (1<<14)` (dav1d's `src_x = −1`) and
steps by `dx`, one `av1_superres_filter_pixel` per output. This is the combined-
accumulator form of dav1d's `resize_c` (`src/mc_tmpl.c`), which keeps `src_x` (integer)
and `mx` (fractional, masked to 14 bits) separate; a Python port
(`scratchpad/resize_ref.py`) proves the two forms **identical** and the cyrius output
matches dav1d's `resize_c` byte-for-byte on 2× / 1.5× / flat test vectors. Building the
driver surfaced a latent kernel fix: `av1_superres_filter_pixel`'s integer base now uses
an **arithmetic** shift (`>>>`), since the accumulator is negative at a row's start
(logical `>>` would send the left-edge base to a huge positive index instead of `−1`) —
the positive-only kernel known-answers are unchanged. A 2-dimension adversarial review
(combined-vs-split accumulator equivalence + edge/shift audit) returned **no findings**.
**20,723 suite assertions + 1,140 fuzz assertions, all green; `make lint` green.**

### Added
- **`src/av1_superres.cyr`**: `av1_superres_upscale_row` (the spec-7.16 / dav1d
  `resize_c` row loop). `av1_superres_filter_pixel` base shift `>>` → `>>>` (arithmetic).
- **`tests/av1_superres.tcyr`**: `test_superres_upscale_row` — 2× (`dx=8192`, `mx0=8321`),
  1.5× (`dx=10923`, `mx0=5461`), and flat, each checked against the dav1d `resize_c`
  reference output (goldens from the Python port).

### Scope / deferred
- The row driver takes `dx`/`mx0` as inputs. Their per-plane **geometry** (dav1d
  `get_upscale_x0` / spec 7.16 — `dx = ((src_w<<14)+dst_w/2)/dst_w`, `mx0` from the
  initial-offset equation) is the next bite, then the per-plane loop + pipeline wiring
  (CDEF → superres → LR, lifting the `use_superres` reject).

## [0.7.52] - 2026-07-12

**Superres upscaling — kernel layer (spec 7.16).** The first of the two remaining
table-dependent decode tracks. Superres codes a frame at a reduced width and upscales
it horizontally back to `UpscaledWidth` on decode (a normative 8-tap poly-phase filter,
run between CDEF and loop restoration). New module `src/av1_superres.cyr` lands the
kernel layer: the **`Upscale_Filter[64][8]` table** + the **per-output-pixel filter
application**. The table is sourced from dav1d's `dav1d_resize_filter` (`src/tables.c`)
— which stores it **negated** (rows sum to −128) — with every value negated back to the
spec's positive-centre form (rows sum to +128, the `Round2(sum, 7)` normalization). It
is verified **structurally** so a transcription/sign slip fails the build, not a decode:
every one of the 64 phase rows sums to 128, phase 0 is the integer-pel identity
`[0,0,0,128,0,0,0,0]`, and mirror symmetry holds (`Upscale_Filter[p]` reversed ==
`Upscale_Filter[64−p]`). `av1_superres_filter_pixel` applies one phase (spec 7.16:
phase = `subpel>>8 & 63`, integer base = `subpel>>14`, taps read `base+k−3` clamped to
the plane edge, `Round2(sum, 7)` + `Clip1`). A 2-dimension adversarial review (kernel-geometry +
table/test-adequacy) confirmed the kernel spec-correct; it caught **one real
test-coverage gap** — the row-sum + symmetry invariants don't pin tap ORDER within a
phase (a permutation preserving the sum, and for the self-mirrored phase 32 the
palindrome, would survive) — which is now closed by a **per-phase position-weighted
cubic checksum against goldens transcribed independently from dav1d** (a second,
separate transcription; agreement verifies the cyrius table row-by-row, position-by-
position). **20,720 suite assertions + 1,140 fuzz assertions, all green; `make lint`
green.**

### Added
- **`src/av1_superres.cyr`**: `enum Av1Superres` (spec 7.16 constants —
  `SCALE_BITS=14`, `EXTRA_BITS=8`, `FILTER_TAPS=8`, `FILTER_OFFSET=3`, `FILTER_SHIFTS=64`,
  …); `av1_upscale_filter_blob` (lazy 64×8 table) + `av1_upscale_filter(idx, tap)`;
  `av1_superres_filter_pixel(src, src_w, subpel_x, bit_depth)`.
- **`tests/av1_superres.tcyr`**: table invariants (64 row-sums, integer-pel, symmetry,
  spot values) + a **per-phase position-weighted checksum** pinning tap order (goldens
  from an independent Python transcription of dav1d) + kernel known-answers (integer-pel
  identity, flat→flat, edge clamp, bit-depth clip, hand-computed fractional phase-17 = 76).

### Scope / deferred
- Kernel layer only (mirrors the CDEF/LR kernel-then-driver split). The per-plane **row
  geometry** (initial subpel position + step, spec 7.16) and the **pipeline wiring**
  (CDEF → superres → LR, and lifting the `av1_decode_frame` `use_superres` reject) are
  the next bites (roadmap.md). Sub-pel interpolation + warp filter tables for **inter**
  are now also in hand (same dav1d paste) for that track.

## [0.7.51] - 2026-07-12

**Multi-tile-group frames — the multi-tile track is complete.** A frame whose tiles
are split across **multiple `TILE_GROUP` OBUs** (each carrying a `TileNum` sub-range,
spec 5.11.1) now decodes; previously only a single group covering the whole frame was
accepted (`tg_count != num_tiles` → `DR_ERR_UNSUPPORTED`). The monolithic
`av1_decode_frame` was decomposed into a **frame-decode context** (`Av1FrameDec`) that
persists the reconstruction frame + the shared frame-sized MI grids + the LR params
across groups: `av1_frame_dec_new` begins the frame, `av1_frame_dec_group` decodes one
group's tiles into the shared grids (requiring each group to continue exactly at the
next `TileNum` — in-order, contiguous, trust-no-input), and `av1_frame_dec_finish` runs
the in-loop filters once over the whole frame when the last tile lands. `av1_decode_obus`
now accumulates standalone tile-group OBUs into one context instead of returning at the
first. `av1_decode_frame` is a thin single-group wrapper over the same context (behavior
byte-identical for the common one-group case — the whole existing suite is the
regression net). A 2-dimension adversarial review (context-lifecycle + ordering/walk)
confirmed the state machine with **no correctness defects** — all three findings
refuted, including a traced check that a stray `FRAME_HEADER` between groups can only
yield a correct frame or a clean error, never wrong pixels; its one coverage observation
(identical flat content can't distinguish a wrong-window grid write) was closed by a
direct Skips-grid probe. **20,575 suite assertions + 1,140 fuzz assertions, all green;
`make lint` green.**

### Added
- **Frame-decode context** (`src/av1_decode.cyr`): `Av1FrameDec` {frame, tile0,
  lr_params, seq, fh, num_tiles, tiles_done} + `av1_frame_dec_new` / `av1_frame_dec_group`
  / `av1_frame_dec_finish`. `av1_decode_frame` reduces to `new → group → finish`;
  `av1_decode_obus` creates the context lazily at the first `TILE_GROUP` OBU and finishes
  when a group completes the frame.
- **Tests** (`tests/av1_decode.tcyr`): `test_frame_decode_multigroup` (drives the context
  directly — two partial groups of one tile each into one shared 256×64 frame → flat-128;
  a Skips-grid probe proving group 1's tile wrote into its own absolute `[32,64)` window;
  plus the out-of-order/non-contiguous first-group reject) and `test_obus_multigroup` (a
  full TD + seq + `FRAME_HEADER` + two `TILE_GROUP` OBU stream through `av1_decode_obus`).
  New hand-built 2-tile-column headers: `frame_mk_fh_2tile` (struct) + `frame_build_seq_2tile`
  / `frame_build_fh_2tile` (bitstream; `tile_cols_log2 = 1`, traced against `av1_tile_info`).

### Scope / deferred
- Multi-tile-group is exercised for **all-skip** tiles (the encode lane's current reach);
  a non-skip end-to-end test awaits the non-skip encode lane. Groups must arrive in
  `TileNum` order (the normal bitstream order); an out-of-order/overlapping group is
  rejected `DR_ERR_UNSUPPORTED`. Multi-group split across **FRAME OBUs** (type 6, one
  embedded group each) is not a real-stream shape and stays single-group per FRAME OBU.

## [0.7.50] - 2026-07-12

**Multi-tile intra correctness — the last table-free multi-tile gaps.** Two
extent-vs-absolute defects in `av1_transform_block` that break intra decode for any
tile past column/row 0 (both latent behind the flat-content 2-tile test): the 0.7.49
scope note had flagged the first, and the adversarial review of that fix surfaced the
second in the same function.

1. **Coeff-context split.** The per-tile `AboveLevelContext` / `LeftLevelContext` (+ Dc)
   arrays are sized to the tile **extent** and cleared tile-relative (spec 5.11.2
   `clear_above/left_context`), but `av1_transform_block` indexed them with **absolute**
   frame-plane coords (`start_x >> 2`) — correct only for a single tile (`MiColStart =
   0`); a windowed tile overran the extent-sized array **and** failed the `(x4+k) <
   max_x4` neighbour bound, zeroing the context past tile column 0. Now rebased to the
   tile origin (`av1_coeff_ctx_col`/`av1_coeff_ctx_row`), landing slot 0 at the tile's
   first column/row.
2. **Intra reference-sample bound.** `av1_transform_block` passed the window **extent**
   (`MI_COLS`/`MI_ROWS`) to `av1_intra_predict`, whose availability clamp `maxX =
   MiCols*MI_SIZE-1` (spec 7.11.2) is a **frame** edge compared against the **absolute**
   `start_x`. For a windowed tile the extent clamp sits *below* the block, collapsing the
   whole above/left reference fill onto the neighbouring tile's edge column/row. Now it
   passes the **frame** MI dims (`FMI_COLS`/`FMI_ROWS`) — the spec-literal `MiCols`, and
   what the parameter meant pre-multi-tile (single tile: `FMI == MI_COLS`).

Both are byte-identical for a single tile (`MiColStart = MiRowStart = 0`, `FMI ==
extent`), so the whole existing suite is the regression net; each fix has a direct unit
test since a non-skip multi-tile end-to-end test awaits the non-skip encode lane.
**20,557 suite assertions + 1,140 fuzz assertions, all green; `make lint` green.**

### Added
- **Coeff-context rebase** (`src/av1_residual.cyr`): `av1_coeff_ctx_col(tile, start_x,
  subx)` / `av1_coeff_ctx_row(tile, start_y, suby)` = `(start_x >> 2) - (MiColStart >>
  subx)` — the absolute→tile-relative plane-4x4 index for the coeff neighbour context;
  `av1_transform_block` passes these to `av1_coeffs_decode`.
- **Intra reference bound** (`src/av1_residual.cyr`): `av1_transform_block` passes
  `FMI_COLS`/`FMI_ROWS` (frame MI dims) to `av1_intra_predict` in place of the window
  extent `MI_COLS`/`MI_ROWS`, restoring the spec-7.11.2 frame `maxX`/`maxY`.
- **Tests** (`tests/av1_residual.tcyr`): `test_coeff_ctx_tile_relative` (single tile ⇒
  identity; column-windowed `[32,64)` first→slot 0 / 8 MI in→slot 8 / last→slot 31 /
  chroma `subx=1`→slot 0; row-windowed `[16,32)` first→slot 0) and
  `test_intra_predict_multitile_ref` (a DC block at absolute `x=128` whose left column
  127 differs from its own above row 128+ — frame-mi reads 200, the old extent-mi reads
  tile 0's 100).

### Scope / deferred
- The frame-addressed `LoopfilterTxSizes` / `BlockDecoded` grids keep **absolute**
  plane coords (clamped to `MiColEnd`/`MiRowEnd`) — a deliberately different addressing
  scheme (frame-wide, shared across tiles), untouched by this change.
- The **encode** transform_block path (`av1_coeffs_encode`) is not yet wired, so it
  needs no matching rebase today; when it lands it must use the same helpers.
- A **non-skip multi-tile** end-to-end test still awaits the non-skip encode lane; both
  fixes are unit-tested directly meanwhile. Multi-tile-group frames remain
  `DR_ERR_UNSUPPORTED` (a later bite; roadmap.md).

## [0.7.49] - 2026-07-12

**Multi-tile decode — the first multi-tile frame decodes.** Completing the
0.7.47/0.7.48 foundation (frame-addressed grids + tile-window geometry),
`av1_decode_frame` now loops the tile group's tiles, decoding each into its absolute
MI window (`[MiColStart, MiColEnd)`, from the header's `MiColStarts`/`MiRowStarts`) of
**one shared set of frame-sized grids** (spec 5.11.2); then the in-loop filters run
once over the whole frame. A 2-tile test decodes the same keyframe bytes into two
128px windows of a 256×64 frame → flat-DC everywhere, proving per-tile placement +
tile independence. Multi-tile is track 1 of the 4 remaining AV1-decode capabilities.
A 2-dimension adversarial review (driver-correctness / filter-frame + single-tile
regression) confirmed the driver with **no correctness defects**; its one
coverage-gap finding (the 2-tile test used only no-op filters) was closed by decoding
the 2-tile stream a second time with CDEF enabled (the filter pipeline runs over the
whole frame). **20,545 suite assertions + 1,140 fuzz assertions, all green; `make
lint` green.**

### Added
- **Grid sharing** (`src/av1_residual.cyr`): `av1_tile_share_grids(dst, src)` copies
  the frame-sized MI grid pointers + frame dims so several tiles write into one shared
  frame grid, each in its own MI window.
- **Multi-tile driver** (`src/av1_decode.cyr`, `av1_decode_frame`): loops
  `[tg_start, tg_end]`, deriving each tile's window from `MiColStarts`/`MiRowStarts`;
  tile 0 allocates the grids, the rest share them; each tile is assembled
  (`set_frame_mi` + `set_window`), activated, and decoded into its window. The in-loop
  filters then run over the whole frame (tile 0's window reset to the frame). A frame
  split across multiple tile groups is rejected `DR_ERR_UNSUPPORTED` (a later bite).
- **Test** (`tests/av1_decode.tcyr`): `test_frame_decode_2tile` — a 256×64 frame, two
  128px tile columns, the same all-skip bytes decoded into each window → the whole
  frame is flat-128 (both windows placed with no gap/overlap). (`frame_mk_fh` now sets
  `MiColStarts`/`MiRowStarts`, which the driver reads.)

### Scope / deferred
- Multi-tile decode is exercised for **all-skip** tiles (the encode lane's current
  reach). A **non-skip** multi-tile tile additionally needs the tile-relative
  above/left **coeff-context split** (the strips are tile-local; a windowed tile would
  misindex them). Deferred — documented in `av1_decode_frame` + roadmap.

## [0.7.48] - 2026-07-12

**Multi-tile foundation, step 2: tile-window geometry (per-tile MI origins).**
Building on 0.7.47's frame-addressed grids, `Av1Tile` gains an absolute MI window —
`MiColStart`/`MiRowStart`/`MiColEnd`/`MiRowEnd` (spec 5.11.2) — set via
`av1_tile_set_window`. The `decode_tile` SB loop now runs over the window
(`r = MiRowStart..MiRowEnd`, `c = MiColStart..MiColEnd`), which makes **every
downstream coordinate frame-absolute** (per the map's leverage insight — the
partition/block recursion is untouched); and the tile-bounds checks (`is_inside`, the
`decode_partition`/`_leaf`/`encode_partition` early-outs + `has_rows`/`has_cols` +
edge guards, `block_write_grids`, `bd_clear`, `transform_block`'s extent check) now use
the absolute window end. **Behavior-preserving for single-tile** (`MiColEnd == MiCols`
→ byte-identical; all existing tests pass unchanged). A window-bound adversarial
review **caught a real latent bug** — the `LoopfilterTxSizes` write clamp in
`transform_block` still used the window *extent* (`MI_COLS`) against an *absolute*
plane coord, so a windowed tile would have written no LFTX data → garbage deblock
(invisible to single-tile tests since `MiCols == MiColEnd`); fixed at the source. The
tile-relative context split (above/left/coeff indexing), grid sharing across tiles,
and the multi-tile driver + 2-tile end-to-end test are the next bite. **20,538 suite
assertions + 1,140 fuzz assertions, all green; `make lint` green.**

### Changed
- **Tile-window geometry** (`src/av1_residual.cyr`, `src/av1_tile.cyr`,
  `src/av1_partition.cyr`): `Av1Tile` gains `COL_START`/`ROW_START`/`COL_END`/`ROW_END`
  (defaulted to `[0, MiCols) × [0, MiRows)` in `av1_tile_new`); `av1_tile_set_window`
  sets the window and resets `MI_COLS`/`MI_ROWS` to the window extent (for the
  tile-local above/left scratch). The SB loop starts at the origin; `is_inside` and
  every partition/grid/extent bound compares against the absolute window end. The
  crux: with a window, `MI_COLS` becomes the *extent*, so every bound against an
  absolute coord uses `COL_END`/`ROW_END`, never `MI_COLS`.
- **Test** (`tests/av1_residual.tcyr`, +11): `test_tile_window` — `set_window` sets
  the window + resets `MI_COLS` to the extent; `is_inside` respects the window
  (col 32/63 inside `[32,64)`, col 31/64 and row 16 outside — the cross-tile-edge
  availability check); single-tile defaults to the whole frame.

## [0.7.47] - 2026-07-12

**Multi-tile foundation, step 1: frame-addressed MI grids.** The AV1 MI grids
(MiSizes / YModes / UVModes / Skips / InterTxSizes / the 3 LoopfilterTxSizes /
CdefIdx) were tile-sized with a tile-relative stride — but the in-loop filters run
frame-wide across tile boundaries, so multi-tile requires **frame-sized shared grids**
indexed by absolute MI. This bite converts the grid substrate: the grids now allocate
at and stride by the **frame** MI dimensions (`Av1Tile` gains `FMI_COLS`/`FMI_ROWS`,
defaulting to the tile dims), so several tiles can later share one frame-sized grid,
each writing its own MI window. **Behavior-preserving for single-tile** (FMI == MiCols
→ byte-identical; all existing tests pass unchanged). The tile-window origins + SB-loop
+ multi-tile driver are the next bites. Multi-tile is track 1 of the 4 tracked
remaining AV1-decode capabilities. **20,527 suite assertions + 1,140 fuzz assertions,
all green; `make lint` green.**

### Changed
- **Frame-addressed MI grids** (`src/av1_residual.cyr`): `Av1Tile` gains
  `AV1TILE_FMI_COLS` / `AV1TILE_FMI_ROWS` (the frame MI dimensions = grid alloc size
  + row stride), defaulted to the tile dims in `av1_tile_new` and overridable via
  the new `av1_tile_set_frame_mi(tile, fmi_cols, fmi_rows)` (call before
  `av1_tile_grids_new`). `av1_tile_grids_new` allocs `FMI_COLS*FMI_ROWS`; every grid
  accessor (`av1_grid_get/set`, `av1_lftx_get/set`, `av1_cdefidx_get/set`), the CDEF
  read context stride (`av1_tile_set_cdef_ctx`, ctx+40), and the `clear_cdef` stride
  passed from `decode_tile`/`encode_tile` now use the frame stride. All remaining
  `AV1TILE_MI_COLS` uses stay tile-extent (SB-loop bounds, `is_inside`, pixel bounds,
  tile-local scratch sizing) — audited for stride consistency.
- **Test** (`tests/av1_residual.tcyr`, +6): `test_frame_addressed_grids` — with
  `FMI_COLS` overridden above the tile MiCols, two grid cells that would COLLIDE under
  the old tile stride (`[1][2]` and `[0][10]` both → flat 10 at stride 8) stay distinct
  (→ flat 18 and 10 at stride 16), and the CdefIdx grid + CDEF ctx use the frame stride.

## [0.7.46] - 2026-07-12

Enables **10/12-bit (high-bit-depth) decode**. `av1_decode_frame` no longer rejects
a non-8-bit sequence — the whole pixel pipeline already threads `bit_depth`
(dequant's `1<<(7+bit_depth)` clamp + the 8/10/12-bit Qlookup tables, the inverse
transform, reconstruct's `Clip1`, every intra mode, and all three in-loop filters'
`(bit_depth-8)` scaling), so removing the blanket guard was all it took. A 10-bit
keyframe now reconstructs to the correct mid-value (`1<<(BitDepth-1)` = 512), a
12-bit one to 2048. First of the four tracked remaining AV1-decode capabilities
(multi-tile / superres / inter / 10-bit — the user directive is to pursue all;
superres + inter await their coefficient tables). A 3-dimension adversarial audit
**workflow** (intra-pred / residual-transform / filters-and-test) swept the pixel
pipeline for hidden 8-bit assumptions and found **none** — notably, a *major*-flagged
SGR box-filter candidate (raw box-sum `b` vs bit-depth-rounded `d`) was rigorously
**refuted** by the verify pass with a flat-region identity proof: the raw `b` is
correct, and the proposed "fix" would itself have broken 10-bit SGR. **20,521 suite
assertions + 1,140 fuzz assertions, all green; `make lint` green.**

### Changed
- **10/12-bit decode enabled** (`src/av1_decode.cyr`): dropped the
  `av1_seq_bitdepth != 8 → DR_ERR_UNSUPPORTED` guard; the reconstruction frame is
  created at the sequence bit depth (`dr_frame_new` validates `BitDepth ∈ {8,10,12}`).
  `use_superres` remains rejected (upscaling unimplemented).
- **Tests** (`tests/av1_decode.tcyr`): `test_frame_decode_10bit` (flat DC 512) +
  `test_frame_decode_12bit` (flat DC 2048) — the skip-DC keyframe tile bytes are
  bit-depth independent, so the same encoded tile reconstructs at the higher depth.
  (`test_frame_decode_highbd_rejected`, which asserted the old rejection, is retired.)
  `test_frame_decode_10bit_cdef` additionally drives the CDEF stage at 10-bit (fresh
  10-bit CdefFrame + direction search + `coeff_shift = bit_depth-8` strengths;
  all-skip → passthrough). Coverage note: the flat tests exercise DC prediction + the
  CDEF path; the directional-intra, residual/transform, and deblock/LR *active-filter*
  math at 10/12-bit are covered by the audit workflow (code-inspected) rather than a
  non-flat high-bit-depth known-answer test — a future hardening (needs a spec model).

## [0.7.45] - 2026-07-12

Teaches `av1_decode_obus` the **combined FRAME OBU (type 6)** — the common real-stream
form that carries the frame header + tile group in a single OBU (spec 5.10
`frame_obu`), previously rejected `DR_ERR_UNSUPPORTED`. The walk now parses the
embedded frame header, splits off the tile group at the **byte-aligned header end**
(`headerBytes = ceil(bits_consumed / 8)`), and decodes it — so both the separate-OBU
form and the combined FRAME OBU decode end-to-end to pixels. A 3-dimension
adversarial review **workflow** (byte-split / error-integration / test-adequacy, each
finding refute-by-default verified) confirmed the split with **no correctness
defects** (it also proved the `hbytes > osize` guard is unreachable — kept as
defensive); its reachable coverage gap (the 0-byte tile-group boundary) was closed
with a test. **20,512 suite assertions + 1,140 fuzz assertions, all green; `make
lint` green.**

### Added
- **FRAME OBU (type 6) handling** (`src/av1_decode.cyr`, `av1_decode_obus`): parse
  the embedded `frame_header_obu`, compute `hbytes = (av1_fh_bits_consumed(fh) + 7)
  >> 3` (the `byte_alignment()` after the header, spec 5.10), bounds-check
  `hbytes > osize` → `DR_ERR_TRUNCATED`, then decode the tile group at
  `buf + off + hbytes` (size `osize - hbytes`) via `av1_decode_frame`. A
  `FRAME` OBU before any `SEQUENCE_HEADER`, or a malformed embedded header, is
  rejected with the precise error (no wrong decode).
- **Tests** (`tests/av1_decode.tcyr`, +8, net): `test_obus_frame_obu` — build a real
  FRAME OBU (`frame-header bytes ++ tile-group bytes`) and decode it end-to-end to
  flat-DC pixels (proving the byte-split lands exactly at the tile start; an
  off-by-one would desync); a no-sequence-header FRAME OBU and a malformed embedded
  header (both surfacing the precise error); and a FRAME OBU whose payload is exactly
  the frame header (0-byte tile group → clean error, no crash). (The old
  `test_obus_frame_obu_rejected`, which asserted `DR_ERR_UNSUPPORTED`, is retired.)
  A known coverage limitation: the happy-path fh is 35 bits, which cannot distinguish
  `ceil` from `floor+1` in the split (both give 5) — constructing an exact-multiple-
  of-8-bit header without changing the decode is impractical, so the ceil intent is
  documented inline instead.

## [0.7.44] - 2026-07-12

Adds the **OBU-stream walk** `av1_decode_obus` to `src/av1_decode.cyr` — the
outermost decode layer that **takes raw AV1 OBU bytes to pixels**. It walks an OBU
stream (`av1_obu_next`), dispatching by type — `SEQUENCE_HEADER` → `av1_seq_parse`,
`FRAME_HEADER` → `av1_frame_parse_uncompressed_header`, `TILE_GROUP` →
`av1_decode_frame` — threading the active sequence + frame header through and
skipping temporal delimiters / metadata / padding. **A complete keyframe bitstream
(TD + SEQUENCE_HEADER + FRAME_HEADER + TILE_GROUP OBUs) now decodes end-to-end to
pixels** — the raw-bitstream-to-pixels loop is closed. A 3-dimension adversarial
review **workflow** (dispatch-state / error-safety / spec-and-test, each finding
refute-by-default verified) confirmed the walk with **no correctness defects**; its
four test-coverage findings were all closed with new tests. **20,504 suite
assertions + 1,140 fuzz assertions, all green; `make lint` green.**

### Added
- **OBU-stream walk** (`src/av1_decode.cyr`): `av1_decode_obus(buf, sz, out_err)` —
  iterate the OBUs and return the first coded frame decoded + filtered to pixels.
  Dispatch is type-routed with the sequence/frame-header state threaded across
  OBUs (a `FRAME_HEADER` before any `SEQUENCE_HEADER`, or a `TILE_GROUP` before
  either, is rejected `DR_ERR_BAD_HEADER`, not a null deref); `av1_obu_next`'s
  tri-state return (`DR_OK` / `AV1_OBU_END` / sticky error) is handled so a parse
  fault is never mistaken for a clean "no frame".
  - **Scope**: separate-OBU keyframe streams, single-tile 8-bit
    (`av1_decode_frame`'s scope). The combined **FRAME OBU** (type 6:
    frame_header + tile_group in one, needing the fh/tile-group byte split) is
    rejected `DR_ERR_UNSUPPORTED` (a later bite); a stream with no tile group
    returns `DR_ERR_BAD_HEADER`.
- **Tests** (`tests/av1_decode.tcyr`, +34): the **end-to-end milestone** — build a
  real `TD + SEQUENCE_HEADER + FRAME_HEADER + TILE_GROUP` OBU stream (custom mono
  128×64 seq + reduced-key frame header hand-built to match an encoded keyframe
  tile) and decode it through `av1_decode_obus` to flat-DC (128) pixels; a
  header-construction sanity check (the hand-built seq/fh parse to the exact
  expected fields); dispatch/error paths (bad args, TD-only, FRAME-OBU rejection,
  tile-group-without-headers); and the review's coverage gaps — a forbidden-bit OBU
  (sticky `DR_ERR_FORBIDDEN_BIT` propagated, not masked), a malformed
  SEQUENCE_HEADER payload (parse error surfaced), and metadata + padding OBUs
  interspersed through the stream (skipped, and the decode stays correct despite the
  shifted byte offsets — a strong witness for the per-OBU slicing).

## [0.7.43] - 2026-07-12

Adds the **frame-level decode driver** `av1_decode_frame` to `src/av1_decode.cyr`
— the integration that decodes a **whole keyframe from parsed headers to filtered
pixels**, tying together every stage built across 0.7.23-0.7.42 (tile group 5.11.1
→ tile assembly + decode_tile 5.11.2 → in-loop filter pipeline 7.4). Given an
already-parsed sequence + frame header and the tile-group payload, it creates the
reconstruction frame, parses the tile group, assembles + activates + decodes the
tile (all params header-driven), and runs the deblock → CDEF → LR pipeline —
returning the final frame. **This is the first end-to-end headers-to-pixels decode.**
Scoped to single-tile 8-bit keyframes; multi-tile, superres, and non-8-bit are
rejected cleanly (`DR_ERR_UNSUPPORTED`) rather than mis-decoded. A 3-dimension
adversarial review **workflow** (field-mapping / error-geometry / scope-integration,
each finding refute-by-default verified) **confirmed two real gaps** (both fixed +
tested): a 10/12-bit sequence was reconstructed at 8-bit (silent mis-decode), and the
frame-alloc failure path masked `dr_frame_new`'s precise error code (a dimension bomb
reported as `OOM` instead of `OVERSIZE`). **20,470 suite assertions + 1,140 fuzz
assertions, all green; `make lint` green.**

### Added
- **Frame-level decode driver** (`src/av1_decode.cyr`): `av1_decode_frame(seq, fh,
  buf, sz, out_err)` — decode one single-tile intra frame from its parsed headers +
  the tile-group payload to the final in-loop-filtered frame. Header-driven tile
  assembly: `mi_cols`/`mi_rows`/`base_q`/`reduced_tx`/`tx_mode` ← fh,
  `enable_intra_edge_filter`/`enable_filter_intra`/`num_planes`/subsampling ← seq,
  `disable_cdf` ← `disable_cdf_update`; then `av1_activate_intra_filters` (CDEF ctx
  + LR params) and `av1_apply_loop_filters`. Every fallible step's error is
  propagated via `*out_err` (returns 0 on failure).
  - **Scope guards** (never a wrong decode): `NumTiles != 1`, `use_superres`, and
    non-8-bit `BitDepth` all return `DR_ERR_UNSUPPORTED` — multi-tile needs per-tile
    MI origins; superres upscaling (7.16) is not implemented (a superres frame would
    emit a non-upscaled, wrong-size frame); the decode path (intra pred / inverse
    transform / recon) is 8-bit only (a 10/12-bit sequence would reconstruct at the
    wrong depth — this one caught by the adversarial review's `error-geometry` pass).
### Fixed
- **Frame-alloc error path masked the precise cause** (review finding): on
  `dr_frame_new` failure `av1_decode_frame` overwrote `*out_err` with `DR_ERR_OOM`,
  hiding the `DR_ERR_OVERSIZE` (dimension bomb) / `DR_ERR_BOUNDS` codes `dr_frame_new`
  had already written. Now a bare `return 0` preserves the precise code so a hostile
  oversize is distinguishable from a transient resource failure.

### Added (tests)
- **Tests** (`tests/av1_decode.tcyr`, +19): encode a keyframe tile → decode it
  through `av1_decode_frame` from hand-built matching headers → verify the frame
  dims + flat-DC (128) pixels (headers → pixels); a CDEF-enabled variant (drives
  the seq/fh → activate → filter path); multi-tile / `use_superres` / non-8-bit /
  dimension-bomb (`DR_ERR_OVERSIZE`, not masked) rejection; and a truncated-payload
  case (the driver surfaces the symbol decoder's sticky error, proving it genuinely
  runs the decode).

## [0.7.42] - 2026-07-12

Adds **tile-group OBU parsing** (`av1_tile_group_parse`, spec 5.11.1) to
`src/av1_decode.cyr` — the frame-driver prerequisite that extracts each tile's
byte range from a tile-group payload so the driver can hand `(buf + offset, size)`
to `decode_intra_tile`. Parses the group header
(`tile_start_and_end_present_flag` + `tg_start`/`tg_end`), then per-tile: non-last
tiles carry a `tile_size_minus_1 = le(TileSizeBytes)` prefix, the last takes the
remaining bytes. Every size field and tile extent is bounds-checked against the
payload — a lying or truncated size is rejected with a sticky error, never an OOB
read. A 3-dimension adversarial review **workflow** (spec-conformance /
input-safety / offset-arithmetic, each finding refute-by-default verified) cleared
it. **20,451 suite assertions + 1,140 fuzz assertions, all green; `make lint`
green.**

### Added
- **Tile-group OBU parser** (`src/av1_decode.cyr`):
  - `av1_read_le(buf, n)` — spec 4.10.4 `le(n)` little-endian byte read (used
    byte-aligned for the `TileSizeBytes` size fields).
  - `Av1TileGroup` (`av1_tile_group_new` + accessors `av1_tg_start` / `_end` /
    `_num_tiles` / `_count` / `_tile_offset` / `_tile_size` / `_tile_row` /
    `_tile_col`) — holds the group's `[tg_start, tg_end]` range and, per whole-frame
    `TileNum`, the tile data's byte offset + size within the payload (absent tiles
    keep offset `-1`).
  - `av1_tile_group_parse(tg, buf, sz, fh, out_err)` — the 5.11.1 parse: header
    (present flag gated on `NumTiles > 1`, `tg_start`/`tg_end` via
    `f(TileColsLog2 + TileRowsLog2)`), `byte_alignment`, then the per-tile size walk.
    Trust-no-input: `NumTiles` capped at `MAX_TILE_COLS*ROWS`, `TileSizeBytes` to
    1..4, `tg_start`/`tg_end` validated against `NumTiles` **before** any array
    index, and every extent checked against `sz`
    (`DR_ERR_TRUNCATED`/`DR_ERR_BAD_HEADER`/`DR_ERR_BOUNDS`).
- **Tests** (`tests/av1_decode.tcyr`, +60): `le(n)` known-answers; single-tile (no
  header bits, whole payload is tile 0); 4-tile no-present-flag (per-tile
  offset/size + row/col mapping, data-byte spot-check); present-flag sub-range
  (tiles outside `[tg_start, tg_end]` stay `-1`); `TileSizeBytes = 2` size field
  through the parser; single-tile group at a nonzero index (`tg_start == tg_end`,
  last-tile branch); adversarial (lying size, truncated size field, inverted
  `tg_end < tg_start`, undersized capacity).

## [0.7.41] - 2026-07-12

Grows `src/av1_decode.cyr` toward the frame-level driver with the **frame-header
filter activation** step — the piece that turns the CDEF/LR decode-time reads
(wired-but-inert since 0.7.32/0.7.39) **live for a real bitstream**.
`av1_lr_params_from_fh` builds an `Av1LrParams` straight from the parsed frame
header (per-plane `FrameRestorationType`/`LoopRestorationSize` + the `read_lr`
frame flags); `av1_activate_intra_filters` attaches the CDEF read context (when the
sequence enables CDEF) + the LR params to a decode tile. An end-to-end test now
decodes a keyframe tile whose LR params were **derived from a header** (the
production path), reading back the exact Wiener coeffs the encoder wrote — the
activation-gap closure. A 3-dimension adversarial review **workflow**
(spec-conformance / error-memory / activation-correctness, each finding
independently refute-by-default verified) cleared the change. **20,391 suite
assertions + 1,140 fuzz assertions, all green; `make lint` green.**

### Added
- **Frame-header filter activation** (`src/av1_decode.cyr`):
  - `av1_lr_params_from_fh(fh, seq, uw, fh_h, np, out_err)` — build the
    `Av1LrParams` for a frame from its header (spec 5.9.20 `lr_params` + 7.17):
    returns 0 when `UsesLr == 0` (frame uses no LR, not an error) or on OOM;
    otherwise a fresh params with each non-`NONE` plane's restoration type + unit
    size and the `allow_intrabc`/`use_superres`/`SuperresDenom` flags `read_lr`
    consumes, subsampling from the sequence.
  - `av1_activate_intra_filters(tile, seq, fh, lr_params)` — attach the CDEF read
    context (5.11.56 `read_cdef`, only when `av1_seq_enable_cdef`; carries
    `cdef_bits` + the `coded_lossless`/`allow_intrabc` gates) and the LR params
    (5.11.57 `read_lr`; 0 leaves `read_lr` inert). After this, `decode_intra_tile`
    populates `CdefIdx` + the LR unit grids that `av1_apply_loop_filters` consumes.
    Returns the `set_cdef_ctx` `DrErr` (may OOM / bounds-fault on a null grid).
- **Tests**: `tests/av1_decode.tcyr` (+ unit: `from_fh` maps header → params incl.
  the no-LR → null / not-an-error path, `activate` sets the ctx only when CDEF is
  enabled + always attaches LR); `tests/av1_tile.tcyr` `test_lr_activation_from_fh`
  (end-to-end: decode a keyframe tile with **header-derived** LR params, read back
  the encoder's Wiener coeffs 15/20 per SB — proves the header → params →
  `decode_tile` chain).

## [0.7.40] - 2026-07-11

Adds the AV1 **in-loop filter pipeline** (`src/av1_decode.cyr`, a new module — the
seed of the frame-level decode driver): `av1_apply_loop_filters` chains
deblocking (7.14) -> CDEF (7.15) -> loop restoration (7.17) in spec-7.4 order over a
reconstructed tile frame, managing the `CurrFrame`/`CdefFrame`/`LrFrame` buffers and
returning the final filtered frame. **This is the first time all three in-loop
filters run chained together.** A 3-dimension adversarial review **workflow**
(spec-order / frame-management / memory-error, each finding independently verified)
**found + confirmed a real conformance bug** — a **latent `av1_deblock` defect since
0.7.28** the pipeline exposed — now fixed. **20,367 suite assertions + 1,140 fuzz
assertions, all green; `make lint` green.**

### Added
- **In-loop filter pipeline** (`src/av1_decode.cyr`): `av1_apply_loop_filters(tile,
  fh, seq, lr_params, out_err)` — deblock in place (7.14.1), then CDEF (gated on
  `av1_seq_enable_cdef`, into a fresh `CdefFrame` via `av1_cdef_frame_new`), then LR
  (gated on `av1_fh_uses_lr` && `lr_params`, into a fresh `LrFrame`), returning the
  final frame with OOM + CDEF coverage-guard (`DR_ERR_BOUNDS`) error propagation.
- **Tests** (`tests/av1_decode.tcyr`, +12): no-filter passthrough (result == input
  frame), CDEF (new frame, spike deringed 140 -> 138), CDEF+LR chaining (LR carries
  138 through), deblock-in-place (edge -> 125) — each matching the standalone
  filters' known answers.

### Fixed
- **`av1_deblock` missing the 7.14.1 frame-level gate (review finding, latent since
  0.7.28):** `av1_deblock` forced `run=1` for luma and relied on the caller to gate
  on `loop_filter_level`. With **both base luma levels 0 but `loop_filter_delta_enabled`
  set** (a legal header; `ref_deltas[INTRA]` defaults to +1), the per-edge strength
  became +1 and it filtered where spec 7.14.1 forbids ALL filtering — corrupting
  pixels that then feed CDEF/LR. Fixed at the source: `av1_deblock` now self-gates
  (`if loop_filter_level[0]==0 && [1]==0: return`). Regression test added
  (`test_deblock_level0_delta`). Not reachable before (av1_deblock had no production
  caller); the pipeline is the first.

### Notes
- `drishti_version()` -> 740. Next: grow `av1_decode.cyr` into the full frame driver
  — OBU walk -> seq/fh -> tile assembly (setting the CDEF context + LR params from
  the frame header, activating the decode-time reads) -> `decode_intra_tile` -> this
  pipeline — which activates the whole in-loop filter layer for real streams.

## [0.7.39] - 2026-07-11

Wires **`read_lr` into `decode_tile`** (spec 5.11.2) — the loop-restoration unit
params are now read from the bitstream per superblock during tile decode, and
mirrored on encode. This completes the loop-restoration decode-tile integration:
`decode_tile` resets the `RefLrWiener`/`RefSgrXqd` predictor per tile, then per SB
(after `clear_cdef` + `clear_block_decoded`, before `decode_partition`) calls
`read_lr`. A 1-agent adversarial review verified all 6 points — the module reorder
legality, the spec order, encode/decode parity, backward-compat, the struct
offsets, and activation honesty — with **no functional bugs**. **Unlike the CDEF
wiring, this is activated + round-trip-tested end-to-end through `decode_tile`.**
**20,353 suite assertions + 1,140 fuzz assertions, all green; `make lint` green.**

### Added
- **`read_lr` in `decode_tile` / `encode_tile`** (`src/av1_tile.cyr`): guarded by
  the new `AV1TILE_LRPARAMS` tile field (`av1_tile_set_lr_params`; 0 = off, so
  non-LR streams are byte-identical), `av1_lr_ref_reset` runs per tile and
  `av1_read_lr`/`av1_write_lr` per SB. `Av1LrParams` gains the read_lr frame flags
  (`allow_intrabc` / `use_superres` / `SuperresDenom`) via
  `av1_lr_params_set_frame_flags`.
- **Module reorder**: `src/av1_lr.cyr` moved before `src/av1_tile.cyr` in the
  include chain (it is self-contained — no `av1_tile`/`av1_deblock`/`av1_cdef`
  deps) so `decode_tile` can call the read_lr functions.
- **Tests** (`tests/av1_tile.tcyr`, +6): a full keyframe `encode_tile` ->
  `decode_tile` round-trip with 2 Wiener restoration units attached — **`read_lr`
  fires through `decode_tile`**, populating SB0 -> unit(0,0) and SB1 -> unit(0,1)
  from the interleaved bitstream, with the partition tree still round-tripping.

### Notes
- `drishti_version()` -> 739. **Loop-restoration is now complete through the
  decode-tile layer** (pixel processes + bitstream parsing + decode_tile wiring),
  and — unlike CDEF, which was verified only at the mode-info level — is exercised
  end-to-end via a tile round-trip. The remaining gap (shared with CDEF): no
  production frame-level driver attaches the LR params / CDEF context yet, so both
  are inert for real streams until that driver. That frame-level driver
  (OBU -> seq/fh -> tile assembly -> decode -> deblock -> CDEF -> LR), which
  activates everything, is next. Also fixed a stale `av1_tile.cyr` header comment
  that under-claimed loop-restoration as "deferred".

## [0.7.38] - 2026-07-11

Adds the AV1 **`read_lr`** per-superblock geometry (spec 5.11.57, `src/av1_lr.cyr`)
— for a superblock at MI (r, c) of size bSize, it computes the restoration-unit
range the superblock overlaps (`unitRowStart/End`, `unitColStart/End`, with the
`use_superres` `SuperresDenom`/`SUPERRES_NUM` horizontal scaling) per plane and
dispatches `read_lr_unit`. This completes the `read_lr` bitstream-parsing logic;
only the `decode_tile` wiring remains. A 1-agent adversarial review verified **all
8 geometry checks** against the spec — the division grouping, the superres branch,
the half-open loop bounds, the `Min` clamps (no OOB), and read/write parity — with
**no bugs**. **20,347 suite assertions + 1,140 fuzz assertions, all green; `make
lint` green.**

### Added
- **`av1_read_lr` / `av1_write_lr`** (`src/av1_lr.cyr`): the §5.11.57 per-SB loop
  — `allow_intrabc` early-return; per plane with `FrameRestorationType != NONE`,
  `unitRowStart = (r*(MI_SIZE>>subY) + unitSize-1)/unitSize`,
  `unitRowEnd = Min(unitRows, ((r+h)*(MI_SIZE>>subY) + unitSize-1)/unitSize)`, the
  `numerator`/`denominator` (superres-scaled) column range, then the half-open
  `unitRow`x`unitCol` double loop dispatching `read_lr_unit` / `write_lr_unit`.
- **Tests** (`tests/av1_lr.tcyr`, +5 -> 80): two 64x64 superblocks reading one unit
  each (SB(0,0) -> unit(0,0), SB(0,16) -> unit(0,1)), a 128x128 superblock spanning
  **both** units (the col loop runs twice), and the `allow_intrabc` early-return —
  all round-tripped through `write_lr` -> `read_lr`.

### Notes
- `drishti_version()` -> 738. Loop-restoration bitstream parsing is complete
  (`read_lr` -> `read_lr_unit` -> the subexp/CDF reads). The last LR integration
  piece is wiring `read_lr` + the per-tile `av1_lr_ref_reset` into `decode_tile`
  (alongside the existing `clear_cdef`), plus attaching the `Av1LrParams` to the
  tile — the same wiring pattern CDEF used. Then the frame-level deblock -> CDEF ->
  LR driver, then inter prediction.

## [0.7.37] - 2026-07-11

Adds AV1 **`read_lr_unit`** (spec 5.11.57) — the per-restoration-unit bitstream
read of the loop-restoration type + Wiener coefficients / SGR set+xqd, into
`Av1LrParams`. Extends the non-coeff CDF blob with the 3 restoration-type CDFs
(`use_wiener` / `use_sgrproj` / `restoration_type`), and adds the `Wiener_Taps` /
`Sgrproj_Xqd` tables + the `RefLrWiener` / `RefSgrXqd` subexp predictor state. A
1-agent adversarial review verified **all 6 checkpoints** against the spec — the
CDF placement/copy, the frame-type-gated type read, the chroma `firstCoeff`/
`tap[0]=0` (and its Ref-skip), and the `radius==0` computed-xqd clip with the
encoder Ref-sync — with **no bugs**. **20,342 suite assertions + 1,140 fuzz
assertions, all green; `make lint` green.**

### Added
- **LR restoration-type CDFs** (`src/av1_noncoeffcdf.cyr`): `use_wiener`
  (`{11570,32768,0}`), `use_sgrproj` (`{16855,32768,0}`), `restoration_type`
  (`{9413,22581,32768,0}`) appended to the non-coeff blob (1622 -> 1634 entries)
  + `av1_ncdf_use_wiener` / `_use_sgrproj` / `_restoration_type` accessors.
- **`av1_read_lr_unit` / `av1_write_lr_unit`** (`src/av1_lr.cyr`): read/encode the
  restoration type via the frame-type-gated CDF (`RESTORE_WIENER` -> `use_wiener`,
  `RESTORE_SGRPROJ` -> `use_sgrproj`, `RESTORE_SWITCHABLE` -> the 3-way
  `restoration_type`), then the Wiener taps (per pass, `firstCoeff = plane?1:0`,
  `decode_signed_subexp_with_ref_bool` with the tap Min/Max/K + the `RefLrWiener`
  predictor) or the SGR `lr_sgr_set` = `L(4)` + the 2 xqd weights (subexp, or the
  `radius==0` / `i==1` `Clip3((1<<7)-RefSgrXqd[0])` computed case). Plus the
  `Wiener_Taps`/`Sgrproj_Xqd` tables, the `RefLrWiener`/`RefSgrXqd` state on
  `Av1LrParams`, and `av1_lr_ref_reset` (per-tile reset to the Mid tables).
- **Tests** (`tests/av1_lr.tcyr`, +18 -> 75): the CDF defaults, and full unit
  round-trips — Wiener (both passes, all taps), SGR set+xqd, the `radius==0`
  computed-xqd path (set 14 -> xqd1 = 95), and `SWITCHABLE` -> `NONE`.

### Notes
- `drishti_version()` -> 737. Next: the `read_lr` per-superblock geometry (the
  unit-range loop, with superres) + the `decode_tile` wiring + `av1_lr_ref_reset`,
  which completes loop-restoration bitstream parsing. A newer `cyrlint` (installed
  `cycc` drift) now flags "later bite" as a deferral keyword; a pre-existing 0.7.35
  comment was reworded to clear it.

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
