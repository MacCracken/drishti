# drishti — Current State

> Refreshed every release. CLAUDE.md is preferences/process/procedures
> (durable); this file is **state** (volatile) — versions, counts,
> sizes, in-flight work.

## Version

**0.7.89** — cut 2026-07-17, not yet tagged (user's git). **COMPOUND DIFFWTD (MASKED) INTER PREDICTION.** A
two-reference block with comp_group_idx==1 && type==COMPOUND_DIFFWTD blends its two predictions through a
PER-PIXEL difference mask — the first MASKED compound mode, reusing the 0.7.87/0.7.88 prep intermediates.
Only WEDGE (type==COMPOUND_WEDGE, needs a mask codebook) stays refused on both lanes. av1_diffwtd_mask_build
(spec 7.11.3.12, src/av1_mc.cyr) fills a new per-luma-pixel Av1_McMask: m = Clip3(0,64, 38 + (Round2(Abs(
t0-t1), (BitDepth-8)+ib) >> 4)), inverted to 64-m when mask_type!=0 (base 38, DIFF_FACTOR 16, MAX_ALPHA 64;
the diff-norm shift is bit-depth dependent — 4 @8-bit, 6 @10/12-bit). The blend (av1_mc_pred_compound gained
comp_mode/mask_type): Clip1(Round2(tmp0*m + tmp1*(64-m), ib+6)); the 6 is AOM_BLEND_A64_ROUND_BITS (log2 of
the mask-sum 64); the scalar AVERAGE/DISTANCE path (comp_mode==0) is untouched. Chroma (av1_diffwtd_mask_at):
the mask is built ONCE on luma then read subsampled — 4:2:0 = Round2(2x2 sum, 2), 4:2:2/vert = Round2(2x1,
1); luma read indices edge-clamped (defensive). Un-gate both lanes to admit type==DIFFWTD; narrow the reject
to WEDGE. 3-source verified (compound_diffwtd.md). THE PROOF (tests/av1_mc_driver.tcyr, av1_intertile.tcyr):
the mask+blend vs an INDEPENDENT integer-MV oracle (p0*m+p1*(64-m)+32)>>6 with m recomputed from the spec
formula (8/10/12-bit, both mask_types, mask varies per-pixel, DIFFWTD-differs-from-AVERAGE); a 4:2:0 chroma
oracle recomputing the luma mask + 2x2 average (witnessing the subsample AND mask-from-luma); Python-
independent KATs from the new spec-literal scripts/refs/diffwtd_ref.py (a third derivation); a DIFFWTD
round-trip (both mask_types) EXHAUSTIVELY equal to the av1_mc_pred_compound(comp_mode=1) oracle AND
differing from AVERAGE. Mutations, 0 survivors: the combine shift, the diff-norm bit-depth shift, base/
divisor/Abs/inversion, and the chroma subsample die in the driver's INDEPENDENT oracle (the round-trip
shares av1_mc_pred_compound, can't see combine-internal bugs); the decode mode-threading + both gate lanes
die in the round-trips. THE REVIEW (3 dims, worktree-isolated): math CLEAN, memory-safety CLEAN (the
top-risk chroma-subsample × edge-clamp proven safe at odd luma dims down to 1x1; no Av1_McMask overflow).
One CONFIRMED coverage finding — the DECODE-side WEDGE reject had NO witness (a 64x64 block can't carry a
wedge symbol) — CLOSED with a 32x32-via-SPLIT fixture that mints a WEDGE stream and drives it through the
decoder as the LAST sub-block (so mis-admission -> DR_OK, not a truncation error), mutation-verified; plus a
latent lw==0 negative-index read (unreachable) hardened with a guard. Next: **compound WEDGE (the mask
codebook) + inter-intra blends, OBMC/warp + the temporal scan**. **Prior: COMPOUND DISTANCE (jnt) (0.7.88).**
The first inter path that codes coefficients: a non-skip inter block decodes with the reconstructed residual
ADDED onto the MC prediction. Scope = UNIFORM tx (TX_MODE_LARGEST / ONLY_4X4, one uniform tx per plane);
var-tx (TX_MODE_SELECT recursion) stays a cleanly-gated later bite. The coeff loop was already inter-ready
(txb_skip/eob/coeff_base/br/dc_sign CDFs are set-agnostic) — the only NEW machinery is the inter
TRANSFORM-TYPE reads: `av1_transform_type_decode/encode` gained the is_inter branch (reads/writes
`inter_tx_type`, placed BEFORE the set dispatch — the tx-set enum COLLIDES INTER_1==INTRA_1); new
Default_Inter_Tx_Type_Set1/2/3 CDFs (spec §10, 3-source verified) into av1_noncoeffcdf's TWO-tier blob (static
builder 1636→1695 AND the av1_ncdf_new copy 1634→1693 — the ship-green-wrong trap); Tx_Type_Inter_Inv_Set1/2/3
+ Tx_Type_In_Set_Inter[4][16] into av1_txtype; compute_tx_type inter-chroma co-location (the block's single
luma TxType via AV1TTC_LUMA_TXTYPE, since <=64x64 uniform blocks have one luma tx). The DRIVER
(av1_intertile): av1_transform_block_inter + av1_residual_inter (NO intra predict; coeffs is_inter=1 +
reconstruct-onto-MC) + the paired encode lane (reads a per-block residual plan via the new AV1FB_RESID slot),
wired behind a VAR-TX gate (skip==0 && TX_MODE_SELECT && sub_size>BLOCK_4X4 && base_q!=0 → UNSUPPORTED, both
lanes). Av1BlockInfo grew 224→232 (a layout-guard test caught it). THE PROOF (tests/av1_intertile.tcyr, 166):
non-skip blocks round-trip with pixels EXHAUSTIVELY equal to an INDEPENDENT oracle (MC + reconstruct composed
from verified leaves with KNOWN planted coeffs/tx types) — per set (INTER_1/2/3), mono + 4:2:0, zero-residual
== pure MC; the 4:2:0 case caught a tx-type-vs-tx-size bug in the TEST oracle (decoder was right). Plus
tx-type round-trip, compute_tx_type matching scripts/refs/inter_residual_ref.py, absolute-offset CDF/table
pins, the var-tx gate. 11 mutations, 11 killed, 0 survivors. THE REVIEW (14 agents, 4 dims, worktree-isolated) confirmed 5+2 findings, all folded: the MAJOR was round-trip circularity (wrong interior CDF/membership/inverse values SURVIVED — every test round-trips through drishti's own encoder; fixed with FULL absolute-offset pins of all 59 CDF + 30 inverse + 64 membership entries vs the ref, killing the 3 survivors); a real encode/decode chroma-tx-type DESYNC when the luma tx is all-zero (no transform_type symbol written -> decoder derives DCT_DCT; the encoder now matches, byte-comparison witnessed); lossless chroma LFTX clamped to TX_4X4; reduced_tx_set threaded from the fh (latent fix) + covered; rectangular tx-set + the one-luma-tx-per-block co-location precondition pinned. The pre-existing use_128x128_superblock gap (read but ungated → a 128-SB stream silently mis-parsed as 64x64, returning DR_OK on garbage) is now FIXED: av1_frame_dec_new latches DR_ERR_UNSUPPORTED at the one chokepoint every decode path (intra+inter) shares, before any tile runs (test_frame_decode_sb128_rejected, mutation-verified — removing the gate flips UNSUPPORTED→DR_OK). Inter suite 166->343. Next: **the VAR-TX inter residual**
(read_var_tx_size + txfm_split CDF + transform_tree + the full per-4x4 TxTypes grid), then compound/OBMC/warp
+ the temporal scan. **Prior: THE INTER TILE DECODE — THE MILESTONE.**
A genuine AV1 inter frame decodes END-TO-END: raw bytes → the complete mode-info decode → motion-
compensated pixels from a DPB reference, through decode_block/decode_tile AND av1_decode_stream. NEW
module `src/av1_intertile.cyr` (after av1_dpb, the enum-visibility rule; the block/tile dispatchers
forward into it): av1_tile_set_inter_ctx + av1_decode_block_inter (5.11.15 driver → the skip scope
gate → compute_prediction per plane via av1_mc_pred_block from av1_dpb_ref_frame → the 5.11.4 storage
loops) + the paired encoder + the inter tile drivers (four per-tile adaptive inter CDF families).
Av1Tile grew 424→544 (the inter context + AV1TILE_IERR — a STICKY inter-lane error latch: the partition
walk discards block returns, so gate errors latch per block and the tile driver surfaces them).
Av1FrameDec carries DPB+refs; av1_frame_dec_group routes non-intra frames (UNSUPPORTED without a DPB);
av1_decode_stream threads its DPB+refs into both OBU paths. SCOPE (each gated UNSUPPORTED,
roadmap-tracked): non-skip inter residual / compound / inter-intra blend / OBMC-warp / scaled refs.
THE PROOF (tests/av1_intertile.tcyr, 98): gradient-reference tiles decode with pixels EXHAUSTIVELY
equal to an INDEPENDENT av1_mc_pred_block computation — integer (4096 px), sub-pel, dual-filter,
a 2x2-SB 128x128 frame with four MVs (16384 px; both neighbour-threading directions + per-quadrant
MI values), 4:2:0 THREE-PLANE two-SB (per-plane exhaustive oracles), GOLDEN→slot-3 reference
SELECTION over a decoy slot 0, and a NON-SB-aligned 48x48 frame (extent clamps + raw border-zero
probes); the spot KAs initially had the MV sign BACKWARDS and the exhaustive oracle overruled the
author, as designed. Plus the BYTE-STREAM layer: bit-exact non-still SEQ + KEY + INTER header builders
(parse-back verified, every byte consumed, KEY + INTER field pins incl. heights) through
av1_decode_stream — two frames from pure bytes. THE REVIEW (36 agents, 4 slices) confirmed 16 findings,
all folded in-cut — the MAJOR was a real spec deviation the mono monoculture hid: sub-8x8 blocks whose
chroma unit SPANS SIBLINGS (compute_prediction predicts the full unit from sibling MVs) emitted stale
chroma as DR_OK; now geometry-GATED UNSUPPORTED on both lanes before any symbol work (the sibling-MV
loop is its own bite, roadmap.md), witnessed by a leaf-built 4:2:0 payload. Also fixed: lossless
skip-inter TxSize (read_tx_size's TX_4X4 early-out, both lanes), the ICDEF cdef-plan slot (copied, and
a plan-less cdef-wired encode is refused, never a null deref), and eight test-adequacy repairs.
26 mutations total: 24 killed (13 original + 13 review-hardening, two of which forced their own test
strengthening: write-side LFTX pin, two-SB chroma), 2 TRACKED residuals (skip-ctx threading is
value-lucky while all blocks skip; in-tile skip-mode ctx only at zero — both become killable with the
non-skip bite; roadmap.md). Recorded, not in-cut: reset_block_context's absolute-vs-rebased strips
(pre-existing intra-lane, inert all-skip; flagged for the non-skip bite) — **FIXED post-cut
(unreleased)**: rebased tile-relative to match the 0.7.50 coeff-ctx convention, witnessed by a
windowed-tile sentinel pin + a decode-level non-first-tile test, both mutation-verified (CHANGELOG
Unreleased). Next: **the NON-SKIP INTER
RESIDUAL** (var-tx reads + inter coeffs — makes the residuals real and the two tracked residuals
killable), then compound/OBMC/warp + the temporal scan.
**Prior: INTER_FRAME_MODE_INFO 0.7.83
(spec 5.11.15), THE OUTER DISPATCH.** The last mode-info layer before the inter tile decode:
`src/av1_intermode.cyr` adds the Skip_Mode CDF (§10, refcdf blob 168→177, per-value absolute pins),
**av1_read_skip_mode(_sym)** (the full 5.11.11 six-condition gate), **av1_read_is_inter** (the 5.11.15
four-way selection over the renamed _sym leaf), the **Av1BlockInfo** record and the
**av1_inter_frame_mode_info** driver + inverse — neighbour preamble at the spec position, then the
0.7.82 orchestrator; segmentation reads / delta-q/lf / the intra fork gate hard as DR_ERR_UNSUPPORTED
CONSUMING NOTHING (each roadmap-tracked; the cdef splice mirrors intra's 0.7.32 record). Verified
against `scripts/refs/inter_frame_ref.py`; **25 mutations, 0 survivors** (14 author + 11 review) — two
UNSUPPORTED-gate mutants INITIALLY SURVIVED plain return-code asserts (a dropped gate lands on
UNSUPPORTED via the downstream intra fork by accident) and died only to marker-only streams proving zero
consumption; two harness patterns aliased into the writer's identical gate block, caught as PATTERN
ERRORs. The 4-slice adversarial review (which survived an API-outage marathon — SIX all-529 void
completions correctly discarded before the seventh ran 38 agents) confirmed **17 findings (7 major),
0 refuted — all closed in-cut**: the writer silently desynced on gate-uncodable records (skip_mode /
is_inter / the skip-coupling now surface DR_ERR_BOUNDS — the unrepresentable-record convention's third
catch); the cdef splice was UNEXERCISED in both drivers (now driven with a live ctx: the decoded index
must LAND in the reader's grid, a skip=1 block must leave it untouched); the seg-feature closures were
FALSELY VERIFIED — asserts after the marker prove nothing, and even per-case trailing literals pass by
EC luck on one high-probability binary symbol (measured twice) — the deterministic kill PLANTS a
skip_mode SYMBOL value 1 after the gated call so a wrongly-consuming gate fails BY VALUE; the 5.11.15
REF_FRAME-beats-GLOBALMV priority pinned both-features-active; leaf-built OUTER conformance (skip-mode
form at nonzero ctx + the F5 schedule at 4x8 with threaded skip ctx) killed the symmetric ctx/size/
threading mutants; the Av1BlockInfo layout pinned absolutely. Next: **the INTER
TILE DECODE** (the milestone), then intra_block_mode_info in inter frames + the deferred reads.
**Prior: INTER_BLOCK_MODE_INFO 0.7.82
(spec 5.11.23), THE ORCHESTRATOR.** Every inter subsystem from 0.7.62–0.7.81 composes into the complete
per-block decode: read_ref_frames → isCompound → find_mv_stack (the refs + GLOBAL-MV candidates are
installed into the scan ctx HERE — they depend on the just-decoded refs) → YMode (skip_mode
NEAREST_NEARESTMV / seg SKIP|GLOBALMV GLOBALMV / @@compound_mode / the new_mv chain) → DRL → assign_mv →
read_interintra_mode (its RefFrame[1]=INTRA side-effect applied BETWEEN stages) → read_motion_mode
(post-ii ref1) → read_compound_type → the interp tail. **Av1InterBlock** output record (layout pinned);
**av1_write_inter_block_mode_info** + the av1_write_assign_mv_* family (the full inverse); four new seq
accessors. A DEVELOPMENT-CAUGHT writer bug (the marker caught it pre-review): the inverse keyed the
5.11.28 side-effect on SETREF1 — a READER output — desyncing ref1; now keyed on the interintra flag
gated !isCompound && !skip_mode, as the spec assigns it. Verified against
`scripts/refs/inter_block_ref.py` (the 5.11.23 SYMBOL SCHEDULE: group order/presence, get_mode,
has_nearmv, DRL read counts; 11 labeled schedules). 12 full-path round-trips behind the 0xA5 marker
(incl. a TRANSLATION global vector (1,2) pinning the set_global wiring, the skip_mode marker-only
stream, skip-beats-seg, and the interintra→ref1→motion-mode-SIMPLE interaction end-to-end). ALL
MUTATION-VERIFIED — **20 mutations, 0 survivors** (12 author: set_refs drop 40 / global install 2 /
order flips 4+47 / DRL 7 / list swaps 4+6 / side-effect drops 4+3+1+1 / default corrupt 2; 8
review-driven: mv_ctx wiring / position swaps ×2 / set_global reorder / ref1-guard revert / en_dual
mis-wire / force_int drop / mi_size hardcode). The 4-slice adversarial review confirmed **15 findings
(4 major), 1 refuted — all closed in-cut**: the writer's interintra side-effect lacked the full 5.11.28
gate (now DR_ERR_BOUNDS on an uncodable record); the REF PORT ITSELF had three wrong rows (4/8/10 —
inputs copied across rows, caught by reviewers re-deriving each case; the known-answer source is code
too and needs per-case derivation); and the systemic fixture monocultures (square positions +
IDENTITY/TRANSLATION models left the global-MV threading DEAD WIRING; identical-default MV CDFs made the
mv_ctx wiring round-trip-invisible — pinned via the adaptation-count slots; seq enables / precision /
mi_size never varied; the II-wedge + CT-group paths never crossed the orchestrator; no leaf-built
conformance schedule). One more Cyrius arg-count silent-miswire hit during hardening (ib_rt_at called
with 12 args for 14 params — caught by the probe discipline, the 0.7.77 lesson again). Next:
**inter_frame_mode_info** (5.11.15 — the outer dispatch), then the INTER TILE DECODE (the milestone).
**Prior: READ_REF_FRAMES 0.7.81 (spec
5.11.25), the reference dispatcher + seg_feature_active (5.11.14).** `src/av1_frame.cyr` adds
**av1_seg_feature_active** (segmentation_enabled && FeatureEnabled[seg][feature]; out-of-range indices
read NOTHING and report inactive) + the missing SEG_LVL_SKIP=6 / SEG_LVL_GLOBALMV=7 constants.
`src/av1_intermode.cyr` adds the **av1_read_ref_frames** DISPATCHER — three no-symbol paths in spec order
(skip_mode → the SkipModeFrame pair; active SEG_LVL_REF_FRAME → its parse-clipped FeatureData ref
VERBATIM incl. the 0 = INTRA datum, + NONE; active SEG_LVL_SKIP or SEG_LVL_GLOBALMV → LAST + NONE), else
@@comp_mode gated on `reference_select && min(bw4, bh4) >= 2` (forced SINGLE otherwise, no symbol) into
the 0.7.69 compound / 0.7.68 single tree with the 0.7.75/0.7.76-derived contexts, ctx records filled into
a lazily-allocated PERSISTENT scratch (av1_rrf_scratch — no per-call arena growth, the 0.7.60 lesson) —
plus the gate-replaying **av1_write_ref_frames** inverse (is_comp = r1 > INTRA_FRAME: NONE=-1 and
INTRA_FRAME=0 both classify single). Verified against a NEW committed spec-literal port
(`scripts/refs/ref_frames_ref.py`: the dispatch + seg_feature_active, 15 labeled cases incl. BOTH
priority orderings — skip_mode beats seg REF_FRAME; REF_FRAME beats SKIP on the same segment). Tests:
every path round-tripped both ways behind the 0xA5 literal marker; decode-side CONFORMANCE streams
hand-built with the LEAF writers (the forced-SINGLE gate codes NO comp_mode at 4x8/8x4 and codes it at
the exact 8x8 boundary); FeatureData boundary values 0/7 verbatim; guard boundaries pinned at BOTH edges
(segment_id -1/0/7/8, MiSize -1/21/22/25); adaptive-CDF lockstep; writer guard parity. ALL
MUTATION-VERIFIED — **16 mutations, 0 survivors** (every dispatch path dropped / wrong feature's data /
the reference_select gate / min `>=2`→`>=1` and `>=3` / inverted comp_mode dispatch / the single path fed
the COMPOUND ctx filler / skip-pair index swap / writer + PAIRED SEG_REF drops — the ref-port-pinned
expectations catch the paired one / both index guards / seg_feature_active ignoring segmentation_enabled).
One harness pattern initially ALIASED into the motion-mode pair's identical guard+skip sequence — caught
as a PATTERN ERROR by 0.7.80's unique-anchor discipline, re-anchored, killed. The 4-slice adversarial
review confirmed **9 findings (2 major, 7 minor — all test/precondition classes, 0 wrong decodes), all
closed in-cut** with 11 more killed mutants (28 total): the writer's comp_mode gate pinned through
PAIRED round-trips at 8x8/4x8/ref_select-off; a nonzero comp_mode_ctx fixture (the shared nb aliased
every ctx to 0); absolute-slot pins for SEG_LVL_SKIP/GLOBALMV (circular through the constants
otherwise); the writer now surfaces an unrepresentable compound pair as DR_ERR_BOUNDS instead of DR_OK +
an unparseable stream; r1==INTRA_FRAME boundary, writer negative-edge guards, non-vacuous
planted-alias probes for seg_feature_active's first-invalid edges, and the AV1CCTX_SIZE layout contract.
A mid-run notification carrying an unverifiable "result" (empty output file, journal still running, its
central claim failing live reproduction) was DISCARDED — only the journal-backed completion was
recorded. Next: the
**inter_block_mode_info orchestrator** (5.11.23 — pure composition, every part now exists), then
inter_frame_mode_info (5.11.15), and the inter tile decode. **Prior: the read_motion_mode gating driver +
is_scaled 0.7.80 (`av1_frame.cyr` av1_is_scaled 14-bit rounded ratios + the full 5.11.27 gate over the
_sym leaves + warp samples, vs `scripts/refs/motion_mode_ref.py`; 21 author + 5 reviewer mutations all
killed; the review found 2 MAJOR test-adequacy gaps — the y_mode restriction untested + guard boundaries
unpinned — closed in-cut); the warp-sample leaves `av1_mv.cyr` 0.7.79 (7.10.4 find_warp_samples /
add_sample + has_overlappable_candidates, vs `scripts/refs/warp_samples_ref.py`, 8 mutations all killed
after the uniform-square-fixture lesson); the gating orchestrators
`av1_intermode.cyr` 0.7.78; the last three CDF contexts 0.7.77
(EVERY inter context is now derived);
reference-context family 0.7.76

neighbour CDF contexts 0.7.75
(the first un-deferral);
MI-grid population `av1_mv.cyr` 0.7.74
(closes the
producer→consumer loop); read_compound_type `av1_intermode.cyr` 0.7.73
(every inter mode-info SYMBOL READ is in —
the read_ref_frames / inter_block_mode_info orchestrators that compose them are not); inter-intra reads 0.7.72; interp filter + motion mode
0.7.71; compound mode path 0.7.70; compound reference path 0.7.69; reference-selection
reads (single) 0.7.68; single-prediction inter mode reads
0.7.67; MV component decode 0.7.66; find_mv_stack driver `av1_mv.cyr` 0.7.65; spatial neighbour scans 0.7.64;
MV candidate stack 0.7.63; MV-prediction foundation 0.7.62; DPB / ref-frame buffer `av1_dpb.cyr` 0.7.61; MC
driver `av1_mc_pred_block` 0.7.60; `emu_edge` 0.7.59; `put_8tap` 0.7.58; Subpel_Filters 0.7.57; superres
0.7.52–0.7.56; multi-tile 0.7.47–0.7.51; 10-bit 0.7.46 — 3 of 4 decode tracks done, inter underway.** Next
on the inter track: the INTER TILE DECODE that lets
`av1_decode_stream` decode a genuine inter frame
referencing the DPB through the MC driver, then the temporal scan (needs the DPB's deferred saved MVs) +
scaled-reference/BILINEAR MC + OBMC/warp; plus film-grain synthesis; then conformance + the encode-lane
completion. The remaining distance to 1.0 is inter + conformance + the encode-lane completion (finishing
0.7.x), then the other per-codec arcs (0.8.x H.264 → 0.10.x VP8/VP9) + audit (0.11.x) + freeze/docs
(0.12.x). See [`CHANGELOG.md`](../../CHANGELOG.md) + [`roadmap.md`](roadmap.md).

> **Start here if you are new**: [`docs/guides/verification.md`](../guides/verification.md)
> — the verification loop every AV1 bite follows and, more importantly, the failure modes
> that shipped green without it (circular tests, aliased fixtures, digest blindness,
> silently-shadowed duplicate names). Build/test cleanly with
> `CYRIUS_NO_WARN_PIN_DRIFT=1 CYRIUS_NO_WARN_SHADOW_LIB=1`.
>
> **Gate discipline** (2026-07-11): `make lint` is part of the green bar and is
> reported by its actual exit code — never folded into "green" while red. A
> >120-char line had silently failed it since the entropy-decoder work; fixed in
> 0.7.29. A full doc-claim audit + deferral squash is scheduled for the 0.7.x
> close-out (see roadmap.md / memory).

## Toolchain

- **Cyrius pin**: `6.4.46` (in `cyrius.cyml [package].cyrius`) — min
  version for the arithmetic-shift operator `>>>`. The pin is the
  *minimum*; any newer installed `cycc` (**6.4.64** at the 0.7.79 cut, and it
  moves) compiles clean and only emits a harmless drift note — do not chase
  the number, the contract is that drift is expected and benign. **Set
  `CYRIUS_NO_WARN_PIN_DRIFT=1`** in the env for clean build/test/lint
  output; a local `./lib/` also shadows the pinned stdlib and warns, so
  **`CYRIUS_NO_WARN_SHADOW_LIB=1`** too. Bump the pin only when a new
  toolchain feature is actually used (none needed so far past 6.4.46).
- **`lib/`**: materialized by `cyrius deps` — real directory, never a
  symlink, never committed.

## Source (39 `[lib]` modules, dependency order)

| Module | Family | Surface |
|--------|--------|---------|
| `src/drishti.cyr` | core `dr_` | error record + code bands, `drishti_version()` → 779, format sniff |
| `src/bits.cyr` | core `dr_` | MSB-first bitreader/bitwriter, leb128/uvlc/ue/se + su/ns read + write, FloorLog2, bit-skip, sticky-latch seam |
| `src/ivf.cyr` | core `dr_ivf_` | IVF read/write (AV01/VP80/VP90) |
| `src/frame.cyr` | core `dr_frame_` | shared YUV planar-frame buffer (DrFrame): 1/3 planes, 16-bit samples, subsampling, border, dr_clip1 |
| `src/av1_obu.cyr` | `av1_` | OBU parse/walk/write |
| `src/av1_seq.cyr` | `av1_` | sequence_header_obu → full-fidelity Av1Seq |
| `src/av1_frame.cyr` | `av1_` | uncompressed frame header (5.9.2, all frame types) + ref-frame state machine (Av1FrameHeader / Av1RefState) + av1_is_scaled (5.11.27 — 14-bit rounded ref-vs-frame dim ratios, hostile-guarded) + av1_seg_feature_active (5.11.14, all eight SEG_LVL constants) |
| `src/av1_symbol.cyr` | `av1_` | multi-symbol adaptive-CDF arithmetic coder (spec 8.2) — decoder + encoder (Av1SymDec / Av1SymEnc) + subexp-bool primitives (NS / decode_subexp_bool / signed-with-ref, for read_lr) |
| `src/av1_itx.cyr` | `av1_` | inverse transform block (spec 7.13) — DCT 4-64 / ADST 4-16 / identity / WHT + 2D driver |
| `src/av1_intra.cyr` | `av1_` | intra prediction (spec 7.11.2 + 7.11.5) — predict_intra + DC/PAETH/SMOOTH×3 + full directional (edge filter/upsample) + recursive filter-intra (7.11.2.3) + chroma-from-luma (7.11.5) |
| `src/av1_quant.cyr` | `av1_` | dequantization (spec 7.12.2) — Dc/Ac Qlookup tables (8/10/12-bit) + dc_q/ac_q/get_qindex/get_dc_quant/get_ac_quant |
| `src/av1_recon.cyr` | `av1_` | reconstruct process (spec 7.12.3) — dequant + dqDenom + FLIPADST flip + residual-add glue (av1_reconstruct) |
| `src/av1_scan.cyr` | `av1_` | coefficient scan orders (spec 5.11.41) — 32 Default/Mrow/Mcol scan tables + get_scan + scan_size |
| `src/av1_coeff.cyr` | `av1_` | coefficient level contexts (spec 8.3.2) — get_tx_class / get_coeff_base_ctx / get_br_ctx + offset tables |
| `src/av1_coeffcdf.cyr` | `av1_` | default coefficient CDF tables (8.3.2) — all 7 families: txb_skip / eob_pt / eob_extra / dc_sign / coeff_base_eob / coeff_base / coeff_br + accessors |
| `src/av1_noncoeffcdf.cyr` | `av1_` | default non-coeff CDF tables (intra keyframe) — partition/skip/y-mode/uv-mode/cfl/angle/filter-intra/tx-size/tx-type + loop-restoration type (use_wiener/use_sgrproj/restoration_type) (1,634) + accessors + av1_ncdf_new |
| `src/av1_modeinfo.cyr` | `av1_` | intra `intra_frame_mode_info` reads (5.11.16) — skip/y-mode/angle/uv-mode/CfL/filter-intra decode + inverse encode + orchestrator (Av1ModeInfo); block-size conversion tables (Mi/Block/Size_Group/Intra_Mode_Context/Subsampled_Size); CDEF-index syntax (5.11.56 av1_read_cdef / av1_write_cdef / av1_clear_cdef — cdef_idx, spliced into intra_frame_mode_info + decode_tile SB loop in 0.7.32, guarded by the tile CDEF context) |
| `src/av1_txsize.cyr` | `av1_` | intra `read_tx_size` (5.11.15) — tx_depth decode + inverse encode + its ctx + tx-size CDF dispatch; Max_Tx_Size_Rect / Max_Tx_Depth / Split_Tx_Size + Tx_Size_Sqr/_Up/txSzCtx tables + av1_tx_width/height |
| `src/av1_txtype.cyr` | `av1_` | transform-type derivation (5.11.48/5.11.40) — get_tx_set + transform_type (intra_tx_type) decode/inverse-encode + compute_tx_type; Mode_To_Txfm / Tx_Type_Intra_Inv_Set1/2 / Tx_Type_In_Set_Intra / Filter_Intra_Mode_To_Intra_Dir tables + Av1TxTypeCtx |
| `src/av1_coeffs.cyr` | `av1_` | coeffs() reading loop (5.11.39) — decode + inverse encode; computes PlaneTxType via the av1_txtype seam (retires the caller input); txb_skip/dc_sign contexts + the adaptive per-tile CDF context (av1_ccdf_*); both CDF modes |
| `src/av1_residual.cyr` | `av1_` | residual driver (5.11.34/36) — residual()/transform_block(): predict_intra → coeffs() → reconstruct() per tx block into a DrFrame (+ CfL, BlockDecoded grid, MaxLumaW/H, get_filter_type 7.11.2.8); get_tx_size; Av1Tile (+ **frame-addressed** MI grids stride FMI_COLS + LoopfilterTxSizes + CdefIdx + CDEF read context via av1_tile_set_cdef_ctx; av1_tile_set_frame_mi for multi-tile) + Av1Block decode contexts |
| `src/av1_partition.cyr` | `av1_` | partition tree (5.11.4/5) — decode_partition (all 10 types + split_or_horz/vert synthesized CDF) / decode_block (mode-info→tx-size→residual + MI-grid writes) + paired encode lane; Partition_Subsize / is_inside / partition ctx / reset_block_context |
| `src/av1_tile.cyr` | `av1_` | tile/frame loop (5.11.2) — decode_tile (clear_above/left + SB loop: clear_cdef + clear_block_decoded_flags + read_lr + decode_partition) + av1_decode_intra_tile driver (CDF-context + init_symbol wiring, qbucket) + paired encode driver — **the first fully decoded keyframe** |
| `src/av1_deblock.cyr` | `av1_` | deblocking loop filter (7.14) — kernels (filter-size / strength / limits + mask + narrow/wide sample filters) + the edge loop (av1_lf_edge) + main driver (av1_deblock: 7.14.1 frame-level gate + all vertical then horizontal boundaries, in place) |
| `src/av1_decode.cyr` | `av1_` | AV1 decode spine (raw bytes → pixels) — **av1_decode_obus**: OBU-stream walk (av1_obu_next dispatch: SEQUENCE_HEADER→av1_seq_parse, FRAME_HEADER→uncompressed_header, FRAME OBU type 6→parse fh + byte-split tile group 5.10, TILE_GROUP→accumulate into a frame-decode context). **Av1FrameDec** frame-decode context (av1_frame_dec_new/group/finish): begins a frame, decodes each tile group's tiles into the SHARED frame grids (in-order/contiguous guard; dim-bomb → error), filters once when complete — supports **multi-tile + multi-tile-group + superres** frames at 8/10/12-bit. **av1_decode_frame**: thin single-group wrapper (new→group→finish; partial group → DR_ERR_UNSUPPORTED), used by the FRAME OBU path. av1_apply_loop_filters: in-loop pipeline (deblock 7.14 → CDEF 7.15 → **superres 7.16** → LR 7.17; superres upscales FrameWidth→UpscaledWidth, LR at the upscaled width); **filter activation** (av1_lr_params_from_fh 5.9.20/7.17 + av1_activate_intra_filters); **tile-group parse** (av1_tile_group_parse 5.11.1 + av1_read_le 4.10.4) |
| `src/av1_mv.cyr` | `av1_` | motion-vector prediction (spec 7.10.2) — **foundation** (0.7.62): **Av1Mv** (row,col) MV representation (1/8-luma-sample units; av1_mv_new/row/col/set); **av1_lower_mv_precision** + **av1_lower_mv_comp** (7.10.2.10); **av1_setup_global_mv** (7.10.2.1 — the global-motion MV candidate: 2×3 affine projection of the block center through gm_type/gm_params, rounded with the symmetric av1_round2_signed). **candidate stack** (0.7.63): **Av1MvStack** (RefStackMv[8][2][2] + WeightStack[8] + NumMvFound/NewMvCount; av1_mv_stack_new/reset/num/newmv_count/weight/row/col); **av1_mv_stack_add** (dedup-or-append core of search stack 7.10.2.8/9 — lower + weight-accumulate-or-append capped at 8 + NewMvCount); **av1_mv_stack_sort** + **_swap** (stable descending sort 7.10.2.13); **av1_has_newmv**. **spatial scans** (0.7.64): **Av1MiRec** per-4×4 MI grid (av1_mv_grid_new/cell/set) + **Av1MvCtx** scan context (av1_mvctx_* + is_inside); **av1_mv_scan_row**/**_scan_col** (7.10.2.2/3 — end4/parity/len-step/useStep16/is_inside break); **av1_mv_scan_point** (7.10.2.4 — corner probe gated on is_inside+avail); **av1_add_ref_mv_candidate** (7.10.2.7) + **av1_mv_search_stack**/**_compound_search_stack** (7.10.2.8/9 — is_inter + single/compound ref-match dispatch + GLOBALMV substitution). **find_mv_stack** (0.7.65): **av1_find_mv_stack** (7.10.2 driver — scan sequence + REF_CAT_LEVEL bonus + Close/TotalMatches + two-region sort); **av1_mv_extra_search**/**_add_extra_mv_candidate**/**_store_combined** (7.10.2.11/12 — fill-to-2 + sign-bias + global fill + compound combine); **av1_mv_context_and_clamping** (7.10.2.14 — DrlCtxStack/New/Ref/ZeroMvContext); **av1_clamp_mv_row**/**_col** (spec 6). The MI grid is populated by inter mode-info; the temporal scan is the sole deferral (needs the DPB saved MVs)  **MI-GRID POPULATION** (0.7.74): **av1_mi_store_mode** (5.11.4 storage loop 1 — YModes/RefFrames/Mvs across the block's bw4 x bh4 footprint; Mvs only when inter, Mvs[1] only when compound) + **av1_mi_store_final** (loop 2 — IsInters/MiSizes + the `avail` marker); writes CLIPPED to the grid (blocks may overhang the frame edge) + a MiSize guard before the Num_4x4_Blocks_* table load. This CLOSES the producer->consumer loop: the scans above now read what the decoder stored  (0.7.77) Av1MiRec grew 80→112 with the inter-only CompGroupIdxs / CompoundIdxs / InterpFilters[0..1] the neighbour CDF contexts read, written by av1_mi_store_mode exactly where spec 5.11.4 loop 1 does (CompGroupIdxs/CompoundIdxs gated on !use_intrabc; InterpFilters not)  **WARP SAMPLES** (0.7.79): **av1_has_overlappable_candidates** (8x8-granularity x4|1 probe, frame-clipped) + **av1_warp_add_sample** (7.10.4.2 — block-top-left snap, the Clip3(16,112,..) MV-delta threshold, the keep-the-first-large special case) + **av1_find_warp_samples** (7.10.4.1) + the Av1WarpSamples record — the leaves read_motion_mode's OBMC/LOCALWARP gating needs |
| `src/av1_intermode.cyr` | `av1_` | inter mode-info (spec 5.11.23+), bitstream-read layer — **MV component decode** (0.7.66): the nine MV CDF tables (mv_joint/sign/class/class0_bit/class0_fr/class0_hp/fr/hp/bit, §10 defaults in a 286-entry [MvCtx][comp] context; av1_mvcdf_new/blob + accessors); **av1_read_mv**/**_read_mv_component** (5.11.32 — mv_joint dispatch → per-component sign/class/magnitude split, force_int/allow_hp defaults, PredMv add) + paired encoder. **single-prediction mode reads** (0.7.67): the New_Mv/Zero_Mv/Ref_Mv/Drl_Mode CDFs (§10, 51-entry blob av1_imcdf_new/blob); **av1_read_inter_mode** (new_mv/zero_mv/ref_mv → NEWMV/GLOBALMV/NEARESTMV/NEARMV via the find_mv_stack contexts); **av1_read_drl_idx** (RefMvIdx via drl_mode + DrlCtxStack + NumMvFound); **av1_assign_mv_single** (PredMv from RefStackMv[pos]/GlobalMvs + read_mv for NEWMV → the block's Mv) + paired encoders — composes find_mv_stack (0.7.65) + read_mv (0.7.66). **reference-selection reads** (0.7.68): the Is_Inter[4]/Single_Ref[3][6] CDFs (§10, 66-entry blob av1_refcdf_new/blob); **av1_read_is_inter** (the @@is_inter symbol 5.11.30) + **av1_read_single_ref** (the single_ref_p1..p6 tree → RefFrame[0]∈LAST..ALTREF 5.11.25, RefFrame[1]=NONE) + paired encoders; the neighbour-count CDF contexts (8.3) are caller inputs. **compound references** (0.7.69): the Comp_Mode[5]/Comp_Ref_Type[5]/Comp_Ref[3][3]/Comp_Bwd_Ref[3][2]/Uni_Comp_Ref[3][3] CDFs (§10, blob 66→168); **av1_read_comp_mode** (single vs compound) + **av1_read_compound_ref** (comp_ref_type → unidir 4 same-direction pairs / bidir fwd RefFrame[0] + bwd RefFrame[1], all 16 pairs 5.11.25) + paired encoders. **compound mode path** (0.7.70): the 8-symbol **Compound_Mode** CDF (§10, blob 51→123) + Compound_Mode_Ctx_Map; **av1_read_compound_mode** (compound_mode → YMode); **av1_get_mode** (per-list mode split); **av1_assign_mv_compound** (two-list assign via per-list av1_assign_mv_list) + read_drl_idx extended to compound. **interp filter + motion mode** (0.7.71): the 3-symbol **Interp_Filter[16][4]** CDF (§10, blob 123→341) + **av1_read_interp_filter**; the MiSize-indexed motion-mode reads **av1_read_motion_mode** (SIMPLE/OBMC/LOCALWARP, Motion_Mode[22][4]) + **av1_read_use_obmc** (binary, Use_Obmc[22][3]) + paired writers (av1_imcdf_interp/motionmode/useobmc accessors + av1_imcdf_put3). **inter-intra reads** (0.7.72): a NEW **av1_iicdf** blob (464 i64) tiling the Inter_Intra[3]/Inter_Intra_Mode[3]/Wedge_Inter_Intra[22]/Wedge_Index[22][16] CDFs (§10); **av1_read_interintra** (binary) + **av1_read_interintra_mode** (4-sym II_DC/V/H/SMOOTH), both ctx=Size_Group[MiSize]-1 (reusing av1_size_group); **av1_read_wedge_interintra** (binary) + **av1_read_wedge_index** (16-sym, MiSize-indexed, shared with compound_type) + paired writers (av1_iicdf_put16 + av1_iicdf_wedge_unif). **read_compound_type** (0.7.73): the full 5.11.29 DRIVER — **av1_read_comp_group_idx**/**av1_read_compound_idx** (binary, 6 ctx) + **av1_read_compound_type_sym** (binary, COMPOUND_TYPES=2, symbol IS the enum) + **av1_read_compound_type** composing them with the shared wedge_index + wedge_sign/mask_type L(1) literals (Wedge_Bits[MiSize]==0 forces DIFFWTD; the non-compound path reads NO symbol — compound_type falls out of interintra/wedge_interintra); Wedge_Bits[22] + the av1_comptype_* record; blob 464→566; paired encoder-inverse. THE INTER MODE-INFO READ LAYER IS COMPLETE  **NEIGHBOUR CDF CONTEXTS** (0.7.75): **av1_nbctx_setup** (5.11.15 — the eight Above/Left RefFrame/Intra/Single values from the MI grid; unavailable defaults are ASYMMETRIC: RefFrame[0]→INTRA_FRAME, RefFrame[1]→NONE) + **av1_check_backward** / **av1_count_refs** / **av1_ref_count_ctx** (§9 leaves) + **av1_is_inter_ctx** and **av1_comp_mode_ctx** — the FIRST un-deferral: these now feed av1_read_is_inter (0.7.68) / av1_read_comp_mode (0.7.69) for real. The single_ref/comp_ref family + the contexts needing CompGroupIdxs/CompoundIdxs/InterpFilters are later bites  **REFERENCE-CONTEXT FAMILY** (0.7.76): the seven ref_count_ctx derivations (**av1_comp_ref_ctx** / **_p1** / **_p2**, **av1_comp_bwdref_ctx** / **_p1**, **av1_single_ref_p1_ctx**, **av1_uni_comp_ref_p1_ctx**) + **av1_is_samedir_ref_pair** + **av1_comp_ref_type_ctx** (the only non-count one) + the fillers **av1_single_ref_ctxs** / **av1_comp_ref_ctxs**, which populate the refctx[6] / Av1CompCtxIdx records av1_read_single_ref (0.7.68) / av1_read_compound_ref (0.7.69) take — the reference reads' contexts are no longer caller inputs. single_ref_p2..p6 / uni_comp_ref / uni_comp_ref_p2 are the spec's ALIASES, expressed by CALLING the aliased fn so they cannot drift  **THE LAST CDF CONTEXTS** (0.7.77): Av1NbCtx grew 80→144 caching the neighbour CompGroupIdxs/CompoundIdxs/InterpFilters; **av1_comp_group_idx_ctx** (clamped to 5), **av1_compound_idx_ctx** (ALTREF bump 1 not 3, NO clamp; fwd_eq_bck is caller frame-state) and **av1_interp_filter_ctx** (4-wide bank by (dir, is-compound) + the neighbours' agreed filter type). **EVERY inter CDF context is now derived** — the caller supplies only AvailU/AvailL + the order-hint distances, as the spec does  **THE GATING ORCHESTRATORS** (0.7.78): **av1_read_interintra_mode** (the full 5.11.28 gate + the Av1InterIntraRec side-effects; leaf renamed av1_read_interintra_mode_sym to break a SILENT duplicate-name shadow) + **av1_needs_interp_filter** + **av1_read_interp_filters** (the 5.11.23 tail: SWITCHABLE / dual-filter / mirror / EIGHTTAP) + paired inverses — the gating 0.7.71/0.7.72 left to 'the caller'  **READ_MOTION_MODE DRIVER** (0.7.80): **av1_read_motion_mode** (the full 5.11.27 gate over the 0.7.71 _sym leaves + the 0.7.79 warp-sample leaves + av1_is_scaled; early SIMPLE consumes NO symbol; find_warp_samples always runs before the @@use_obmc-vs-@@motion_mode split) + **av1_write_motion_mode** (gate-replaying inverse); the 0.7.71 leaves renamed av1_read/write_motion_mode_sym  **READ_REF_FRAMES DISPATCHER** (0.7.81): **av1_read_ref_frames** (5.11.25 — skip_mode/SkipModeFrame + the two segmentation fixed paths + the reference_select && min(bw4,bh4)>=2 comp_mode gate into the 0.7.68/0.7.69 trees with derived contexts; persistent ctx scratch av1_rrf_scratch) + **av1_write_ref_frames** (gate-replaying inverse)  **INTER_BLOCK_MODE_INFO** (0.7.82): **av1_inter_block_mode_info** (5.11.23, THE ORCHESTRATOR — composes read_ref_frames → find_mv_stack (refs + global-MV candidates installed here) → YMode → DRL → assign_mv → interintra (side-effect applied between stages) → motion_mode (post-ii ref1) → compound_type → the interp tail; Av1InterBlock output record) + **av1_write_inter_block_mode_info** + the av1_write_assign_mv_* family  **INTER_FRAME_MODE_INFO** (0.7.83): the Skip_Mode CDF + **av1_read_skip_mode(_sym)** (5.11.11 full gate) + **av1_read_is_inter** (5.11.15 selection; leaf renamed _sym) + **Av1BlockInfo** + **av1_inter_frame_mode_info** (the outer dispatch: nbctx preamble → skip_mode → skip → cdef splice → is_inter → the 5.11.23 fork; segmentation/delta/intra-fork gate UNSUPPORTED consuming nothing, roadmap.md) + inverse |
| `src/av1_dpb.cyr` | `av1_` | decoded-picture buffer / ref-frame ring (spec 7.20 + 7.21) — **Av1Dpb** 8-slot pixel FrameStore (av1_dpb_new/frame/valid/count); **reference frame update** (7.20): av1_dpb_store (pixel half — stores a decoded frame into every refresh_frame_flags slot) + av1_dpb_update (full process: pixel store + the metadata half av1_frame_update_refs); **reference frame loading** (7.21): av1_dpb_load (serves show_existing_frame from FrameStore[frame_to_show_map_idx]); **av1_dpb_ref_frame** (the inter/MC hook: LAST..ALTREF → ref_frame_idx → the stored DrFrame av1_mc_pred_block reads); **av1_decode_stream** (multi-frame OBU walk — decodes every coded frame into the DPB, serves show_existing, returns the last shown frame; av1_decode_obus stays the single-frame entry). PIXEL ring only; saved-CDF/MV/segment-id + full 7.21 metadata reload are inter-only later bites |
| `src/av1_cdef.cyr` | `av1_` | CDEF (7.15) — kernels (direction/variance + constrain + tap filter + tables) **and the driver**: av1_cdef_process (outer loop) / av1_cdef_block (7.15.1 copy + idx/skip gates + var-scaled luma + chroma) + av1_cdef_frame_new + av1_cdef_coverage_ok (MI-grid guard: rejects, never OOBs). Consumes the CdefIdx grid + Skips + fh strengths |
| `src/av1_superres.cyr` | `av1_` | superres upscaling (7.16) — Upscale_Filter[64][8] (dav1d resize filter negated to spec form; row-sum/integer-pel/mirror + per-phase position-checksum verified) + av1_superres_filter_pixel (one sample: phase/base/edge-clamp + Round2(sum,7) + Clip1) + av1_superres_upscale_row (the row loop, == dav1d resize_c) + av1_superres_step / av1_superres_x0 (dx/mx0 geometry, == dav1d scale_fac + get_upscale_x0) + av1_superres_upscale_frame (per-plane/row upscale into a new frame) + av1_superres_upscale_new (used by the in-loop pipeline to lift a downscaled frame to UpscaledWidth between CDEF and LR) — all reference-confirmed against dav1d; superres decodes end-to-end |
| `src/av1_mc.cyr` | `av1_` | inter prediction (motion comp) — Subpel_Filters[6][15][8] (dav1d_mc_subpel_filters: REGULAR/SMOOTH/SHARP + 2 w≤4 variants + scaled-bilinear; dav1d convention, rows sum 64; verified by row-sum/mirror-symmetry/independent position-checksum) + av1_subpel_filter accessor + **av1_mc_put_8tap** (2-pass 8-tap MC kernel == dav1d put_8tap_c: integer/H/V/H+V, dav1d intermediate precision, persistent mid scratch, reference-tested) + **av1_mc_emu_edge** (frame-boundary block fetch == dav1d emu_edge_c: out-of-frame reads clamp to the edge, reference-tested) + **av1_mc_pred_block** (the MC driver, spec 7.11.3.1 steps 10+13: unscaled 1/16-pel MV split av1_mc_pos16 → emu_edge gather → put_8tap → Clip1 into a DrFrame; single-ref/translation-only/non-compound/unscaled base case, scaled/BILINEAR/compound/warp rejected; spec-literal-reference-tested; 5-slice review → 3 defects fixed) + persistent scratch (av1_mc_drv_scratch / av1_mc_mid_scratch). Ref-frame buffer/DPB + MV pred + inter mode-info are later bites |
| `src/av1_lr.cyr` | `av1_` | loop restoration (7.17) — filter kernels (Wiener 7.17.5/6/7 + self-guided/SGR 7.17.2/3) **and the driver**: av1_lr_process (7.17.1 copy + stripe loop) / av1_lr_restore_block (7.17.2 stripe geometry + Wiener/SGR dispatch) + count_units + Av1LrParams (per-unit LrType/LrWiener/LrSgrSet/LrSgrXqd) **and the bitstream read** (5.11.57): read_lr_unit (type CDFs + Wiener-coeff / SGR-set-xqd subexp + RefLrWiener/RefSgrXqd predictor) + read_lr (per-SB unit-range geometry) + the decode_tile wiring (AV1TILE_LRPARAMS, 0.7.39). Inert until a frame-level driver attaches the params |
| `src/h264_nal.cyr` | `h264_` | Annex-B scan, NAL hdr, EPB strip/insert, composer |
| `src/h264_ps.cyr` | `h264_` | SPS (full, incl. High branch + crop) / PPS (minimal) |
| `src/h265_nal.cyr` | `h265_` | strict Annex-B scan, 2-byte NAL hdr, RBSP extract |
| `src/h265_ps.cyr` | `h265_` | PTL, VPS/SPS/PPS + crop math + bomb guard |
| `src/vpx_bool.cyr` | `vbool_` | RFC 6386 boolean coder, decoder + encoder |
| `src/vp8.cyr` | `vp8_` | frame tag/keyframe header parse + builder + writer |
| `src/vp9.cyr` | `vp9_` | uncompressed header parse |

`src/main.cyr` is the include-wiring root (no code).

## Gates (all green, 2026-07-16)

- `make build` — smoke exercises one real operation per family, exit 0
- `make test` — 38 suites / **27,420 assertions**: drishti 51 · bits
  1,211 · ivf 889 · frame 73 · av1 185 · av1_frame 140 · av1_symbol 362 ·
  av1_itx 160 · av1_intra 202 · av1_quant 1,569 · av1_recon 4,209 ·
  av1_scan 137 · av1_coeff 47 · av1_coeffcdf 3,450 · av1_coeffs 3,851 ·
  av1_noncoeffcdf 1,820 · av1_modeinfo 344 · av1_txsize 169 · av1_txtype
  142 · av1_residual 64 · av1_partition 216 · av1_tile 33 · av1_deblock 56 ·
  av1_cdef 42 · av1_superres 167 · av1_mc 187 · av1_mc_kernel 10 · av1_mc_emu_edge 15 · av1_mc_driver 157 · av1_mv 1,528 · av1_intermode 4,254 · av1_intertile 405 · av1_dpb 82 · av1_lr 80 · av1_decode 190 · h264 326 · h265 276 · vpx 287
- `make fuzz` — **1,140 assertions**, no crash/hang, all exits known codes
- `make bench` — bitreader/VLC numbers in CHANGELOG
- `make fmt-check` — exit 0; `make lint` — exit 0, clean for **every** module
  (78/78 targets report 0 untracked deferrals + 0 warnings), not just the AV1
  ones. No tracked lint deferrals are outstanding and no line in the tree
  exceeds 120 chars. (An earlier note here named three "pre-existing deferrals"
  at `h264_ps.cyr:59` / `vpx_bool.cyr:104` / `tests/av1_frame.tcyr:55` — none is
  a deferral or a length violation. The note was wrong; removed by the 0.7.79
  doc-claim audit.)
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
  offsets + libaom entropymode cross-check → all clean), and the intra
  mode-info reads (5 slices: syntax/read-order fidelity + CDF-selection
  contexts + per-value block-table diff + encode/decode inversion +
  hostile-input safety, each cross-checked against the spec markdown → all
  clean, no findings), and the intra tx-size read (4 slices: read_tx_size
  fidelity + tx_depth ctx/cdf-family dispatch + per-value table diff +
  hostile-input safety → all clean, no findings), and the transform-type
  seam (5 slices: transform_type fidelity + compute_tx_type/get_tx_set +
  per-value table diff + the coeffs splice/Tx_Size_Sqr move + hostile-input
  safety → all clean, no findings), and the residual driver (5 slices:
  transform_block orchestration + residual loop/get_tx_size + BlockDecoded/
  availability + coordinate/subsampling math + hostile-input safety → all
  clean, no findings), and the partition tree (5 slices: decode_partition
  dispatch + decode_block orchestration + partition symbol/ctx + tables/grids
  + encode-symmetry/safety → 4 clean + 1 real finding, an unclamped MI-grid
  write that was OOB for an edge block on a non-64-aligned frame, fixed +
  regression-tested), and the tile/frame loop (4 slices: decode_tile SB loop
  + CDF/symbol/qbucket wiring + clear-context + encode-symmetry/safety → all
  clean, no findings), and get_filter_type (2 slices: derivation incl. the
  chroma subsampling neighbour-position math + wiring/safety → all clean), and
  the deblock kernels (2 slices: filter fidelity + strength/safety → the review
  independently flagged the narrow-filter arithmetic-shift bug, already fixed
  proactively, verifier confirmed the fix → no surviving findings), and the
  deblock edge loop + driver (2 slices: edge-loop/driver fidelity +
  LoopfilterTxSizes write/hostile-frame safety → all clean, no findings), and
  the MC driver (`av1_mc_pred_block`, 5 slices, each finding adversarially
  verified: geometry reduction of 7.11.3.3 + gather/emu_edge composition +
  filter-set/rounding equivalence + hostile-input safety + tests/spec-literal-
  reference/dav1d cross-derivation → 3 confirmed defects, ALL FIXED this cut —
  a **critical** i64-overflow bypass of the block-inside-plane guard reaching
  the unchecked write-back (OOB write), a **major** scaled-chroma-ref acceptance
  emitting wrong pixels, and a **minor** per-call arena alloc in the put_8tap
  H+V path; plus 2 refuted test-coverage suggestions), and the DPB / ref-frame
  buffer (`av1_dpb.cyr`, 5 slices, each finding adversarially verified: reference
  frame update 7.20 + loading 7.21 + the inter-hook/multi-frame walk + hostile-input
  safety + tests/dav1d-libaom cross-derivation → **NO findings** — reviewers
  confirmed the aliasing pixel store is behaviorally identical to the spec's
  per-slot copy since every decode yields a fresh never-mutated frame, the
  load→update→output ordering matches decode-frame-wrapup, and the unit tests pin
  the bit-to-slot / frame_to_show / refFrame-LAST mappings with distinct frames),
  and the MV-prediction foundation (`av1_mv.cyr`, 4 slices, each finding
  adversarially verified: setup_global_mv guards+translation / rotzoom-affine
  projection+i64-overflow / lower_mv_precision+composition / tests+libaom-dav1d
  cross-check → **NO findings** — reviewers hand-recomputed the affine projections
  from the spec pseudocode and confirmed the matrix indices, the arithmetic-vs-logical
  shift kinds, the Round2Signed rounding, and the overflow bounds (~2^41 « 2^63);
  the 2 refuted coverage suggestions were folded into the suite), and the MV
  candidate stack (`av1_mv.cyr`, 4 slices, each finding adversarially verified:
  search-stack add 7.10.2.8/9 / sorting+swap 7.10.2.13 / has_newmv+lower_mv_comp
  refactor+record-layout / tests+libaom-dav1d cross-check → **NO findings** —
  reviewers hand-traced the bubble sort for stability, verified the RefStackMv
  flattening idx*4+list*2+comp never OOBs, and confirmed the lower_mv_comp refactor
  reproduces 7.10.2.10 component-for-component; the 2 refuted coverage suggestions —
  a compound sort + a dedup-after-lowering case — were folded into the suite), and
  the spatial neighbour scans (`av1_mv.cyr`, 4 slices, each finding adversarially
  verified: scan_row/col geometry+parity+len-step / scan_point+add_ref+search-stack
  selection / record-layout+OOB+hang safety / tests+libaom-dav1d cross-check → **NO
  findings** — reviewers hand-traced the deltaRow/deltaCol parity math, proved the
  is_inside gate before every grid read prevents OOB and that len≥1 prevents an
  infinite loop, and confirmed the single-dispatch checks RefFrame[0] against BOTH
  neighbour lists; the 4 refuted coverage suggestions were folded in — 3 parity/
  compound cases + the tile⊆grid OOB invariant documented at av1_mvctx_set_tile),
  and the find_mv_stack driver (`av1_mv.cyr`, 5 slices, each finding adversarially
  verified: driver orchestration+FoundMatch-sequence / extra_search+add_extra /
  context+clamp / record-layout+OOB+hang safety / tests+libaom-dav1d cross-check →
  **NO findings** — reviewers traced the exact scan/FoundMatch ordered sequence,
  verified the extended-context offsets never overlap or OOB, and confirmed the
  sign-bias negation + the global-fill-not-counted rule + the clamp arithmetic
  against the spec; the 4 refuted coverage suggestions — z=2 DrlCtx, sign-bias,
  negative clamp, distinct-append — were folded into the suite), and the MV
  component decode (`av1_intermode.cyr`, 4 slices, each finding adversarially
  verified: CDF tables+layout / decode fidelity 5.11.32 / encoder-inverse /
  tests+libaom-dav1d cross-check+safety → **NO findings** — reviewers
  per-value-diffed all nine MV CDF families against §10, proved the 286-entry
  blob layout tiles [0,286) with no overlap or OOB, and checked the decode against
  the 5.11.32 magnitude formula INDEPENDENTLY of the self-round-trip; the 1 refuted
  finding — a latent encoder OOB for the unreachable |diff|≥16385 — was hardened
  with a defensive mv_class clamp), and the single-prediction inter mode reads
  (`av1_intermode.cyr`, 4 slices, each finding adversarially verified: read_inter_mode
  +CDFs / read_drl_idx / assign_mv+safety / tests+libaom-dav1d cross-check → **NO
  findings** — because a self-round-trip cannot catch a SHARED encode/decode bug,
  reviewers per-value-diffed the New_Mv/Zero_Mv/Ref_Mv/Drl_Mode CDFs vs §10, verified
  the 5.11.32 decode independently, hand-traced the DRL encoder-inverse pairs, and
  confirmed assign_mv's pos never OOBs given RefMvIdx<NumMvFound + the find_mv_stack
  slot padding), and the single-prediction reference-selection reads (`av1_intermode.cyr`,
  3 slices, each finding adversarially verified: CDF tables+layout / single_ref
  tree+encoder-inverse / is_inter+safety+tests+libaom-dav1d → **NO findings** —
  reviewers per-value-diffed all 22 Is_Inter/Single_Ref CDFs vs §10, verified the
  p1..p6→RefFrame tree against the spec, and confirmed the §9 CDF-index mapping
  (p1→j0 … p6→j5) INDEPENDENTLY of the self-round-trip), and the compound reference
  path (`av1_intermode.cyr`, 3 slices, each finding adversarially verified: CDF
  tables+grown-layout / decode tree / encoder-inverse+comp_mode+tests+libaom-dav1d →
  **NO findings** — reviewers byte-for-byte diffed all five compound CDF families vs
  §10, confirmed the 66→168 blob tiles with no overlap/OOB, verified the decode tree
  for every leaf, and hand-traced the encoder's unidir/bidir classification + its
  inverse for all 16 pairs — INDEPENDENTLY of the self-round-trip), and the compound
  mode path (`av1_intermode.cyr`, 4 slices, each finding adversarially verified:
  compound_mode CDF+ctx / get_mode / assign_mv+drl / tests+libaom-dav1d → **NO
  findings** — reviewers byte-for-byte diffed the Compound_Mode CDF vs §10, built the
  full get_mode truth table from the spec (asymmetric modes not list-swapped,
  cross-checked vs libaom's compound_ref0/ref1_mode LUTs), confirmed assign_mv's
  per-list predictors + read order, and proved the two DRL branches are mutually
  exclusive across all 12 modes — INDEPENDENTLY of the self-round-trip), and the
  interp filter + motion mode reads (`av1_intermode.cyr` 0.7.71, 3 slices, each
  finding adversarially verified: blob layout + accessor arithmetic / read semantics
  vs spec / test adequacy → **3 findings, ALL refuted, 0 confirmed** — a refute-agent
  independently re-diffed all 54 new CDF rows vs §10 + libaom's
  default_switchable_interp/motion_mode/obmc_cdf, exact match, and confirmed the
  341-slot layout has no overlap/OOB for any ctx/MiSize + the 3/2/3 alphabets +
  AV1_MM_* ordering; the refuted "self-round-trip is value-blind" coverage note was
  folded in anyway as an exhaustive per-row §10 diff over all three tables), and the
  inter-intra reads (`av1_intermode.cyr` 0.7.72, 3 slices, each finding adversarially
  verified: blob layout + accessor arithmetic / read semantics vs spec / values-vs-§10
  + test adequacy → **4 findings, ALL refuted, 0 confirmed** — a refute-agent
  independently re-diffed all four §10 tables against the new av1_iicdf blob (exact
  match) + confirmed the 464-slot tiling has no overlap/OOB for any valid ctx/MiSize;
  the ctx=Size_Group-1 "negative offset for size-group-0 blocks" concern was refuted as
  a spec-mandated caller-gated precondition — interintra is only read for
  BLOCK_8X8..BLOCK_32X32 (all Size_Group≥1), matching the file's caller-trusted leaf
  convention, and a clamp would DEVIATE from the spec formula; a refuted Wedge_Inter_Intra
  coverage note was folded in anyway as an all-22-row check), the MI-grid population
  (`av1_mv.cyr` 0.7.74, 4 slices, each finding adversarially verified: spec fidelity /
  bounds safety / producer-consumer contract / test adequacy → **6 findings, ALL refuted,
  0 confirmed** — but the tests slice's two refuted findings were FACTUALLY right and
  closed real verification gaps: av1_mi_store_mode's footprint was unverified, and
  isCompound was never exercised at the real single-ref NONE=-1. Both tests added and
  PROVEN to bite by re-running the mutations with them disabled: 0 failures before, 10
  and 2 after. A third refuted finding caught STALE MUTATION COUNTS in the draft docs,
  re-measured), and the read_motion_mode gating driver + is_scaled
  (0.7.80, 4 slices in isolated worktrees with the uncommitted bite copied in +
  sawCode tripwires all green, every finding verified by two refute agents that
  REPRODUCE in their own worktree: 5.11.27 gate fidelity line-by-line / is_scaled vs
  spec + libaom scale.c cross-derivation incl. a hand recompute of the 32767/32768
  rounding edge / encoder-inverse + desync + the duplicate-name grep / test adequacy
  with NEW reviewer-invented mutants → **6 findings, 5 CONFIRMED, all fixed in-cut**:
  (1) note — dist/ was stale mid-review (regenerated as part of the release flow,
  re-verified); (2) MAJOR — the global gate's y_mode RESTRICTION was untested: an
  `if (1)` mutant for the GLOBALMV-family check survived the whole suite because
  every beyond-TRANSLATION fixture used a GLOBALMV-family mode; closed with
  NEWMV + ROTZOOM/AFFINE warp-branch cases (kills: 4); (3) MAJOR — the hostile
  guards were tested one value per side only, so three off-by-one mutants survived
  TOGETHER (`>=` ALTREF rejecting the last valid ref / a weakened mi_size guard
  accepting 22 and negatives / is_scaled `>= 7` misreporting the last valid slot);
  closed with boundary cases at ALTREF / MiSize 21 / 22 / -1 / slot 7 (kills:
  3/1/1); (4) minor — the divide-by-zero backstop had zero coverage, its deletion
  survived; closed with fw=0 / fht=0 cases (the mutant now CRASHES the suite,
  SIGFPE); (5) note — a stale mm_rt comment describing the retired MiSize-21
  marker, fixed. The 1 REFUTED finding died to the best kind of evidence: a refute
  agent fetched the spec's own YMode table (07.bitstream.semantics.md,
  NEARESTMV=14..NEW_NEWMV=25) proving the ref port's numbering is the spec's, not
  an implementation copy. THE LESSON (0.7.74's, sharpened): re-running the author's
  own mutation list proves nothing new — these reviewers invented mutants the
  author had not; "each gate driven both ways" is NOT "each CONDITION of each gate
  driven both ways", and guards need pinning at BOTH boundary values, not one
  hostile value per side), and read_compound_type
  (`av1_intermode.cyr` 0.7.73, 4 slices, each finding adversarially verified: driver
  control flow vs spec / encoder-inverse + desync / blob layout + values-vs-§10 / test
  adequacy → **4 findings, 2 CONFIRMED** — the two highest-risk slices (driver flow,
  encoder inverse) found NOTHING, but the tests slice proved BY MUTATION that the
  "exhaustive per-row §10 diff" was CIRCULAR: fill and check share the accessor, so a
  self-consistent base/stride error cancels out, and the row-checkers skipped the
  adaptation-count slot that an ascending fill clobbers on overlap — two stride-3→2
  mutations left the whole suite GREEN. Fixed (count-slot asserts + absolute-offset
  layout tests for all three blobs) and re-verified by re-running the mutations
  (7/23/23/2/23 failures, previously 0). Also fixed a field comment overclaiming
  wedge_index validity on the non-compound interintra-wedge path)

## Dependencies

- stdlib only: string, fmt, alloc, io, vec, str, syscalls, assert, bench
- No external crate deps. No C. No FFI.

## Consumers

None yet — registered targets: tarang, tazama, jalwa, aethersafta
(they arrive at the families' decode milestones).

## In-flight / next

> ### Picking this up cold — the next task, concretely
>
> **Where we are (0.7.83):** keyframes decode end-to-end. **Inter frames do NOT** — the
> tile decoder is still intra-only. The ENTIRE inter mode-info decode now exists as one
> call: `av1_inter_frame_mode_info` (5.11.15, 0.7.83) over `av1_inter_block_mode_info`
> (5.11.23, 0.7.82) over everything from 0.7.62–0.7.81. ONE layer remains to a decoded
> inter frame.
>
> **Do these in order** (each is one bite; read
> [`docs/guides/verification.md`](../guides/verification.md) first):
>
> 1. **The inter tile decode** — wire `av1_inter_frame_mode_info` +
>    `compute_prediction` (the MC driver) into `decode_block`/`decode_tile`, populate
>    the MI grid + SkipModes/Skips neighbour state (un-deferring the caller-input
>    ctxs), so `av1_decode_stream` decodes a real inter frame. **This is the
>    milestone.**
> 2. Then: intra_block_mode_info in inter frames (the non-kf y_mode CDF) + the deferred
>    reads (segmentation map, delta-q/lf), the temporal scan (7.10.2.5/6 — needs the
>    DPB to save MVs), `warp_estimation` (7.11.3.8), compound blending, OBMC,
>    scaled-ref MC.
>
> **Remaining to AV1 100%:** ~35–55 patches (inter 15–22 · film grain 2–3 · the deferred
> feature-gated list 7–10 · conformance 3–8 · the encode lane 5–10 · close-out audit 1–2).
> The conformance and encode numbers are the soft ones — conformance because you cannot
> know what fails until the vectors run, and encode because *mode decision has no spec
> answer* (the 37 `av1_write_*` inverses already exist; choosing modes is a design
> problem the spec does not adjudicate, and the stated 1.0 gate is round-trip-clean,
> not compression-competitive).

The **intra still-picture decode MILESTONE is COMPLETE (0.7.25)** — profile-0
AV1 keyframes decode end-to-end to pixels. Per-release history is in
[`CHANGELOG.md`](../../CHANGELOG.md); the current picture:

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

**Done — the block/partition decode** (the 7-bite, leaf-to-root sequence
that reached a decoded keyframe, mapped by a multi-agent scoping pass;
scope + tables per bite are in the review transcript / CHANGELOG):

1. **non-coeff CDF tables** — `av1_noncoeffcdf.cyr` **[done 0.7.19]**
2. **mode-info reads** — `av1_modeinfo.cyr`: `intra_frame_mode_info` intra
   branch — `read_skip`, `intra_frame_y_mode` (above/left `Intra_Mode_Context`
   ctx), `uv_mode` (CfL-allowed selection), `read_cfl_alphas`, `angle_delta`
   (directional), `filter_intra` use/mode — decode + inverse encode +
   the `Av1ModeInfo` orchestrator, consuming the 0.7.19 CDFs. Shipped with
   the shared block-size conversion tables (Block_Width/Height,
   Mi_Width/Height_Log2, Num_4x4_*, Size_Group, Intra_Mode_Context,
   Subsampled_Size). Round-trip tested (both CDF modes + adaptive
   multi-block). The YModes/Skips neighbour grids are caller inputs, wired by
   the tile/frame loop (bite 7). **[done 0.7.20]**
3. **tx-size reads** — `av1_txsize.cyr`: `read_tx_size` / `tx_depth` symbol +
   its ctx (`(aboveW>=maxTxW)+(leftH>=maxTxH)`, neighbour-tx inputs) + the
   `maxTxDepth → Tx8/16/32/64` cdf dispatch; tables Max_Tx_Size_Rect /
   Max_Tx_Depth / Split_Tx_Size (+ av1_tx_width/height). Decode + inverse
   encode, round-trip tested (both CDF modes + adaptive). The InterTxSizes
   grid write is a caller concern (bite 5/7). **[done 0.7.21]**
4. **`compute_tx_type`** — `av1_txtype.cyr` spliced INTO
   `av1_coeffs_decode`/`_encode` (between all_zero and get_scan): retired the
   `PlaneTxType` caller-input; reads `intra_tx_type` (Set1/Set2 CDFs, ctx
   `[Tx_Size_Sqr][intraDir]`) + `get_tx_set` + `compute_tx_type`
   (`Mode_To_Txfm` for chroma). `Tx_Size_Sqr` moved to `av1_txsize`; coeffs
   take `cc`+`ncc`+`Av1TxTypeCtx` and return the computed tx type. Coeffs
   round-trip stayed green (DCT_DCT via `base_q=0` = byte-identical stream).
   **[done 0.7.22]**
5. **residual driver** — `av1_residual.cyr`: `residual()`/`transform_block()`
   (5.11.34/36) — per tx block, predict_intra → coeffs() → reconstruct() into
   a DrFrame; CfL (predict_chroma_from_luma) + MaxLumaW/H; the BlockDecoded
   availability grid (haveAboveRight/haveBelowLeft); get_tx_size; the Av1Tile +
   Av1Block decode contexts (populated by bite 7). A transform block decodes
   end-to-end to pixels; verified by concrete DC/skip/eob checks + a
   driver-vs-manual reconstruct consistency test. **[done 0.7.23]**
6. **`decode_partition` tree + `decode_block`** — `av1_partition.cyr`: the
   partition symbol/ctx + split_or_horz/vert synthesized CDFs +
   Partition_Subsize; all 10 partition types; per block mode-info → tx-size →
   residual + the MiSizes/YModes/Skips/InterTxSizes grid writes; paired encode
   lane. A full partition tree round-trips. The adversarial review caught +
   fixed an OOB MI-grid write for edge blocks on non-64-aligned frames.
   **[done 0.7.24]**
7. **tile/frame loop** — `av1_tile.cyr`: `decode_tile` (clear_above/left +
   the SB loop + clear_block_decoded_flags + decode_partition), the
   `av1_decode_intra_tile` driver (init the CDF contexts av1_ncdf_new +
   av1_ccdf_new with the base_q_idx bucket, init_symbol), + a paired encode
   driver — drives into a `DrFrame` = **first fully decoded keyframe**;
   verified by a 2-superblock varied-partition round-trip (both CDF modes).
   **[done 0.7.25 — MILESTONE close.]**

**Next — the AV1 inter layer** toward AV1 100%: the MC leaf kernels
(`put_8tap` 0.7.58, `emu_edge` 0.7.59), the **MC driver** that composes them
(`av1_mc_pred_block` 0.7.60 — single-ref/unscaled/translation-only/non-compound),
the **reference-frame buffer/DPB** (`av1_dpb.cyr` 0.7.61 — the 8-slot pixel
FrameStore + ref update 7.20 / loading 7.21 + the `av1_dpb_ref_frame` MC hook +
the `av1_decode_stream` multi-frame walk), the **MV-prediction foundation**
(`av1_mv.cyr` 0.7.62 — the `Av1Mv` representation + `av1_lower_mv_precision` 7.10.2.10
+ `av1_setup_global_mv` 7.10.2.1, the global-motion candidate), the **MV candidate
stack** (`av1_mv.cyr` 0.7.63 — `Av1MvStack` + `av1_mv_stack_add` search-stack dedup/
append 7.10.2.8/9 + the stable `av1_mv_stack_sort` 7.10.2.13 + `has_newmv`), and the
**spatial neighbour scans** (`av1_mv.cyr` 0.7.64 — `av1_mv_scan_row`/`_col`/`_point`
7.10.2.2/3/4 + `av1_add_ref_mv_candidate` 7.10.2.7 + the search-stack selection, reading
the `Av1MvCtx`/`Av1MiRec` grid), and the **`find_mv_stack` driver** (`av1_mv.cyr` 0.7.65 —
`av1_find_mv_stack` 7.10.2 + `av1_mv_extra_search`/`_add_extra` 7.10.2.11/12 +
`av1_mv_context_and_clamping` 7.10.2.14 + `av1_clamp_mv_row`/`_col`, the full candidate list
+ NewMv/RefMv/Zero/DRL contexts; temporal deferred), the **inter mode-info MV component decode**
(`av1_intermode.cyr` 0.7.66 — the MV CDF family + `av1_read_mv`/`_read_mv_component` 5.11.32 +
the paired encoder, turning the entropy stream + `PredMv` into a `Mv`), and the **single-prediction
inter mode reads** (`av1_intermode.cyr` 0.7.67 — `av1_read_inter_mode`/`_read_drl_idx`/
`av1_assign_mv_single` 5.11.32 + the New/Zero/Ref/Drl CDFs, composing the find_mv_stack contexts +
candidate stack + `read_mv` into a decoded inter YMode + Mv), the **reference-selection reads**
(`av1_intermode.cyr` 0.7.68 — `av1_read_is_inter` 5.11.30 + `av1_read_single_ref` 5.11.25 + the
Is_Inter/Single_Ref CDFs, decoding the single `RefFrame[0]`), the **compound reference path**
(`av1_intermode.cyr` 0.7.69 — `av1_read_comp_mode` + `av1_read_compound_ref` 5.11.25 + the Comp_Mode/
Comp_Ref_Type/Comp_Ref/Comp_Bwd_Ref/Uni_Comp_Ref CDFs, decoding all 16 compound reference pairs), and
the **compound mode path** (`av1_intermode.cyr` 0.7.70 — `av1_read_compound_mode` + `av1_get_mode` +
`av1_assign_mv_compound` 5.11.32 + the Compound_Mode CDF, the two-list mode/MV decode), the **interp
filter + motion mode reads** (`av1_intermode.cyr` 0.7.71 — `av1_read_interp_filter` 5.11.30 +
`av1_read_motion_mode`/`av1_read_use_obmc` 5.11.27 + the Interp_Filter/Motion_Mode/Use_Obmc CDFs), and the
**inter-intra reads** (`av1_intermode.cyr` 0.7.72 — `av1_read_interintra`/`_interintra_mode`/
`_wedge_interintra`/`_wedge_index` 5.11.28 + the new av1_iicdf blob of Inter_Intra/Inter_Intra_Mode/
Wedge_Inter_Intra/Wedge_Index CDFs) are in, as are read_compound_type (0.7.73), the MI-grid population
(0.7.74), every neighbour CDF context (0.7.75-0.7.77), the interintra/interp gating orchestrators (0.7.78)
the warp samples (0.7.79), the full read_motion_mode gating driver + is_scaled (0.7.80), the
read_ref_frames dispatcher + seg_feature_active (0.7.81) and THE 5.11.23 ORCHESTRATOR itself
(inter_block_mode_info, 0.7.82) — the complete per-block inter mode-info decode is ONE CALL now. What is
NOT in: inter_frame_mode_info
(5.11.15) — and the inter tile decode
that lets `av1_decode_stream` decode a genuine inter frame referencing the DPB through the MC driver, then
the temporal scan (which needs the DPB's deferred saved MVs) + scaled-reference/BILINEAR MC + OBMC/warp;
plus film-grain synthesis; then conformance + the encode-lane completion. (In-loop filters — deblocking,
CDEF, loop restoration — plus superres and 10/12-bit are already complete.) The deferred,
feature-gated pieces (128×128 SBs, palette, intrabc, segmentation, active
delta-q/lf, frame-end CDF save/average, the non-skip residual-encode lane)
fold in with the inter / conformance work. (`get_filter_type` was completed
in 0.7.26.)

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
