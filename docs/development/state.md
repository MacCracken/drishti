# drishti — Current State

> Refreshed every release. CLAUDE.md is preferences/process/procedures
> (durable); this file is **state** (volatile) — versions, counts,
> sizes, in-flight work.

## Version

**0.7.119** — cut 2026-07-20, not yet tagged (user's git). **FIRST MOTION-WITNESSING INTER FRAME DECODE
FROM REAL BYTES** (Phase C part 1). Preceded by a scoping workflow that CORRECTED my own premise: a
degenerate inter frame ALREADY decoded E2E (test_inter_stream_e2e) — but over a FLAT-128 reference (intra
encode lane is skip-only), so MC of any MV yields 128 and the `==128` check survives skipping MC entirely.
NO decode had ever witnessed motion; that was the real gap, not "an inter frame decodes at all." So my
earlier "no inter frame has ever decoded" was too strong — corrected in the docs. TWO coupled tests, one
release: **C1a** (test_inter_stream_content) — a NON-FLAT reference from a stream via a non-skip inter
residual (the only content-producing encode path), proving the residual survives the full av1_decode_stream
route (only ever record-tested on hand-built tiles). TX_MODE_LARGEST + DC AND AC (DC-only is flat). Teeth:
zeroing the residual -> flat. **C1b** (test_inter_stream_motion) — KEY(flat) -> INTER(content) -> INTER(pure
MC of content by a small integer MV); decoded motion frame == independent MC of the content ref AND differs
from the unshifted content. Teeth: dropping the decode-side MV reddens both (2624 px diverge). Content
snapshotted via the 2-frame prefix before the DPB refresh overwrites it. **NOT DONE, stated plainly:** the
header is still the DEGENERATE one (error_resilient=1, enable_order_hint=0) — the realistic order-hint parse
path (explicit primary_ref_frame f(3), order_hint, get_relative_dist, RefFrameSignBias) is the NEXT bite.
The oracle shares av1_mc_pred_block, so this pins WIRING not MC math (same scope as test_inter_tile_e2e).
Single-ref forward-only SIMPLE only; compound/backward refs OUT (RefFrameSignBias never derived —
av1_mvctx_set_signbias has 0 callers); CDF inheritance / intra fork / segmentation / delta still reject. A
real .ivf does NOT decode past its first non-key frame. LESSON: the scoping workflow caught that my own
"no inter frame decodes" was imprecise — a degenerate one did; what was missing was a motion-WITNESSING
decode. Verify claims against a running test, not memory of the arc. 38 suites, **29,508** suite + **1,140**
fuzz, all six gates green. Next (Phase C part 2): the realistic order-hint-enabled header — seq
enable_order_hint=1 + per-frame order_hint + explicit primary_ref_frame=7, exercising get_relative_dist and
the order-hint machinery on a decoded frame for the first time. [[av1-arc-cannot-close-yet]]

**0.7.118** — cut 2026-07-20, not yet tagged (user's git). **THE AV1 DECODE PATH IS NOW FUZZED**
(roadmap item 12). The 0.7.116 audit found the only fuzz harness (tests/drishti.fcyr) contained ZERO
codec symbols — IVF + generic bit readers only, so "fuzz from day one" was true only of the container.
tests/av1_decode.fcyr hammers av1_decode_obus / av1_decode_stream / the OBU iterator with mutated OBU
streams and asserts the trust-no-input contract: never crash, never OOB, never hang; every outcome is a
valid frame or a documented DR_ERR_* / AV1-family (band 10..29) code. PASSES from a real
reduced-still-picture keyframe seed: single-byte mutation across the whole stream x interesting values;
every truncation prefix; OBU leb128 size-field attacks; 400 random-garbage rounds + all-zeros/all-ones;
300 rounds corrupting ONLY the tile payload with headers valid, so the mutation reaches the symbol
decoder / partition walk / reconstruction. +6,270 fuzz assertions (1,140 -> 7,410). THE HARNESS WAS
CANARY-VERIFIED (the "test the harness before the code" discipline): removing the OBU obu_size<=remaining
guard makes a lying size yield an OOB payload and the harness's per-OBU "payload inside buffer" assertion
reddens (rc=174). FINDING worth recording: the DEEP decode path is STRUCTURALLY safe, not guard-based —
the arithmetic decoder reads size-matched CDFs, so garbage always decodes to in-range symbols and in-range
eob/coeff positions; removing a reconstruction-origin guard did NOT OOB from fuzz because the MI-bounded
partition walk + the frame border make it unreachable for a header-bounded frame. Two harness false
alarms fixed while building it: my known-code list first omitted the AV1 family band 10..29 (a harness
bug, not a decoder bug — the decoder correctly returns AV1_ERR_BAD_SEQ/BAD_FRAME on malformed headers).
38 suites, **29,494** suite + **7,410** fuzz assertions, all six gates green. Next remaining AV1 items
(roadmap): cross-frame CDF inheritance + intra_block_mode_info (module-sized, unblock real inter frames),
then the conformance-vector harness (the gating item). [[av1-arc-cannot-close-yet]]

**0.7.117** — cut 2026-07-20, not yet tagged (user's git). **TEST HARDENING — the compound-warp lane
dispatch was UNTESTED.** The 0.7.116 audit flagged (item 16) that a use_warp0<->use_warp1 swap in
av1_mc_pred_compound SURVIVED THE ENTIRE SUITE across four test files; I confirmed it by mutation before
trusting the finding. The per-reference warp gating had no witness. Code was correct all along — a
coverage hole, not a bug. WHY INVISIBLE: every compound-warp test used ONE frame + ONE model for both
refs, so warping ref0 == warping ref1 pixel-for-pixel, and the "mixed lane" test only asserted the two
mixed cases DIFFER — symmetric, and AVERAGE is commutative, so a swap merely EXCHANGES them and every
symmetric assertion passes both ways. THE FIX: distinct content for the two refs, then pin
mixed(ref0=warp, ref1=trans) to an ABSOLUTE oracle. Threshold-free: the finals-averaged oracle
double-rounds vs combining intermediates (~26 LSB inherent gap), so rather than a magic tolerance the
assertion is `dcorrect < dswapped` — m10 tracks the correct lane (~26) closer than the swapped one
(~119). Swap now reddens (1 failure). DEFERRED WITH REASON: the audit also suggested replacing the
linear-ramp it_ref_frame (27 sites); most are decode-vs-oracle comparisons where a shared ramp hides
nothing, and the filter-sensitive tests (BILINEAR/OBMC/sub-8x8) already carry non-linear refs — a blanket
swap would churn hardcoded goldens for little gain, so it stays a per-test fix. LESSON: "they differ" is
not a lane test when the operation is commutative and the swap exchanges the operands — pin to an
absolute oracle, and a relative-ordering assertion (closer-to-correct-than-to-wrong) beats a magic
tolerance when the oracle is only approximate. 38 suites, **29,494** suite + **1,140** fuzz assertions,
all six gates green. Next: decode-path fuzzing (roadmap item 12 — the cheapest confidence win, and the
one the audit showed the "fuzz from day one" claim had overstated).

**0.7.116** — cut 2026-07-20, not yet tagged (user's git). **ARC AUDIT + SILENT-MIS-DECODE REJECTS + the
stale-band fix. THE 0.7.x AV1 ARC DOES NOT CLOSE.** A full adversarial audit (doc claims / remaining gates /
deferrals / test quality / charter, 21 agents, every critical+major finding independently re-verified)
returned canClose=FALSE, and not close. **CORRECTNESS:** (a) inter prediction no longer leaves the MI-grid
overhang band stale — the plane loop clamped to the visible frame, so on any frame whose dims are not a
multiple of 8 the band [FrameWidth, MiCols*4) was never written, while spec/dav1d/libaom all predict the
NOMINAL extent into padded storage and that band IS read back (av1_cdef_get_at gates on cand_r < mi_rows,
not plane dims; av1_deblock walks the full MI grid). DrFrame now carries its ALLOCATED extent (152->200
bytes); writers bound against it, reference reads still clamp to VISIBLE. Witnessed on BOTH axes — the
width half only became testable after adding a RIGHT-cut (28x32) fixture, since a 32-wide frame has no
horizontal overhang. (b) SEVEN silent mis-decodes converted to clean rejects at the shared chokepoint:
primary_ref_frame != PRIMARY_REF_NONE on a non-key frame (cross-frame CDF inheritance unimplemented — such
a frame decoded its FIRST symbol with wrong probabilities and returned DR_OK on garbage, and essentially
every non-key frame a real encoder emits sets it), segmentation_enabled, delta_q_present, delta_lf_present,
allow_intrabc, allow_screen_content_tools. **A STRUCTURALLY BROKEN GATE:** `make lint` COULD NOT FAIL ON
DEFERRALS — Makefile matched only `^\s*warn ` while cyrlint prints "N untracked deferrals" and itself exits
0 on them; the gate had been reporting success with 8 present. Fixed; all 8 resolved (6 STALE, describing
work landed 0.7.92-0.7.113; 2 false positives). This is the THIRD broken measuring instrument this arc
(after the tail-piped gate check and the mutation scorer whose regex never matched) — see
[[verify-the-harness-before-the-code]]. **DOCS:** "THE INTER MODE-INFO READ LAYER IS COMPLETE" was STILL
false, the exact string the 0.7.79 audit flagged, for the same structural reason (av1_intermode.cyr rejects
segmentation/delta-q/delta-lf/the intra fork before reading anything); nine sites still said only
scaled-ref/BILINEAR remained (landed 0.7.108/0.7.110); state.md carried TWO mutually inconsistent assertion
totals ~1000 lines apart, one 588 short; "fuzzed from day one" was overstated — the single harness contains
ZERO codec symbols and the 1,140 figure has not moved in 64 releases. **THE VERDICT:** the roadmap's
criterion (decode conformance-clean + encode round-trip-clean) is unmet on both halves. NO external
conformance vector has ever been run — every AV1 test decodes bytes drishti's own writer produced, which
docs/guides/verification.md itself says proves nothing about a bug shared by both lanes. The "encoder" is a
plan-replay BITSTREAM WRITER with no forward transform, quantiser, mode decision, motion search or rate
control. And an inter FRAME still does not decode. Accurate statement: **0.7.x delivers a complete profile-0
keyframe decoder and a complete set of inter-prediction PRIMITIVES; inter frames, conformance, decode-path
fuzzing and a real encoder all remain.** roadmap.md now carries the 16 itemised remaining items with sizes.
38 suites, **29,492** suite + **1,140** fuzz assertions, all six gates green. LESSON: the arc-end audit
found MORE than any single bite's review, because it asked "is this claim true?" of prose that had been
re-read dozens of times without being checked against code — [[av1-arc-end-audit]]'s premise, confirmed.

**0.7.115** — cut 2026-07-20, not yet tagged (user's git). **INTER-INTRA BLOCKS MAY OVERHANG THE FRAME
EDGE — THE LAST TRACKED AV1 DECODE GAP CLOSES.** Both the decode reject and its encoder mirror are gone.
av1_intra.cyr: av1_intra_predict keeps its EXACT signature as a wrapper (Cyrius does not hard-fail a wrong
ARG COUNT, so changing it would have silently broken a dozen call sites) and delegates to a new
av1_intra_predict_gen taking (out_buf, out_stride) — the same split av1_warp_pred_gen/av1_warp_pred_block
already use; only the writeback branches, the reference edges still come from the frame. av1_mc.cyr: a new
Av1_McIntra scratch; av1_mc_pred_interintra_w predicts the intra half into it at the NOMINAL stride and the
blend reads values from there. **WHY STAGING RATHER THAN RELYING ON 0.7.114's PADDING:** the padding makes
the nominal intra write SAFE, but writing it to the frame would leave a RAW, UNBLENDED intra prediction in
the overhang band — different from what every other inter block leaves there, since the plain inter path
clamps. Staging keeps an edge-cut inter-intra block touching exactly the pixels a plain inter block touches,
so this bite changes no behaviour outside the blocks it enables. PROOF: a 32x28 4:2:0 fixture (MI grid 32
rows vs a visible 28) with a BLOCK_16X16 inter-intra block at pixel (16,16) overhanging by 4 luma rows,
across four mode/wedge combinations. TWO assertions carry it — the visible region must actually be BLENDED
(differ from a plain-inter MC) and the overhang band must be left UNTOUCHED. MUTATIONS (3, all red):
reverting the staging writes exactly 64 samples into that band (16 cols x 4 rows, matching the review's
independent measurement); re-inserting the decode gate; re-inserting the encoder mirror.
**A FIXTURE MISTAKE WORTH RECORDING:** the first attempt failed with DR_ERR_BOUNDS at encode and I chased
the edge cut, then the MI-row count, before finding the real cause — the fixture never set
AV1_SEQ_ENABLE_INTERINTRA. Isolating with a no-edge-cut control (which also failed) is what ruled the edge
out in one step; guessing at the geometry twice cost more than that control would have. ALSO: an unscoped
`sed -i` while debugging rewrote a shared tile-construction line in FIVE other tests — `sed -i` over a test
file applies to every match, and the pattern was not unique. Use a python replace scoped to the function's
byte range, and always re-run the whole suite after a debugging edit. **KNOWN GAP, NOW TRACKED RATHER THAN
LATENT:** the plain inter path CLAMPS predictions to the visible plane, so for a frame whose dims are not a
multiple of 8 the band [FrameWidth, MiCols*4) is never written by inter prediction. Spec/dav1d/libaom all
predict over the NOMINAL extent into padded storage, and that band IS read back — av1_cdef_get_at gates
availability on cand_r < mi_rows rather than the plane dims, and av1_deblock iterates the full MI grid — so
an edge-cut INTER frame can differ from a conformant decoder in visible pixels via CDEF taps. Intra
keyframes do NOT have this problem (av1_intra_predict writes the nominal extent). Fixing it needs
av1_mc_pred_block's bounds guard to bound against the ALLOCATED extent rather than the visible plane, which
likely means storing alloc_w/alloc_h on DrFrame. 38 suites, **29,462** suite + **1,140** fuzz assertions,
all six gates green. Next: **the stale overhang band above**, then conformance vectors + the encode lane.

**0.7.114** — cut 2026-07-20, not yet tagged (user's git). **SECURITY: HEAP BUFFER OVERFLOW IN THE AV1
INTRA DECODE PATH.** A conformant keyframe whose dimensions are not a multiple of the superblock size
could make the decoder write PAST THE END of a plane allocation and still return DR_OK. Measured: a 64x40
mono keyframe with one legal PARTITION_NONE/BLOCK_64X64 block wrote **2048 bytes** beyond the buffer.
THE DEFECT: prediction writes a block's NOMINAL extent through the deliberately-unchecked dr_frame_set,
and that extent exceeds the visible frame two ways — (1) MiCols*MI_SIZE already exceeds FrameWidth by up
to 7 samples (MiCols = 2*((W+7)>>3)); (2) a block may overhang the MI grid by a further half-1 MI units
because decode_partition only requires the block's HALF to be inside (has_rows/has_cols) — 7 MI = 28 luma
samples for a BLOCK_64X64. The decode border was 8. For 64x40 the buffer held 56 rows while the block
wrote 64, so rows 48..63 landed outside. **NOTHING CAUGHT IT BECAUSE EVERY FIXTURE IN THE CORPUS WAS A
MULTIPLE OF 64** — no test block had ever overhung. Reachable from ORDINARY video, not just crafted input.
THE FIX: dr_frame_new_ext allocates to an explicit (alloc_w, alloc_h) while REPORTING the visible dims;
dr_frame_new is now a wrapper passing visible for both, so every other caller is unchanged. The AV1
decode path allocates to the MI GRID (av1_decode_alloc_w/_h, which max() against the visible dims rather
than trusting two header fields to agree) with a 32-sample border, covering the 28-sample worst case.
Reported plane dims untouched, so CDEF/LR/superres/output crop still measure the visible frame. NOT merely
defensive padding: the overhang band is READ BACK by deblocking and CDEF into visible output, so clamping
the write would have produced WRONG PIXELS rather than a fix (the intra-parity lens established this, with
the spec + dav1d + libaom all blending over the nominal extent into padded storage). dr_frame_new_ext also
reorders its guards so an oversize frame reports OVERSIZE rather than being masked by the new
alloc-consistency BOUNDS check. PROOF: a canary alloc'd immediately after the plane buffer, with the
ADJACENCY ITSELF asserted so the test fails loudly rather than quietly stopping witnessing if the
allocator changes. Reverting the border to 8 clobbers exactly 256 u64 words = 2048 bytes — matching the
original probe AND an independent hand calculation (three concordant measurements). MUTATIONS (5 on the
decode site, all red) incl. **border 27 vs 32**, one below the worst case, pinning the BOUND and not just
its sufficiency. HOW IT WAS FOUND: an adversarial review of the INTER-INTRA overhang gate. The gate's
premise — "plain intra blocks survive an overhang" — was FALSE; the gate is sound but over-strict, and
the real bug was in the path nobody was looking at. LESSON: a gate's stated justification is a hypothesis,
not evidence; this one had been read past for many releases. Also: a corpus whose fixtures all share an
alignment cannot witness ANY alignment-dependent bug — the 64-multiple habit hid this for the whole arc.
38 suites, **29,442** suite + **1,140** fuzz assertions, all six gates green. Next: **the inter-intra
overhang gate itself** — now that the allocation covers the nominal extent, lift it and blend over the
NOMINAL w x h (what spec/dav1d/libaom all do) rather than the clamped extent; note the plain-inter clamp
at av1_intertile.cyr leaves the same band stale for every edge-cut inter block and is part of that bite.

**0.7.113** — cut 2026-07-20, not yet tagged (user's git). **SUB-8x8 CHROMA SIBLING-MV PREDICTION (spec
5.11.5 compute_prediction) — the sibling-span gate is LIFTED on both lanes.** At 4:2:0 four BLOCK_4X4 luma
blocks share ONE 4x4 chroma unit, and the spec does NOT predict it with a single MV: it emits FOUR 2x2
quadrants, each borrowing the MV of the sibling whose luma quarter it covers, read from the MI grid at
(candRow+r, candCol+c). Only the bottom-right sibling (odd MiRow AND odd MiCol) carries the chroma, so it
performs all four. Affects ORDINARY content (4x4/4x8/8x4 at 4:2:0 are common) and was previously rejected
outright rather than guessed. av1_intertile.cyr: the 0.7.112 emission loop is now LIVE — when the plane's
residual extent exceeds one prediction (only when a luma dim is 4 AND that axis is subsampled) each quadrant
reads its own sibling's cell for ref / MV / interp filters. Everything the block-level machinery adds is
spec-impossible at these sizes (inter-intra needs MiSize>=BLOCK_8X8 per 5.11.28; warp needs a nominal plane
block >=8x8 which a 2x2 quadrant never is), and a COMPOUND sibling has no single MV to lend so it is rejected
rather than silently borrowing list 0. New av1_inter_some_use_intra transcribes the someUseIntra scan (which
collapses the borrow to one whole-extent prediction when any covered cell is intra), CLIPPED to the grid —
blocks legitimately overhang the frame-sized MI grid and av1_mv_grid_cell is unchecked pointer arithmetic, so
an unclipped scan is an OOB read at the frame edge. PROOF: a 32x32 4:2:0 tile whose nested plan reaches four
BLOCK_4X4 leaves at MI (6..7,6..7) with FOUR DISTINCT MVs, each with a distinct dx+2*dy, against a NON-LINEAR
reference — itw_ctx420's x+2y ramp shifts by exactly dx+2*dy so two MVs sharing that sum give identical
pixels and the fixture would witness NOTHING (the 0.7.101 OBMC trap); the test also asserts the quadrants are
pairwise distinct so a later edit cannot make them alias. A second fixture gives each sibling a DUAL FILTER
pair with a sub-pel MV, since at 2x2 both w<=4 and h<=4 and the narrow remap collapses EIGHTTAP with SHARP —
only mixing EIGHTTAP against EIGHTTAP_SMOOTH makes the borrowed dir0/dir1 pair observable. MUTATIONS: 14 run,
**13 red** (both baseX/baseY forms, both candRow/candCol maskings, the wrong-sibling swap, forcing the
single-prediction path, borrowing list 1, the swapped filter pair, and all four someUseIntra leaf properties).
**TWO RESULTS WORTH RECORDING:** (a) reverting the 0.7.112 storage hoist NOW TURNS THIS RED (12 of 16 chroma
pixels), retroactively supplying the witness that bite could not have — the carrier's own unwritten cell reads
as INTRA_FRAME, someUseIntra fires and the prediction collapses; (b) the DRIVER's someUseIntra call SURVIVES
DELETION and is REPORTED AS UNWITNESSED — drishti's inter tile decode has no is_inter==0 path so no sibling
can be intra in a well-formed stream. Transcribed anyway (the spec has it; a future intra-in-inter bite makes
it live; and it is what turns a missing hoist into a collapsed prediction rather than a borrow of garbage) and
pinned by a DIRECT LEAF TEST rather than a claimed stream witness. ALSO FIXED: a citation I FABRICATED in
0.7.107 — av1_mc.cyr cited "6.10.22" for predW = Block_Width[MiSize] >> subX; no source supports that number,
I invented it while paraphrasing a verifier's file:line reference. Now names compute_prediction. 38 suites,
**29,418** suite + **1,140** fuzz assertions, all six gates green. Next: **the inter-intra frame-edge
overhang** (av1_intra_predict writes the NOMINAL extent unclamped) — the last tracked AV1 decode gap; then
conformance vectors + the encode lane.

**0.7.112** — cut 2026-07-19, not yet tagged (user's git). **compute_prediction GROUNDWORK — OUTPUT-NEUTRAL.**
Two prerequisites for the sub-8x8 chroma sibling-MV bite, landed together because NEITHER is independently
verifiable. Preceded by a multi-source understand workflow (spec 5.11.33 compute_prediction + 5.11.38
get_plane_residual_size, dav1d recon_tmpl.c, libaom reconinter_template.inc) with three adversarial lenses;
the ordering lens REFUTED the draft plan's mutation list as unsound, and the fixture lens CONFIRMED the
central fixture EMPIRICALLY by building it in an isolated git worktree and running it.
**(a) STORAGE LOOP 1 HOISTED above prediction** (av1_inter_store_mode split out of av1_inter_store_block,
called before the plane loop on both lanes). The spec's decode_block writes YModes/RefFrames/Mvs/InterpFilters
BEFORE compute_prediction() and the rest after residual(); drishti deferred BOTH to block end, equivalent only
while nothing read the grid mid-block. **REQUIRED FOR LUMA, not just the sub-8x8 chroma case that motivated
it:** compute_prediction's someUseIntra scan reads RefFrames at (candRow+r, candCol+c) and at LUMA
candRow/candCol ARE the block's own MiRow/MiCol; the grid is zero-initialised and AV1_INTRA_FRAME==0, so a
block that has not written its own cell reads ITSELF as intra -> geometry collapses, MV reads (0,0).
**(b) THE PLANE LOOP RESTATED IN SPEC TERMS** — planeSz/num4x4W/H/baseX/baseY/predW/predH with the spec's y/x
emission loop present but DEGENERATE (exactly one iteration for every currently-decodable block; predW x predH
differs from the num4x4*4 extent only when a luma dim is 4 AND that axis is subsampled — precisely the gated
sibling-span cases). OBMC moved OUTSIDE the emission loop (byte-identical while degenerate; per-quadrant it
would blend neighbours in up to 4x). Plus a BLOCK_INVALID guard: Subsampled_Size really does carry a -1
sentinel and av1_num_4x4_w would index OOB — unreachable for a legal stream, now a clean DR_ERR_BOUNDS.
**VERIFICATION, STATED PRECISELY BECAUSE MOST OF IT IS NOT MUTATION-COVERABLE YET:** the hoist has NO
available mutation witness and I CONFIRMED THAT BY BUILDING IT — reverting it leaves the whole suite green,
because nothing reads the grid mid-block today, which is exactly why it is output-neutral. NOT reported as
mutation-verified. For the loop restatement 2 of 7 mutations redden — the ones breaking COVERAGE (stepping by
a constant instead of predW/predH overlaps and overruns). The other five survive for a STRUCTURAL reason, not
a coverage gap: **while every sub-prediction shares ONE MV, the loop's PARTITIONING is unobservable**, because
splitting a translation MC into exactly-tiling sub-blocks with the same MV reproduces identical pixels — so
swapping n4w/n4h in the bounds, or taking predH from the wrong axis, still tile exactly and still survive.
Two more are proven tautologies under the gate ((c>>sx)*4 == (c*4)>>sx whenever bw4>=2, hence even MiCol) and
one is vacuous (Block_Width[planeSz] vs Block_Width[MiSize]>>subX differ on exactly the six gated sizes). ALL
become witnessable in the NEXT bite, where the quadrants carry DIFFERENT MVs. Evidence here = the
byte-identical suite (29,400 unchanged, ~1000 inter assertions incl. e2e pixel comparisons) + the two coverage
mutations. LESSON: an output-neutral restatement of a loop is only witnessed in its COVERAGE, never its
PARTITIONING, until the per-part inputs actually differ — do not claim otherwise. 38 suites, **29,400** suite
+ **1,140** fuzz assertions, all six gates green. Next: **lift the sibling-span gate and make the emission
loop live — per-quadrant chroma prediction borrowing each sibling's MV from the MI grid.** The fixture is
already proven constructible (four BLOCK_4X4 at MI (6..7,6..7) with four distinct MVs round-trip and each
luma quadrant is bit-exact vs its own-MV oracle); note that a GREEN LUMA witness is NOT evidence for the
hoist — luma reads the block's own ib and never touches the grid, so only a CHROMA comparison can redden it.

**0.7.111** — cut 2026-07-19, not yet tagged (user's git). **WITNESSES FOR THE is_scaled GATES THAT 0.7.110
MADE LOAD-BEARING.** Tests only, no shipped-code change. Until scaled references decoded these gates were
OUTCOME-NEUTRAL (a scaled ref was rejected by the MC layer whatever the warp gate decided), and **all three
were confirmed to SURVIVE mutation before these tests were written** — the honest way to find out what B5
actually needed. tests/av1_intertile.tcyr: three GLOBALWARP witnesses for spec 7.11.3.1 step 7's
`is_scaled(refFrame)==0` condition on useWarp==2 — the single-ref model build and EACH compound lane.
Dropping a conjunct makes that lane build a global model and call av1_warp_pred_gen on a scaled ref, which
still correctly refuses, latching DR_ERR_UNSUPPORTED where pixels were expected. The compound pair uses
exactly ONE scaled ref each (ref0-scaled / ref1-scaled) because a both-scaled fixture cannot tell the two
gates apart; the two orientations are additionally asserted to give DIFFERENT pixels. New it_ref_frame_scaled
(32x32, NON-LINEAR fill — it_ref_frame's x+2y gradient is reproduced exactly by every AV1 sub-pel filter and
so cannot distinguish predictions; the same trap 0.7.108 hit in the BILINEAR e2e). Plus a TWO-SOURCES-OF-TRUTH
test: "is this reference scaled?" is answered from Av1RefState METADATA (what av1_is_scaled reads -> GATES
warp) and from the DPB DrFrame's real PIXEL dims (what av1_mc_pred_core measures -> drives MC GEOMETRY).
Both disagreement directions pinned: metadata claiming UNSCALED over half-size pixels gives a clean latched
DR_ERR_UNSUPPORTED from the warp path; metadata claiming SCALED over full-size pixels decodes to the unscaled
global-MV translation. Hostile input must yield a sticky error or correct-per-pixels output, never a crash.
MUTATIONS: the three gates each red INDEPENDENTLY (1 failing assert each for the compound pair, confirming
the isolation), plus the warp-relax mutation caught by BOTH the gw-scaled reject assert and meta/pixel case A.
**THE LOCALWARP HALF NEEDED NOTHING — it was already fully witnessed**, and finding that out mattered: it
rests on a DIFFERENT mechanism (read_motion_mode 5.11.27 refuses to code the motion_mode symbol at all when
is_scaled(RefFrame[0]) — a SYMBOL-SCHEDULE property, not a prediction one), already covered on both lanes in
tests/av1_intermode.tcyr by the 0xA5 marker idiom plus an independent decode-side conformance test built from
the leaf writers (so a gate bug shared by the driver and its inverse cannot cancel). The original plan
conflated the two mechanisms; doing so would have produced a redundant test AND left the three GLOBALWARP
gates unwitnessed. LESSON: when a plan says "witness gate X", first MUTATE to find out which parts are
already covered — the answer here was "the half the plan emphasised, and none of the half it mentioned in
passing". 38 suites, **29,400** suite + **1,140** fuzz assertions, all six gates green. Next: the AV1 arc's
remaining decode gaps are the sub-8x8 chroma sibling-span and the inter-intra edge overhang (both cleanly
rejected, both tracked in roadmap.md), then conformance vectors + the encode lane.

**0.7.110** — cut 2026-07-19, not yet tagged (user's git). **SCALED-REFERENCE MC IS WIRED — the last
MC-GEOMETRY track closes.** A block whose reference differs in size from the current frame now decodes to
correctly scaled pixels instead of DR_ERR_UNSUPPORTED. Every motion mode (SIMPLE/OBMC/LOCALWARP/GLOBALWARP),
every compound and masked form, the full temporal-MV arc, every interpolation filter, and now every reference
geometry are in. **NOT "the inter arc is complete" — I wrote that first and it was an OVERCLAIM caught by
auditing the gates instead of re-reading my own prose ([[av1-arc-end-audit]]'s standing lesson, recurring).
TWO inter-prediction gaps remain, both still DR_ERR_UNSUPPORTED in av1_intertile.cyr:** (a) a sub-8x8 block
whose CHROMA UNIT SPANS SIBLING blocks (subx && bw4==1, or suby && bh4==1) — the spec's compute_prediction
predicts the full even-aligned chroma unit using the SIBLINGS' MVs from the MI grid, drishti predicts per
block; rejected on GEOMETRY ALONE before any symbol is read, so never silent garbage; (b) an INTER-INTRA
block OVERHANGING the frame edge — av1_intra_predict writes the NOMINAL extent without clamping to the plane.
The compound-type and motion-mode gates beside them are DEFENSIVE, not scope limits (a 2-value alphabet and a
3-value enum; unreachable from a conformant bitstream). av1_intertile.cyr's scope comment still listed OBMC,
compound, inter-intra and scaled MC as pending bites — re-derived from the actual gates this bite.
av1_mc_pred_core: the reference gate SPLIT BY KIND — bit-depth/subsampling mismatch stays a PERMANENT
DR_ERR_UNSUPPORTED (incomparable sample grids); EXACT dim equality is the fast-path selector; any difference
runs av1_mc_scale_valid then av1_mc_put_8tap_scaled. A non-conformant ratio (ref >2x larger or >16x smaller on
either axis) is now DR_ERR_BAD_HEADER — a bitstream violation, not an unsupported feature. WARP DELIBERATELY
KEEPS REJECTING a scaled ref, on TWO INDEPENDENT spec mechanisms that are NOT the same rule (the spec-fidelity
lens's correction): 7.11.3.1 step 7 gates useWarp==2 on is_scaled==0, while LOCALWARP is unreachable because
read_motion_mode (5.11.27) refuses to code the motion_mode symbol when is_scaled(RefFrame[0]). COMPOUND with
ONE ref scaled and one not now produces pixels on both lanes — NO code change needed (av1_mc_pred_compound
already routes each ref through av1_mc_pred_core independently), and it is genuinely reachable: 7.11.3.1
evaluates useWarp inside the per-refList loop, so ref0 can warp while ref1 scale-translates. PROOF: the five
fixtures that used to assert DR_ERR_UNSUPPORTED are now correctness KATs, chief among them **THE
CHROMA-COLLISION TRIPLE** — luma 23x17 / 23x18 / 24x17 ALL collide to 12x9 chroma against a 24x18 frame at
4:2:0, so the chroma PLANE dims are identical in all three; because 7.11.3.3 derives the scale factors from
LUMA the three must give THREE DIFFERENT results, and deriving them from plane dims collapses the checksums to
one value (mutation W1, red). That is exactly the case the old gate rejected because getting it wrong emits
plausible wrong chroma with no error. Compound anchored by AVERAGE-of-self vs the verified single-ref scaled
prediction + a mixed lane differing from both all-unscaled and all-scaled. MUTATIONS (8, all red): plane-vs-luma
scale factors, stepX/stepY swap, startX/startY swap, chroma sub forced to 0, dropping scale_valid, keeping the
old blanket reject (dead-path check), relaxing the warp reject, and dropping the compound flag.
**ONE DOCUMENTED NON-WITNESS:** the fast-path selector is EXACT dim equality, not "does the scale factor round
to 1<<14". Those genuinely differ — a 32768-wide frame with a 32767-wide ref rounds to a unit factor while
lastX still differs, so the unscaled path would read one column past the ref's last valid column at the right
edge. But it is UNREACHABLE here: dr_frame_new caps dims at DR_FRAME_MAX_DIM=16384 and the rounding cannot
collapse below 32768 (scale_factor==1<<14 needs (ref-cur)*16384 inside a window of half-width <= cur/2 <= 8192,
which no nonzero step of 16384 enters; the smallest cur where ref==cur-1 rounds to unit is exactly 32768, twice
the cap). The test pins the CAP and the ARITHMETIC rather than asserting it from a comment — per the 0.7.98
lesson I BUILT the witness first and it fails at frame allocation, not at the gate. The exact selector is kept
as the strictly safer form. 38 suites, **29,373** suite + **1,140** fuzz assertions, all six gates green.
Next: **B5 = witness the is_scaled gates that just became load-bearing** (the GLOBALWARP pixel witness and the
LOCALWARP symbol-not-consumed witness are DIFFERENT mechanisms and need separate fixtures; plus the
metadata-vs-pixel-dims disagreement case — Av1RefState governs gating, the DrFrame governs MC geometry).

**0.7.109** — cut 2026-07-19, not yet tagged (user's git). **THE SCALED CONVOLVE KERNEL (spec 7.11.3.4 with a
non-unit step) — OUTPUT-NEUTRAL, not yet wired.** The largest and riskiest bite of the track; only the wiring
(B4) and the is_scaled gate witnesses (B5) remain before inter frames decode end-to-end. av1_mc.cyr:
av1_mc_put_8tap_scaled — a SEPARATE kernel, not a put_8tap flag, because a non-unit step changes the sub-pel
PHASE from sample to sample so the filter row must be re-selected inside both loops; that also means the source
window is no longer a fixed rectangle (at the 2x bound a 128-wide block reads 262 source samples), so the
emu_edge gather serving the unscaled path (AV1_MC_MAX_GATHER=135) CANNOT be reused — the kernel clamps PER TAP
straight out of the DrFrame (av1_mc_8tap_clipped, clip INSIDE the tap loop) and needs no gather buffer at all.
Rounding family 6-ib / 6+ib / 6 mirrors put_8tap so the two agree bit-for-bit at step 1024. Phase 0 is inline
in both passes because drishti's table DROPS the spec's phase-0 identity row (index p is the spec's p+1): the
identity makes the H dot px<<ib and the V dot av1_round2(m, ib), sampling the CENTRE tap (t==3). New
Av1_McScaledMid (262*128 i64) with a DEDICATED lazy allocator — kept out of av1_mc_drv_scratch whose OOM check
is one disjunction (a partial failure there returns DR_OK with the pointer still 0 -> a wild write to address
0). PROOF: **K1, the identity differential, needs NO golden** — at scale 1<<14 the geometry gives step 1024 and
startX=(pos16<<6)+32, so the scaled kernel must reproduce the already-trusted av1_mc_pred_block bit-for-bit.
NOT a tautology: put_8tap picks one filter row per block and takes FUSED rounding shortcuts on its 1D branches
while the scaled kernel always materialises the intermediate and re-derives the phase per sample, so the 15
cases deliberately include H-only / V-only / integer to exercise all three fused branches, plus overhang cases
that cross the gather boundary (emu_edge padding vs per-tap Clip3). Then 15 genuinely-scaled KATs from
scripts/refs/scaled_mc_ref.py (spec convention) + a hostile-input table. MUTATIONS: 22 run, **21 red**. Both
spec asymmetries are pinned — the H pass uses the FULL startY while the V pass uses only (startY & 1023), and
the -3 tap offset belongs to the H source column ONLY — plus every shift, both phase-0 identities, the hoisted
clip, and the filter-set axis selection. **Removing the w/h cap SEGFAULTS (rc 139)**, concretely proving the
memory-safety lens right that an intermediateHeight-only reject is insufficient: (h-1)*stepY is an i64 multiply
and h-1==2^54 with stepY==1024 wraps the product to exactly 0 -> intermediateHeight 8 passes any height-only
check while the V loop runs 2^54 iterations off the end. A test pins that wrap directly.
**THE ONE SURVIVOR, recorded not glossed:** deleting the scratch's DR_ERR_OOM null-check leaves every test
green — alloc never fails under test and drishti has NO allocator fault-injection harness, so NO DR_ERR_OOM
branch anywhere in the repo is mutation-covered. A real repo-wide coverage gap; noted at the allocator, and a
candidate for the 0.11.x audit arc. 38 suites, **29,324** suite + **1,140** fuzz assertions, all six gates
green. Next: **B4 = wire the scaled path into av1_mc_pred_core (bit-depth/subsampling stay HARD rejects, exact
dims become the unscaled fast-path selector, any dim difference runs av1_mc_scale_valid then the scaled kernel;
warp KEEPS rejecting a scaled ref) — the OUTPUT-CHANGING bite that closes the inter arc; then B5 the gate
witnesses.**

**0.7.108** — cut 2026-07-19, not yet tagged (user's git). **BILINEAR MC (output-CHANGING, lifts an explicit
reject) + the 7.11.3.3 SCALING GEOMETRY (output-neutral leaves).** Two halves of the last inter track; only
scaled-reference MC now remains. **BILINEAR:** av1_mc_filter_set gained `f == 3 -> set 5` and
av1_mc_pred_core's reject is gone (filter guard widened 0..2 -> 0..3). NO table work — drishti set 5 already
IS the halved bilinear kernel {0,0,0,64-4p,4p,0,0,0}; I verified all 720 coefficients against the spec under
the permutation (spec 3->drishti 5, 4->3, 5->4). The branch precedes the narrow remap because spec 7.11.3.4's
`w <= 4` branch has NO else — BILINEAR is never remapped. Reachable ONLY via the frame header's
interpolation_filter f(2) (SWITCHABLE's alphabet is 3 symbols); av1_read_interp_filters copies the frame-level
value to both dirs. PROOF scripts/refs/bilinear_mc_ref.py — deliberately in the SPEC convention (16 phases,
rows summing 128, spec InterRound0/1) rather than drishti's halved dav1d one, so agreement PROVES the
halving-plus-reduced-shift equivalence instead of assuming it; its table is MACHINE-GENERATED from the
digest-pinned spec markdown (md5 51249ad9) with a verify_against_spec() re-derivation; and it REPRODUCES ALL
17 pre-existing driver KATs before emitting the new ones — which also re-establishes the provenance those
tests lost when mc_driver_ref.py's scratchpad was wiped. 14 new driver KATs (b01-b14) + an e2e + direct
set-selection asserts. MUTATIONS (6, all red) incl. the LATENT-MIS-DECODE (delete the f==3 branch -> wrong
pixels, no error) and the ORDERING (move it after the dim remap -> only narrow blocks break).
**GEOMETRY:** av1_mc_scale_valid / _scaled_step / _scaled_start / _scaled_last / _scaled_mid_h, plus
av1_scale_factor EXTRACTED into av1_frame.cyr (av1_is_scaled computed it inline twice; is_scaled and the MC
geometry now share one derivation). scripts/refs/scaled_geom_ref.py cross-checks every startX against
libaom's DIFFERENT algebraic form (av1_scaled_x / SCALE_EXTRA_OFF) over 2688 combinations. 15 KATs; 13
mutations, all red. Max intermediateHeight over the whole legal space is EXACTLY 262 with the vertical read
topping out at 261 — zero slack, so B3's buffer sizing is an immediate-OOB risk, not a latent one.
**TWO ALIASED-FIXTURE DEFECTS FOUND AND FIXED — both mine, both caught by mutation, not by reading:**
(a) the e2e inter harness could not distinguish interpolation filters AT ALL — ir_ref fills with x+2*y, a
LINEAR RAMP, and every AV1 sub-pel filter reproduces a linear function exactly, so BILINEAR == EIGHTTAP ==
SHARP bit-for-bit. The first BILINEAR e2e assertion passed for the wrong reason; only the paired
`decode != EIGHTTAP oracle` half failed. New ir_ref_hc (non-linear, high-contrast). Same secretly-an-identity
trap as OBMC 0.7.101. (b) the conformance fixtures were SQUARE (fw==fht), so rewriting the HEIGHT condition to
test fw passed green; now deliberately non-square and both axis-swap mutations redden. **AND A DOC CLAIM I GOT
WRONG AND MUTATION CORRECTED:** I wrote that the halfSample terms cancel at 1:1 so an unscaled fixture cannot
witness EITHER — false. Dropping ONE breaks 1:1 too; only the JOINT drop is invisible there (residue
8*(scale-(1<<14))). The comment now says that, and G13 confirms the joint drop reddens exactly g04-g15 and
leaves g01-g03 green. LESSONS: (a) Round2Signed is witnessable ONLY at an exact tie — av1_round2 is arithmetic
so it agrees everywhere else; a merely-NEGATIVE input is not enough (0.7.103's half-boundary lesson recurring),
so g15 is tuned to baseX == -408704 == -1597*256+128. (b) A complementary oracle that calls the function under
test witnesses WIRING, not MATHS — recorded in the e2e test itself, mutation-demonstrated both ways. 38 suites,
**29,129** suite + **1,140** fuzz assertions, all six gates green. Next: **B3 = the scaled convolve kernel
(unwired; carries the memory-safety lens's mandatory w/h/step guards — (h-1)*stepY WRAPS i64 so an
intermediateHeight-only reject is insufficient), then B4 the wiring, B5 the is_scaled gate witnesses.**

**0.7.107** — cut 2026-07-19, not yet tagged (user's git). **FILTER-SET + REFERENCE-GEOMETRY LEAVES — an
OUTPUT-NEUTRAL refactor opening the LAST inter track (scaled-reference / BILINEAR MC).** Preceded by a
multi-source understand workflow (spec 7.11.3.3/7.11.3.4 + Subpel set map re-fetched from AOMediaCodec/av1-spec,
dav1d mc_tmpl.c/tables.c, libaom convolve.c/scale.c/decodeframe.c — all md5-pinned in scratchpad/srcs/) whose
adjudicated derivation was checked by four adversarial lenses; three confirmed, the memory-safety lens REFUTED
the draft plan (see B3's carried-forward guards below). av1_mc.cyr: `av1_mc_filter_set(filt, dim)` — the
7.11.3.4 set selection lifted out of put_8tap, TOTAL by construction (a leading `& 3` keeps every input inside
0..AV1_SUBPEL_SETS-1; av1_mc_subpel_row bounds-checks nothing and the blob is exactly 6*15*8 i64) — which also
CLOSES a latent OOB: the horizontal set was masked (`filter_type & 3`) but the vertical was a bare
`filter_type >> 2`, unbounded above (unreachable today, the caller range-guards filt to 0..2). And
`av1_mc_ref_compat` (bit-depth + subsampling — a PERMANENT reject on every path) / `av1_mc_ref_unscaled`
(exact LUMA dims + the plane's own), split along the seam where the callers diverge: B4 lets the TRANSLATION
path accept a dim mismatch while WARP must keep rejecting it (spec 7.11.3.1 step 7 for GLOBALWARP; the
read_motion_mode syntax gate for LOCALWARP — two DISTINCT mechanisms, per the spec-fidelity lens). PROOF: the
existing suite passing BYTE-IDENTICALLY (38 suites / 28,890 / 1,140 unchanged, only av1_mc.cyr touched) IS the
neutrality proof; then `test_filter_set_selection` pins the leaf directly on the two cases no kernel fixture
reaches — dim==2 (REACHABLE: predW = Block_Width[MiSize] >> subX, so a BLOCK_4X4 luma block's 4:2:0 chroma is
2 samples wide) and a hostile filt x dim sweep asserting the result never leaves the table. MUTATIONS (10, all
red): the `& 3` mask, `dim<=4`->`dim<4`, `dim<=4`->`dim<=2`, `3+(f&1)`->`3+(f&3)`, narrow base 3->4, the two
axis swaps (dims w<->h, filter halves h<->v), both luma conjuncts INDEPENDENTLY, and the bit-depth conjunct.
THE FIXTURE TRAP THIS BITE FOUND AND CLOSED: luma 24x18 vs 23x17 differs in BOTH dims, so the chroma-collision
reject fired even with one luma conjunct deleted — a symmetric fixture witnessing the PAIR but neither half
(the 0.7.76 ref_count_ctx lesson exactly). All four of 24x18/23x18/24x17/23x17 collide to 12x9 chroma at
4:2:0, so width-only and height-only references now pin each conjunct alone (both mutations confirmed SURVIVING
before the fixtures were added). Doc defects fixed (all three verified against the fetched spec): Subpel_Filters
cited to 7.11.3.4 (7.11.3.2 is the ROUNDING-VARIABLES process); the dav1d convention described as HALVED
coefficients with correspondingly reduced shifts — bit-identical to spec since Round2(2s,n)==Round2(s,n-1) for
the arithmetic-shift av1_round2 and every spec tap is even — INDEPENDENTLY of the extra intermediate_bits its
2-pass kernel carries (a kernel property, not a table property); set 5 named BILINEAR (spec set 3), a genuine
2-tap kernel, not "scaled-bilinear", with the set-order map (drishti->spec 3->4, 4->5, 5->3) written out; and
the stale warp-table MD5 pin re-recorded (c764ff07 as fetched 2026-07-18 vs fbf72ee5 on master 2026-07-19 —
byte-identical rows, stale provenance not data divergence). 38 suites, **28,905** suite + **1,140** fuzz
assertions, all green. **INCIDENT — I REPORTED "gates green" WHEN fmt-check WAS RED.** `make fmt-check` was
failing on the COMMITTED 0.7.106 tree (av1_mc.cyr + av1_mv.cyr); my session-start check piped `make lint` to
`tail`, which discards the exit code and showed only a passing tail. Separately my first mutation harness
scored `grep -oE "^[0-9]+ failed"`, which NEVER matches (the failed count is mid-line, not line-start), so
three mutations were scored SURVIVED that were in fact RED — caught only by running a deliberately blatant
mutation as a harness sanity check. LESSONS: (a) NEVER pipe a gate through `tail`/`head` — use the EXIT CODE;
(b) a mutation harness must itself be sanity-checked against a known-red mutation BEFORE any survivor is
believed, because a broken scorer reports universal survival, which reads exactly like thorough-but-clean;
(c) [[av1-arc-end-audit]] applies — do not report green while a gate is red. fmt-check is now green for the
first time in the arc. Next: **B1 = BILINEAR (un-gate filt==3; the table already exists at set 5, so it is
selection + reject-lift only), then B2 scaling-geometry leaves, B3 the scaled convolve kernel, B4 the wiring,
B5 the is_scaled gate witnesses.**

**0.7.106** — cut 2026-07-18, not yet tagged (user's git). **COMPOUND GLOBAL_GLOBALMV WARP — a latent-mis-
decode FIX.** A compound (2-ref) GLOBAL_GLOBALMV block whose refs carry >TRANSLATION global models was
previously translation-MC'd SILENTLY (warp_valid gated on is_comp==0); now each ref WARPS at INTERMEDIATE
precision + the existing combine runs unchanged. 3-source confirmed (spec 7.11.3.5 + dav1d warp_affine_8x8t_c
+ libaom av1_warp_affine_c): compound warp vertical = Round2(sum,7) NO Clip1 (vs single-ref
Clip1(Round2(sum,7+ib))), horizontal unchanged (7-ib) — lands at bit_depth+ib intermediate byte-identical to
compound put_8tap (Round2,6), so the combine is producer-agnostic; per-REFERENCE gating (mixed reachable: one
warps while the other translation-MCs); only GLOBAL_GLOBALMV reaches it (LOCALWARP is single-ref only); no
rounding offset (drishti plain Round2). av1_mc.cyr: av1_warp_affine_8x8 + a `compound` flag (intermediate vs
final vertical); av1_warp_pred_gen + a `compound` param + a DEDICATED Av1_McWarp8 kernel-output scratch (was
Av1_McTmp — decoupled so the compound path write-backs into BOTH McTmp/McOut without a self-copy); av1_warp_
pred_block + the inter-intra warp pass compound=0 (unchanged); av1_mc_pred_compound + (wm0,wm1,use_warp0,
use_warp1) — each ref warps into its intermediate buffer or translation-MCs, the two warps INDEPENDENT
(av1_warp_pred_gen touches neither McTmp nor McOut internally: kernel=McWarp8, gather=McRect/McGather,
mid=McMid). av1_mv.cyr: a 2nd reusable warp-model scratch (av1_warp_model_scratch2) — a compound block needs
both refs' models live at once. av1_intertile.cyr av1_decode_block_inter: the GLOBALWARP model-build gained a
compound branch (wm0 from ref0 in scratch, wm1 from ref1 in scratch2, each gated GmType>TRANSLATION &&
!force_int && !is_scaled); the plane loop passes per-ref use_warp0/1 = warp_valid_r && nominal-plane>=8x8; the
is_comp==0 restriction LIFTED. The ENCODER uses a GIVEN residual + does NOT predict -> decode-only change, no
encoder mirror. PROOF: test_mc_compound_warp direct complementary-oracle anchored to the VERIFIED single-ref
warp (compound(AVERAGE,R,R,warp,warp) == av1_warp_pred_block(R) within +-1 — a wrong intermediate shift blows
the diff far past 1) + warp!=translation + a MIXED (ref0 warps, ref1 translates) per-ref-independence witness;
test_ir_compound_global_warp e2e (a compound GLOBAL_GLOBALMV block with two DISTINCT warp models decodes == a
compound warp-warp reference + != translation-compound). MUTATIONS (8, all red): the compound vertical round
7->8, the no-Clip1 branch, both av1_mc_pred_compound per-ref branches, the dispatch use_warp0/1 gates, the
compound model-build GLOBAL_GLOBALMV gate, and the ref1-model source (av1_ib_ref(ib,1) — needed DISTINCT GMs
to witness, identical GMs masked it). 38 suites, **28,890** suite + **1,140** fuzz assertions, all green.
LESSON: a shared warp fn re-parameterized TWICE (write-back target 0.7.105 + a dedicated McWarp8 kernel scratch
0.7.106) now serves single-ref-final / inter-intra-final / compound-intermediate paths with one wrapper each;
a compound-warp witness needs DISTINCT per-ref models (identical GMs make the ref1-source mutation invisible),
and the AVERAGE-of-self==single-ref anchor pins the intermediate precision without a fresh ref port. Next:
scaled-reference / BILINEAR MC (the last inter-prediction track before inter frames decode end-to-end).

**0.7.105** — cut 2026-07-18, not yet tagged (user's git). **INTER-INTRA WARP-BLEND.** Un-defers the
`is_ii && warp_valid` reject (installed by 0.7.100's review): a GLOBALMV inter-intra block whose ref carries a
>TRANSLATION global model (useWarp==2 / GLOBALWARP) now WARPS the inter part per plane + blends the intra
instead of returning DR_ERR_UNSUPPORTED. 3-source confirmed (spec 7.11.3.1 + dav1d recon_tmpl.c + libaom
reconinter.c): the useWarp derivation has NO inter-intra exception — the inter part warps exactly as a plain
warp block (same per-plane >=8x8 gate: luma warps, 4x4 chroma at 4:2:0 falls back to translation), and since
inter-intra is isCompound==0 (InterPostRound==0) the inter samples are final-precision either way, so the
Round2(mask*intra + (64-mask)*inter, 6) blend is byte-identical. Inter-intra is never LOCALWARP
(read_motion_mode forces SIMPLE) so only GLOBALWARP is reachable. av1_mc.cyr: av1_warp_pred_gen (the former
av1_warp_pred_block body + (out_buf, out_stride); the per-8x8 kernel writes Av1_McTmp, the write-back targets
the frame or a block-relative buffer — so the inter-intra path warps into Av1_McOut for the blend;
av1_warp_pred_block is now a thin frame-write wrapper, all 9 callers unchanged); av1_mc_pred_interintra_w (the
former av1_mc_pred_interintra body + (wm, use_warp): warp the inter into Av1_McOut when the plane warps else
av1_mc_pred_core; intra + mask + blend UNCHANGED; av1_mc_pred_interintra is the translation-form wrapper).
av1_intertile.cyr av1_decode_block_inter: the is_ii && warp_valid reject REMOVED; the plane loop computes
use_warp = warp_valid && nominal-plane>=8x8 once and passes it to both the plain-inter and inter-intra paths.
The encoder uses a GIVEN residual (av1_fb_resid) and does NOT predict, so this decode-only change needs no
encoder mirror. PROOF: the 0.7.100 gw-ii e2e test now asserts the block DECODES (was rejected) + its 32x32
skip block == a direct warp-blend reference (av1_warp_model_from_global + av1_mc_pred_interintra_w use_warp=1);
+ a direct complementary-oracle test ii_warp_orch_case (av1_mc_pred_interintra_w(use_warp=1) pixel-exact vs
Round2(mask*intra + (64-mask)*WARPED, 6), the warped inter from the VERIFIED av1_warp_pred_block) at the origin
AND a non-origin (8,8) block (witnesses the block-relative write-back offset) + a warp!=translation
differential. MUTATIONS (5, all red): the use_warp branch, the dispatch per-plane gate, the -x and -y
write-back offsets, the McTmp/McOut kernel target (also breaks the plain-warp path). 38 suites, **28,881**
suite + **1,140** fuzz assertions, all green. LESSON: parameterizing a shared warp fn (write-back target +
kernel scratch McOut->McTmp) let the inter-intra path reuse the verified warp kernel with ONE thin wrapper +
zero call-site churn; the complementary-oracle pattern (warp inter via the verified av1_warp_pred_block, then
recompute the blend) validates the new path without a fresh ref port. Next: compound GLOBAL_GLOBALMV warp,
then scaled-reference/BILINEAR MC.

**0.7.104** — cut 2026-07-18, not yet tagged (user's git). **THE TEMPORAL SCAN (temporal-MV Bite 3) — the
first OUTPUT-CHANGING temporal-MV bite.** The last find_mv_stack deferral: when use_ref_frame_mvs is set,
find_mv_stack now reads the current frame's MotionFieldMvs (built by motion_field_estimation, 0.7.103), folds
projected temporal MVs into the candidate stack, and derives ZeroMvContext — closing the temporal-MV arc
(producer 0.7.102 → estimation 0.7.103 → scan 0.7.104). av1_mv.cyr: av1_temporal_scan (7.10.2.5 — step 2/4 by
dim<64/≥64, bound Min(bw4/bh4,16), + 3 extension samples for a block in [8×8,64×64) gated on check_sb_border
using MiRow&15/MiCol&15); av1_add_tpl_ref_mv (7.10.2.6 — mvRow/Col|1, is_inside FIRST, y8/x8=>>1, the
LOAD-BEARING ZeroMvContext state machine: unconditional=1 at origin BEFORE the sentinel, lower_mv_precision
AFTER the sentinel BEFORE the |cand-gmv|>=16 test, the refine is an ASSIGN that may reset 1→0; single reads
RefFrame[0], compound reads both planes at the same cell needing BOTH valid; reads an ALREADY-projected MV, NO
re-projection); av1_tpl_stack_append (dedup/append weight FIXED 2, NO NewMvCount, list-0 dedup single / 4-comp
compound, cap 8) + a reusable Av1_TplScratch for lower_mv_precision; wired into av1_find_mv_stack between the
REF_CAT_LEVEL weighting and scan_point(-1,-1), gated on use_ref_frame_mvs. 3-source reconciled (spec 7.10.2.5/6
+ dav1d refmvs.c + libaom mvref_common.c) via a workflow. PROOF scripts/refs/tmvs_scan_ref.py spec-literal
oracle + ctx-level KATs (origin state machine sentinel-leaves-1 / far-refines-1 / near-RESETS-0; lower inside
the scan; grid+extension+dedup; temporal dedups a spatial entry; compound both-valid/one-sentinel/distinct-
list1; check_sb_border isolated from is_inside via a 2-SB frame; is_inside isolated via a sub-tile; the
use_ref_frame_mvs gate e2e through find_mv_stack). MUTATIONS (12, all red): is_inside, unconditional ZeroMvCtx
set, single+compound sentinels, lower, the >=16 threshold, the refine reset-to-0, append weight, dedup weight,
check_sb_border, compound list-1 dedup, the sample step; the mvRow/Col|1 is UN-WITNESSABLE by construction
((X|1)>>1==X>>1 + even SB-aligned tile bounds). Existing find_mv_stack tests use use_ref_frame_mvs=0 → no
regression. 38 suites, **28,870** suite + **1,140** fuzz assertions, all green. LESSON: a temporal witness
cell is silently skipped when is_inside/check_sb_border fails, the cell is sentinel, or it dedup-matches an
existing entry — the sentinel/dedup analogue of the earlier "projected off-grid" masking; isolate each gate
(a sub-tile isolates is_inside from check_sb_border and vice versa). Next: **inter-intra + GLOBALWARP
warp-blend, compound GLOBAL_GLOBALMV warp, then scaled-reference/BILINEAR MC.**

**0.7.103** — cut 2026-07-18, not yet tagged (user's git). **motion_field_estimation (temporal-MV Bite 2).**
The full projection process (spec 7.9) that builds MotionFieldMvs — the per-8×8 pre-scaled temporal-MV field
the scan (7.10.2.5/6, Bite 3) will read — landed OUTPUT-NEUTRAL in two de-risked steps. **2a (leaves):** the
pure arithmetic as un-wired KAT'd leaves (the warp_estimation/setup_shear pattern). av1_mv.cyr: Div_Mult[32]
(spec 7.9.3, floor(16384/i), formula-generated + KAT-anchored to the 32 spec values); av1_get_mv_projection
(clippedDenom=Min(31,den), clippedNum=Clip3(-31,31,num), each comp Clip3(-16383,16383, Round2Signed(mv*cn*
DivMult[cd], 14)) — USES av1_round2_signed NOT plain round2, product fits i64 so no int32 overflow trick);
av1_mv_project_pos (7.9.4 project — offset8 negate-shift-negate with LOGICAL >> on the positive operand, -1
outside the window); av1_get_block_position (PosY8 maxOff 0 / PosX8 maxOff 8). **2b (driver + projection +
scratch + hook):** av1_mv_projection (7.9.2 — per-ref, early-rejects on resolution change / KEY / INTRA_ONLY
/ null saved field; per cell posValid = |refToCur|≤31 && |refOffset|≤31 && refOffset>0; the position-finder
projection carries *dstSign, the per-dst stored projections do NOT; reads drishti's compact per-8×8 saved
field at (y8,x8) directly since the producer pre-sampled the odd 2*y8+1 rows); av1_motion_field_estimation
(7.9.1 driver — init to -32768 sentinel, then LAST(-1) if useLast / BWDREF(+1) / ALTREF2(+1) / ALTREF(+1) /
LAST2(-1) with the useLast + refStamp bookkeeping; only BWDREF/ALTREF2/ALTREF decrement refStamp, ALTREF +
LAST2 gated on refStamp≥0); a reusable module-global MotionFieldMvs scratch ([8][h8][w8][2], resized only on
growth, header-stamped h8/w8); the frame-start hook in av1_tile_set_inter_ctx behind a use_ref_frame_mvs
gate. THE DIRECTIONAL TRAP (3-source reconciled vs a re-fetched spec 7.9 + dav1d refmvs.c): refToCur =
dist(OrderHints[src], OrderHint) and the inner refToDst = dist(OrderHint, OrderHints[dst]) use OPPOSITE
argument order. PROOF scripts/refs/{mv_projection_ref.py, tmvs_est_ref.py} spec-literal oracles + KATs: the
leaves KAT (half-boundary Round2Signed vs Round2 -16 vs -15, non-64-multiple negate-shift-negate 7 vs 6, all
window rejects); the estimation KAT (a 2-ref 8×8 scenario, every MotionFieldMvs cell vs the oracle — LAST→
(0,1), BWDREF→(2,3), ALTREF2 empty-field drives refStamp to -1 so ALTREF+LAST2 skip, their cells stay
sentinel) + a direct-call gate test (dimension / KEY / INTRA_ONLY / null / refOffset≤0 / |refToCur|>31).
MUTATIONS (13, all red): Div_Mult generator, Round2Signed->Round2, num clip, den clamp, negate-shift-negate;
both refStamp≥0 gates, useLast, *dstSign placement, both get_relative_dist arg orders, the >INTRA cell guard,
the KEY/dimension/null gates, the sentinel value, both posValid distance gates. Output-neutral (nothing reads
MotionFieldMvs yet — the full suite staying green IS the no-regression proof). 38 suites, **28,810** suite +
**1,140** fuzz assertions, all green. LESSONS: av1_round2 is ARITHMETIC (>>>) so it AGREES with round2_signed
except at half-boundaries (the witness needs a ties-away case); a would-contribute witness cell needs a SMALL
in-window MV or the projected position lands off-grid and get_block_position rejects it, masking a removed
refStamp/posValid gate (three mutations first SURVIVED for exactly this reason). Next: **Bite 3 = the
temporal scan (7.10.2.5/6) — read MotionFieldMvs in find_mv_stack, add temporal candidates + ZeroMvContext;
the output-CHANGING bite (needs a 2-frame fixture with a non-degenerate MotionFieldMvs).**

**0.7.102** — cut 2026-07-18, not yet tagged (user's git). **Temporal-MV PRODUCER (Bite 1 of 3).** The
first piece of temporal motion-vector prediction (the sole remaining find_mv_stack deferral). At inter-frame
decode end, the per-8x8 motion field is saved into the DPB slots the frame refreshes, so a FUTURE frame can
read it as temporal candidates (spec 7.19 storage + 7.20 save). OUTPUT-NEUTRAL — nothing reads it yet (the
projection/motion_field_estimation is 0.7.103, the scan 0.7.104), so every existing test staying green IS
the proof it changed no decode behavior. av1_mv.cyr: av1_mv_save_field — per 8x8 cell (y8,x8) samples the MI
grid at (2*y8+1, 2*x8+1); list0 THEN list1 NO-break (list1 OVERWRITES list0 when it also qualifies); keep
{ref,mv} iff ref>INTRA && get_relative_dist<0 (display-past) && |mv|<=4095 (REFMVS_LIMIT); else NONE. Compact
self-indexed field (AV1SMF_H8/W8/REF + variable MV). av1_frame.cyr: AV1REF_SAVED_MF per-slot storage
(AV1REF_SIZE 4096->4160) + av1_ref_saved_mf/set. av1_decode.cyr: the save hook in av1_frame_dec_finish (alloc
one buffer, reduce tile0's MI grid, alias into every refreshed slot; intra frames leave null). Reconciled vs
spec + a FETCHED dav1d refmvs.c (save_tmvs) + libaom (3-source understand workflow); drishti follows the
SPEC's per-ref pre-scaled MotionFieldMvs layout (0.7.103), NOT dav1d's single-field deferred scaling (a
documented future memory optimization). PROOF: scripts/refs/tmvs_save_ref.py spec-literal oracle + a 2x4-field
KAT with ASYMMETRIC witnesses (list1-overwrites-list0, list0-survives, future->NONE, intra->NONE, REFMVS
4095-kept/4096-rejected each component, 8x8 ODD-cell sampling vs an even decoy) asserted cell-by-cell + a
frame-level save-hook aliasing test. MUTATIONS (6): list preference, dist<0 direction, REFMVS boundary,
2*y8+1 sampling, hook-fires, buffer-aliasing. 38 suites, **28,516** suite + **1,140** fuzz assertions, all
green. Next: **Bite 2 = motion_field_estimation (7.9 — Div_Mult table + get_mv_projection + the projection
onto the 8x8 grid, order-hint scaled), still output-neutral; then Bite 3 = the temporal scan (7.10.2.5/6).**

**0.7.101** — cut 2026-07-18, not yet tagged (user's git). **OBMC — overlapped block motion compensation
(spec 7.11.3.9/10).** The SECOND inter motion mode after LOCALWARP: an OBMC block decodes to overlap-blended
pixels (its own MC smoothed at the top/left edges with the above-row + left-col neighbours). The mode-info
read (av1_read_use_obmc) was already wired; the inter tile decode used to REJECT AV1_MM_OBMC. av1_mc.cyr:
the Obmc_Mask table (av1_obmc_mask_tbl self-indexed [64], own-weights == 64 - dav1d_obmc_masks) +
av1_obmc_mask(len,i) + av1_mc_out_buf() (scratch handle). av1_intertile.cyr: av1_obmc_predict (two-pass) +
av1_obmc_overlap (per-neighbour MC via av1_mc_pred_core compound=0 + in-place blend Round2(m*own+(64-m)*nb,6),
above indexes mask by ROW/left by COL, table from NOMINAL extent). ABOVE pass gated mi_row>ROW_START AND
plane residual size>=BLOCK_8X8; LEFT pass gated mi_col>COL_START, NO size gate (the spec asymmetry — a 4:2:0
8x8-luma block blends its LEFT chroma neighbour but not ABOVE). Scan: odd cells x|1/y|1, step4=clip3(2,16,·),
up to min(4, mi_width/height_log2) inter neighbours, intra stepped over. Neighbour MC uses the NEIGHBOUR's
interp filters. Sequential in-place (above then left; top-left corner blends twice). AV1_MM_OBMC admitted in
decode+encode gates; an OBMC block is always single-ref/non-interintra/non-warp (read_motion_mode forces
SIMPLE otherwise) so it took the plain translation MC. Reconciled vs spec + cached dav1d recon_tmpl.c obmc +
libaom (3-source understand workflow; the one disagreement — chroma above-gate asymmetry — resolved to spec).
PROOF (tests/av1_intertile.tcyr + scripts/refs/obmc_ref.py spec-literal oracle, integer-MV MC = shift):
test_obmc_e2e (4-SB tile, BR OBMC decodes == ref checksum 375934 + spots); test_obmc_mask (62 entries vs
64-dav1d); test_obmc_chroma_gate (direct call, luma above blends / chroma above skipped / chroma left
blends); test_obmc_edge_gate (top/left-edge passes skipped). MUTATIONS (8): mask table, blend orientation,
mask orientation (row/col), blend rounding, chroma above-gate, above mi_row>ROW_START, left mi_col>COL_START,
the intra step-over / REF0>INTRA skip (a multi-neighbour A/B-intra/C/D scan; the unconditional advance is
the never-infinite-loop guard). THE REVIEW (2 dims, verify): NO shipped-code defects — spec-conformance
found []. 7 CONFIRMED findings, all test-COVERAGE gaps (minor/nit); closed the intra-step-over + the stale
comment; DEFERRED (code verified spec-correct, need new fixture infra): the x|1 odd-cell probe (4-wide
neighbour), step4 clip [2,16] bounds (4-/128-wide), mask-length NOMINAL-vs-clamped (non-8-aligned edge),
fractional-MV + neighbour interp filter (un-witnessable with integer MVs — 8-tap is identity), the top-edge
gate witness robustness (rides the OOB bounds-guard; a cross-tile row makes it deterministic). INCIDENT: a
review agent ran `git checkout` on the shared live tree (reverting uncommitted work) then restored from a
md5-verified backup — [[review-agents-need-worktree-isolation]] still applies; isolate review worktrees.
LESSON: gradient x+2y makes own==nb when dx+2*dy coincide -> a blend is secretly identity + witnesses
nothing; the ref-anchored checksum + DISTINCT-contribution MVs are the guard. 38 suites, **28,483** suite +
**1,140** fuzz assertions, all green. Next: **the temporal MV scan (7.10.2.5/6, needs the DPB's saved motion
fields), then compound GLOBAL_GLOBALMV + inter-intra warp-blend, then scaled-reference/BILINEAR MC.**

**0.7.100** — cut 2026-07-18, not yet tagged (user's git). **GLOBALWARP — the global-motion warp path
(spec 7.11.3.1 useWarp==2).** A single-ref GLOBALMV block whose reference carries a >TRANSLATION global
model now decodes to GLOBALLY-WARPED pixels (previously it fell through to a translation MC). Second warp
mode after LOCALWARP (0.7.98), reusing the whole verified warp pixel path. av1_mv.cyr:
av1_warp_model_from_global — gm_params[ref][0..5] ARE the warp matrix wmmat[0..5] (1<<16 precision, the
layout warp_estimation produces), so NO least-squares: copy them, set AV1WM_VALID=1 (a global model has no
estimation det — realizability rides entirely on AV1WM_SHEARVALID), run setup_shear -> globalValid.
av1_intertile.cyr: the per-block model build (LOCALWARP-only before) gains an else branch — a
SIMPLE-motion-mode single-ref (is_comp==0) block with YMode==GLOBALMV, GmType[ref0]>TRANSLATION,
!force_integer_mv, !is_scaled builds the global model + warp_valid=shearValid. The EXISTING per-plane gate
(warp_valid && nw>=8 && nh>=8) then warps with the model, else av1_mc_pred_block; block>=8x8 comes from the
nominal nw>=8 gate. Fallback: Mv[0] IS the global MV (assign_mv/GlobalMvs), so <8x8 / shearValid==0 / scaled
blocks translate correctly. Reconciled vs dav1d recon_tmpl.c gmv_warp_allowed (GmType>TRANSLATION &&
!force_integer_mv && shear-valid && !is_scaled; per-block imin(bw4,bh4)>1 && GLOBALMV) — GLOBAL warp does
NOT need allow_warped_motion (that gates LOCALWARP). Compound GLOBAL_GLOBALMV (each ref warped + blended) is
a DEFERRED follow-on (the compound path doesn't warp yet). PROOF (tests/av1_intertile.tcyr): a ROTZOOM
GLOBALMV block decodes == a DIRECT warp_pred_block on a model from the same gm_params (complementary oracle,
proves WIRING) AND != the global-MV translation; a GmType==TRANSLATION control that translates; a
NEWMV-with-rotzoom-GM control that still translates by its own MV; a warp_model_from_global KAT. MUTATIONS:
admit-TRANSLATION reddens the trans control; widen-YMode reddens the NEWMV control; warp_valid=0 reddens the
positive test; shearValid->VALID reddens the unrealizable control; drop-!force_integer_mv reddens the
force-int control; drop the inter-intra reject reddens the reject test. THE REVIEW (2 dims, adversarial
verify): 1 MAJOR — a GLOBALMV INTER-INTRA block whose global model would warp was silently translation-
blended (the is_ii dispatch precedes the warp gate; dav1d warps the inter part THEN blends). FIXED by
REJECTING it (is_ii && warp_valid -> DR_ERR_UNSUPPORTED; warp-blend deferred). Plus 4 coverage gaps: the
shearValid fallback, force_integer_mv, and the KAT's wmmat[3]/[4] are now witnessed; the !is_scaled conjunct
is UN-WITNESSABLE in the current codebase (both av1_warp_pred_block AND the translation av1_mc_pred_block
reject a scaled ref identically -> the gate is outcome-neutral until scaled-ref MC lands) so it's kept +
documented. LESSON: gm_params ARE wmmat (no least-squares); the global model's realizability rides on
setup_shear's shearValid, NOT the always-1 VALID; a would-warp block that a mode can't warp (inter-intra,
compound) must REJECT, not silently translate. 38 suites, **28,395** assertions + **1,140** fuzz, all green.
Next: **OBMC + the temporal
scan (needs the DPB's deferred saved MVs); compound GLOBAL_GLOBALMV warp; scaled-reference/BILINEAR MC.**

**0.7.99** — cut 2026-07-18, not yet tagged (user's git). **Closed the three deferred 0.7.98 useWarp-gate
coverage witnesses** (TEST-ONLY; shipped code unchanged, was already spec-correct). The 0.7.98 review flagged
three gate boundaries no SB-aligned fixture could distinguish; this bite builds a nested-SPLIT harness
(shared `itw_ctx420` 4:2:0 helper) to place small / edge-cut LOCALWARP blocks and witness each
(tests/av1_intertile.tcyr): `chroma8` — a 16×16-luma warp block whose chroma nominal `nw==8` **warps** (kills
F2b `(bw4*4)>>sx` → `>>(sx+1)`); `chroma4` — an 8×8-luma block whose 4×4 chroma **translates** while luma
warps (kills the loose `nw>=4` side); `edge_chroma` — a 16×16 block bottom-cut in a 32×28 frame (chroma
clamped 8×6, nominal `nh==8`) that still **warps the visible strip** (kills gating on the CLAMPED `w`/`h`).
Complementary-oracle (decoded == direct `warp_pred_block`, ≠ translation); neighbour MVs kept within the
add_sample threshold (16 for ≤16×16) so the models are genuine **num≥2** affines, not force-kept degenerates.
MUTATION-VERIFIED: `>>(sx+1)` reddens chroma8+chroma4+edge; the clamped-gate reddens edge only; `nw>=4`
reddens chroma4 only. 38 suites, **28,358** assertions + **1,140** fuzz, all green. LESSON: the warp-sample
add_sample threshold is `clip3(16,112,max(bw,bh))` — for any ≤16×16 block that clamps to **16**, so a
synthetic warp fixture needs neighbour MVs with `|Δmv| ≤ 16` (vs the block Mv) to produce VALID (non-degenerate)
samples; larger MVs are force-kept as a single degenerate sample (valid det≠0 but often shear-unrealizable at
8×8). Next: **GLOBALWARP (the global-motion warp path, useWarp==2 + gm_params), then OBMC + the temporal scan**.

**0.7.98** — cut 2026-07-18, not yet tagged (user's git). **LOCALWARP DECODES TO PIXELS (the warp milestone).**
A LOCALWARP inter block now decodes end-to-end to WARPED pixels: the inter tile decode builds the local warp
model (warp_estimation 0.7.93 → setup_shear 0.7.94) and predicts each plane through av1_warp_pred_block
(0.7.97). Wires the whole warp arc (samples→model→shear→filter→warped block). av1_intertile.cyr (spec 7.11.3.1
useWarp): the motion-mode gate admits SIMPLE + LOCALWARP (OBMC out); once per LOCALWARP block the model is
built from the tile's find_warp_samples output (AV1TILE_WS, filled during mode-info with the same Mv[0]);
per plane, dispatch av1_warp_pred_block iff warpValid AND the plane's NOMINAL block >= 8x8, else the existing
translation av1_mc_pred_block (a 4x4 chroma at 4:2:0 translates while luma warps). Encode gate mirrors.
Av1_WarpModelScratch (av1_mv.cyr) avoids per-block alloc. warpValid = AV1WM_VALID (estimation det!=0) &&
AV1WM_SHEARVALID, with setup_shear GATED on AV1WM_VALID. 0.7.98 LESSONS: (a) **THE det==0 GUARD IS
LOAD-BEARING and REACHABLE** — I mistakenly declared it un-witnessable (det>0 for any sample); the review
CORRECTED it: find_warp_samples FORCE-KEEPS its sole large-MV neighbour via the NUM=1 "no small MV, return
the first large one" case (av1_mv.cyr:1351), and that force-kept sample then FAILS warp_estimation's per-axis
LS_MV_MAX (256) inlier filter → all accumulators 0 → det==0 → AV1WM_VALID==0. So a LOCALWARP block whose Mv[0]
is >= 256 (1/8-pel) from every neighbour reaches det==0; without the guard the identity default passes
setup_shear (wmmat[2]=65536>0) → shearValid=1 → a spurious zero-motion COPY instead of the block-MV
translation. GENERAL: NumSamples (find_warp_samples output) != estimation inliers — the force-keep path admits
a sample that estimation's own LS_MV_MAX then discards. Do NOT declare a guard un-witnessable without BUILDING
the witness ("a test you have not seen fail is not evidence" applies to un-witnessability claims too). (b) the
useWarp >=8 gate uses the NOMINAL subsampled dims (bw4*4)>>sx, NOT the edge-clamped w/h; dispatch on the
clamped w/h (warp_pred_block crops). (c) GLOBALWARP (useWarp==2, gm_params) is a DEFERRED follow-on — a
GLOBALMV block with GmType>TRANSLATION currently gets motion_mode SIMPLE and decodes as translation. THE PROOF
(tests/av1_intertile.tcyr): a 4-SB tile where SB4 (LOCALWARP) finds SB2 (above)+SB3 (left) as samples and
decodes == a DIRECT warp_estimation+setup_shear+warp_pred_block on the post-decode samples (complementary
oracle: math pinned by the 0.7.93/94/97 Python refs; this proves WIRING) AND != translation MC; a det==0 case
(far-MV block → translation, witnessing the guard); a 4:2:0 chroma case (32x32 chroma warps == direct chroma
warp != translation). MUTATIONS: the gate, the >=8 dispatch, the warp-vs-translation branch, the estimation MV
arg, the setup_shear result, the AV1WM_VALID guard, and the chroma dispatch all go red. THE REVIEW (2 dims,
worktree-isolated, verified): 1 MAJOR (the det==0 guard reachability + the wrong "un-witnessable" doc) — FIXED
(the det==0 regression test); 2 MINOR test-coverage gaps DEFERRED (code verified-correct via 0.7.97 chroma
KATs + reconciliation): the 8x8-chroma-boundary gate / 4x4-chroma fallback (need a 16x16- / 8x8-luma block)
and the edge-overhang nominal-vs-clamped gate (need a non-multiple-frame block) — both need a SPLIT-partition
test harness (roadmap.md). Next: **GLOBALWARP (the global-motion warp path, useWarp==2 + gm_params), then OBMC
+ the temporal scan**. **Prior: WARP PREDICTION DRIVER (0.7.97).**

**0.7.97** — **WARP PREDICTION DRIVER.** The block-level warp
motion compensation (spec 7.11.3.5) — per 8x8 sub-block it projects the block centre through the warp model
to the integer source position + sub-pixel phase seeds, gathers the padded reference, calls the 0.7.96 kernel,
and writes back cropped. Handles luma + subsampled chroma. This assembles the whole warp pixel path
(model→shear→filter→warped-block); only the LOCALWARP tile-decode un-gate remains. Verified STANDALONE like
av1_mc_pred_block. av1_mc.cyr: av1_warp_pred_block(dst,ref,plane,x,y,w,h,wm) — loops 8x8 plane-pixel
sub-blocks; per sub-block src=(centre)<<sub → project through wmmat (av1_warp_model_param 0..5) → x4=>>>sub →
ix4=>>>16, sx4=&0xffff → seed mx=(sx4-4*alpha-7*beta)&~0x3f, my=(sy4-4*gamma-4*delta)&~0x3f; gather 15x15 at
(ix4-7,iy4-7) via the rect-copy+av1_mc_emu_edge pattern; call av1_warp_affine_8x8; write the 8x8 output back
CROPPED (only cells within the block → 4x4 chroma / non-mult-of-8 write just their valid cells). Chroma lifts
the centre <<sub into the LUMA grid the wmmat is defined in, drops the projection >>>sub back; shear+wmmat are
plane-independent (setup_shear derives them once). Reuses Av1_McRect/Gather/Out scratch + the emu_edge pattern
(like av1_mc_pred_core). Reconciled vs spec + the CACHED dav1d recon_tmpl.c warp_affine (authoritative) +
libaom; oracle scripts/refs/warp_driver_ref.py reuses the 0.7.96 kernel ref. 0.7.97 LESSONS: (a) the SEED FOLD
is -4*alpha-7*BETA (H pass spans 15 rows → beta origin i1=-7) and -4*gamma-4*DELTA (V pass spans 8) — the
7-vs-4 asymmetry is INVISIBLE to a symmetric model, so the KATs use an ASYMMETRIC model (alpha!=beta AND
gamma!=delta); the kernel starts its loop at r=0 so the DRIVER must pre-fold (kernel does NOT). (b) the &~0x3f
(=(0-64)) mask is a PROVEN no-op given setup_shear's mult-of-64 reduction (the sub-64 residue never carries in
the kernel's offs=64+Round2(tmx,10)); applied anyway to match dav1d/libaom + the ported kernel. (c) the
arithmetic >>>16/>>>sub matter ONLY when the projection goes NEGATIVE (a block near a frame edge projecting
off-frame) — witnessed by a strongly-negative-translation model (both axes off-frame); a logical shift there
yields a huge positive index. (d) the residue masks (sx4/sy4 & 0xffff) are only witnessed when the residue
>= 32768 (bit 15 set) — the neg model's residues cross it. (e) TWO self-inflicted KAT/model mismatches
surfaced mid-loop (updated the ref-port model + KAT but forgot the test's model builder) — the ref port is the
oracle only when the test's inputs match it EXACTLY. THE PROOF (tests/av1_mc_driver.tcyr): 9 KATs — luma
8x8/16x16/edge, 4:2:0 chroma 8x8 + a 4x4 crop, 12-bit, a strong-neg projection (arith-shift + residue-mask
witness), + a crop-confinement assert. MUTATIONS, 18 killed: the seed fold (each 4/7/4/4 factor via the
asymmetric model), the projection, the gather geometry (ix4-7/iy4-7/soff=48), all four arithmetic shifts, both
residue masks, the chroma <<sub lift, the write-back crop (row+col). THE REVIEW (2 dims, worktree-isolated,
patch-applied, verified): the per-8x8 derivation (vs cached dav1d) + memory-safety/chroma/gather/crop/off-frame
CLEAN — no findings in either dimension. Next: **un-gate LOCALWARP — wire warp_estimation→setup_shear→
av1_warp_pred_block into the inter tile decode so warped inter blocks decode to pixels; then OBMC + the
temporal scan**. **Prior: BLOCK WARP KERNEL (0.7.96).**

**0.7.96** — **BLOCK WARP KERNEL.** The per-8x8 warp
motion-compensation kernel (spec 7.11.3.5) — a two-pass separable filter applying the warp model's shear
params (0.7.94) through the Warped_Filters table (0.7.95) to produce warped reference pixels. The pixel stage
of the warp arc; the model→shear→filter→warp-pixels chain is complete bar the block-level driver. Verified
STANDALONE like put_8tap (0.7.58), NOT yet wired. av1_mc.cyr: av1_warp_affine_8x8(dst,doff,dstride, src,soff,
sstride, alpha,beta,gamma,delta, mx,my, bit_depth) — H pass: 15 rows x 8 cols into a signed `mid`, phase
mx+beta*r stepping +alpha per col, offs=64+av1_round2(tmx,10) (ARITHMETIC — tmx may go negative), the 8-tap
dot rounded av1_round2(.,7-ib); V pass: 8x8, phase my+delta*r stepping +gamma per col, dot over mid rows
r..r+7, dr_clip1(av1_round2(.,7+ib)). ib=4 (8/10-bit) / 2 (12-bit). Reuses av1_mc_8tap + av1_warp_filter_row
(0.7.95) + av1_round2 + dr_clip1 + the put_8tap mid scratch. Reconciled vs spec + the CACHED dav1d
warp_affine_8x8_c (authoritative) + libaom; oracle scripts/refs/warp_affine_ref.py ported from the dav1d
kernel. 0.7.96 LESSON / THE TRAP: the warp table is SPEC-LITERAL (rows sum to 128), so the rounds are the FULL
7±ib — NOT put_8tap's 6±ib (whose subpel table is HALVED to sum 64). Copying put_8tap's shift corrupts every
warped pixel; this is the single easiest transcription bug and it's why the reconciliation pinned it. THE
PROOF (tests/av1_mc_kernel.tcyr): 5 KATs vs the ref port — zero-shear identity (offs 64 → filter
[0,0,0,127,1,0,0,0]), a varying-offs shear, a NEGATIVE-phase case (offs Round2 goes negative → witnesses the
arithmetic shift), a 12-bit case (ib=2 → 5/9 rounds), a big-negative-shear case (offs down to 28). MUTATIONS,
11 killed: the 7±ib rounds, the arithmetic-shift offs (a logical shift both reds K4 AND OOB-crashes on the
negative-tmx K5), the per-row/per-col alpha/beta/gamma/delta step assignment, the signed mid, the -3/+3 tap
offsets, the offs centre (64), the 12-bit ib. THE REVIEW (2 dims, worktree-isolated, patch-applied, verified):
fixed-point (vs cached dav1d) + memory-safety CLEAN, no confirmed findings; the one raised concern (unchecked
offs into the 193-row table) REFUTED — the kernel deliberately trusts the driver's warpValid gate to keep
offs∈[0,192], exactly as it trusts the emu_edge gather for source coords and as put_8tap does (contract
correct + documented; enforcing the bound is the driver's job). Next: **the warp DRIVER (7.11.3.5 setup) —
the mx/my/dx/dy derivation from wmmat, the per-8x8 sub-block loop, the emu_edge gather, and the LOCALWARP
un-gate — which finally makes warped inter blocks decode to pixels; then OBMC + the temporal scan**. **Prior:
WARP FILTER TABLE (0.7.95).**

**0.7.95** — **WARP FILTER TABLE.** The Warped_Filters[193][8]
interpolation table (spec 7.11.3.5) — the signed 8-tap filter, indexed by the 1/64 sub-pixel warp offset
offs∈[0,192], that the warp block-predict (next bite) applies. Table-only bite (like Subpel_Filters 0.7.57),
NOT yet consumed. av1_mc.cyr: av1_warp_filter_tbl (lazy 193*8 i64 blob, 193 av1_wfill8 rows) +
av1_warp_filter(offs,tap)/_row(offs) accessors + the AV1_WARPEDPIXEL_PREC_SHIFTS(=64)/AV1_WARPEDDIFF_PREC_BITS
(=10) constants the coming offs map (offs=Round2(sx,10)+64) needs. dav1d stores this SPEC-LITERAL (positive
centre, each row sums to +128=1<<FILTER_BITS) — UNLIKE its NEGATED resize / HALVED subpel neighbours in the
same file (a convention trap, flagged inline). THE DATA PATH: a web-enabled multi-source pass established the
table is a RAW CONSTANT with NO generation formula (all of spec/libaom/dav1d carry it literally), and
re-fetched dav1d src/tables.c to disk; the 1544 signed values were MACHINE-GENERATED (never hand-typed) from
that MD5-verified source (MD5 c764ff07aecee5aba2348072f285059b) — dav1d writes some negatives as '- N'
(minus-space), which a naive tokenizer silently drops (corrupts ~17 rows), so a DETERMINISTIC parser gated on
the digest is the only safe path. Oracle scripts/refs/warp_filter_ref.py (embeds the table + asserts the MD5).
THE PROOF (tests/av1_mc.tcyr): every one of 193 rows sums to 128 (catches a transpose); reversal symmetry
row[i]==reverse(row[192-i]) i=1..191 with row[192]==row[191] (guard-tail sentinel, NOT mirror of row 0);
anchor spot values at PINNED [row][tap] offsets vs the ref port (incl. a raw-blob absolute-offset read that
can't hide a consistent accessor bug); a full position-weighted checksum 19083838 over all 1544 coeffs.
MUTATIONS: a single-coefficient change AND a row-sum-preserving within-row swap both go red. THE REVIEW
(worktree-isolated, patch-applied): accessor/storage offsets, the exact alloc size (12352 bytes), OOM
handling, the block_warp constants, no symbol shadowing, the ref-port MD5 anchor — all CLEAN, no defects
(the reviewer's own accessor mutation confirmed the tests are non-circular). 0.7.95 LESSON: for a big
constant table with no in-session source and NO formula, the disciplined path is not memory-reconstruction
(hallucination risk for 1544 values) — it is re-FETCH the reference source, verify a cryptographic digest
(MD5), then MACHINE-GENERATE both the Cyrius and the ref port from that verified file, gating on the digest +
structural invariants; a from-memory 8-tuple is never trusted. Next: **block_warp (7.11.3.5) — the per-pixel
warp using the model+shear+filter, then un-gate LOCALWARP; then OBMC + the temporal scan**. **Prior: SETUP
SHEAR (0.7.94).**

**0.7.94** — **SETUP SHEAR (warp shear params + realizability).**
The process (spec 7.11.3.6) turning a warp model's wmmat[2..5] into the four shear params alpha/beta/gamma/
delta + a warpValid flag — the second warp step, consumed by block_warp (7.11.3.5, later). Reuses the 0.7.93
resolve_divisor/Div_Lut verbatim (small delta); pure derivation (no bitstream symbol → no encoder inverse),
NOT wired to pixels yet. Un-defers the shear-realizability rejection 0.7.93 flagged. av1_mv.cyr adds
av1_setup_shear: guard wmmat[2]<=0 (is_affine_valid — also protects resolve_divisor from FloorLog2(0)) →
resolve_divisor on wmmat[2] (the x-scale, NOT the determinant; RAW output, UNLIKE warp_estimation's
-WARPEDMODEL_PREC_BITS rescale — divShift>=14 so no <0 fixup) → alpha0/beta0/gamma0/delta0 (INT16-clamped;
v=m4*65536, w=m3*m4) → reduce each to a multiple of 1<<WARP_PARAM_REDUCE_BITS(=64) → warpValid=0 if
4|alpha|+7|beta|>=65536 or 4|gamma|+4|delta|>=65536. Av1WarpModel grew (AV1WM_ALPHA..DELTA + a separate
AV1WM_SHEARVALID; SIZE 56→96) + accessors. 3-source reconciled (spec+libaom+dav1d, UNANIMOUS;
scripts/refs/setup_shear_ref.py the oracle, reusing the checksum-pinned resolve_divisor). THE PROOF
(tests/av1_mv.tcyr): 17 KATs — identity→all-zero+valid, three real warp_estimation outputs (4 distinct
params each), the wmmat[2]<=0 guard (zero AND negative), the reduce (100→128), both INT16 clamp bounds, and
BOTH realizability checks pinned from BOTH directions at their exact boundaries (each of the 4/7/4/4 coeffs +
the >= comparator). MUTATIONS, 19 killed (divisor input / raw-shift / every param formula / reduce / all
four validity coeffs increase AND decrease / both >= / guard); lone survivor a PROVABLY-EQUIVALENT ±1 in the
INT16 clamp bound (the granularity-64 reduce absorbs it — clamp PRESENCE separately witnessed by removing it).
THE REVIEW (2 dims, worktree-isolated, patch-applied, verified): fixed-point + memory-safety CLEAN; one MINOR
coverage gap found + closed (the gamma/delta coeffs were un-witnessed for an INCREASE — the sole reject case
bad_gd is symmetric; added gamma/delta boundary cases AND, by the same logic, the alpha/beta increase cases —
shipped code was spec-correct). 0.7.94 LESSON: a SYMMETRIC boundary case (gamma==delta) pins neither
coefficient's magnitude; a validity coefficient needs BOTH a reject-at-exact-boundary case (catches decrease)
AND a pass-just-under-boundary case (catches increase) to be fully mutation-covered. Next: **the warp-filter
table (dav1d_mc_warp_filter[193][8]) + block_warp (7.11.3.5) + OBMC + the temporal scan**. **Prior: WARP
ESTIMATION (0.7.93).**

**0.7.93** — **WARP ESTIMATION (local warp model).** The
least-squares solve (spec 7.11.3.8) turning the find_warp_samples CandList into a 6-param affine
LocalWarpParams[0..5] + LocalValid — the direct consumer of the 0.7.79 warp-sample leaves, and the first
half of the warp arc. Like setup_global_mv it is a pure DERIVATION (no bitstream symbol → no encoder
inverse) and NOT yet wired to pixels (LOCALWARP motion stays gated in av1_intertile until the warp-MC bite
that needs the warp-filter table). av1_mv.cyr adds: av1_div_lut_tbl (the lazy 257-entry Div_Lut[i]=round(2^22/
(256+i)); anchors [0]=16384=2^14, [256]=8192=2^13, exact — no tie ever occurs) + av1_resolve_divisor (7.11.3.7:
n=FloorLog2(|D|), f=(n>8)?Round2(e,n-8):e<<(8-n), divShift=n+14, divFactor=±Div_Lut[f], f∈[0,256] guarded);
the LS macros av1_ls_square/product1/product2 (Tikhonov +1, exact >>2 — arithmetic >>> on the SIGNED product
numerators); av1_warp_mult_clip (Round2Signed(v*divFactor, divShift) then a diag/nondiag Clip3 window); and
av1_warp_estimation (accumulate symmetric 2x2 A + Bx/By over samples with the LS_MV_MAX per-sample guard →
det==0 is the SOLE LocalValid=0 exit → Cramer solve scaled by resolve_divisor → diag clamp near 1<<16 /
nondiag near 0 → translation wmmat[0..1] anchored at the block center, ±2^23 clamp). CandList is ALREADY
1/8-pel (add_sample) so NO extra *8. Av1WarpModel record (av1_warp_model_new/_valid/_param). 4-source
reconciled (spec+libaom+dav1d+focused-divisor → adjudication; scripts/refs/warp_estimation_ref.py the
spec-literal oracle). DEFERRED (un-witnessable by a self-consistent test → conformance-vector bite,
roadmap "warp"): the libaom LS_MAT_MIN/MAX accumulator clamp (existence+bounds unverified) and the
shear-realizability rejection (get_shear_params ~7.11.3.6, a SEPARATE post-process). THE PROOF
(tests/av1_mv.tcyr): Div_Lut via 9 anchored spot values + a full 257-entry sum/position-weighted-checksum
digest (defeats the circular per-entry accessor test); resolve_divisor over 2^n±1 boundaries (witnessing
f=0, f=256, negative D); 13 warp KATs vs the ref port — identity/translation, a clean 4-distinct-param
affine, the LS_MV_MAX guard (BOTH horizontal and vertical conjuncts), all four clamp bounds (diag
57345/73727, nondiag ±8191), the divShift<0 rescale branch (det=1 single sample), the ±2^23 translation
clamp, a single-sample + a small negative-product case, det==0→invalid. MUTATIONS, 16 killed (Div_Lut
rounding / resolve shift+branch / every LS macro / Cramer products / both clamp bounds / guard / translation
anchor / invalidation / signed rounding); the lone survivor is a PROVABLY-EQUIVALENT >-vs->= at the n=8
divisor branch (e<<0 == Round2(e,0) == e). 0.7.93 LESSON: symmetric 4-sample vectors MASKED the
arithmetic-shift + signed-rounding bugs via an i64-overflow coincidence (two ~4.6e18 logical-shift terms
summed just past i64-max and wrapped back to the correct value) — a SINGLE-sample and a small 2-sample case
witness them cleanly. THE REVIEW (3 dims, worktree-isolated, patch-applied, every finding verified): math +
memory-safety CLEAN; three MINOR test-coverage gaps found + closed (divShift<0 branch, the vertical guard
conjunct, the translation-clamp bound MAGNITUDE — all with the shipped code confirmed spec-correct; new
K/CV/TC KATs now fail red under the matching mutation). Next: **warp MC (the warp-filter table) + OBMC + the
temporal scan**. **Prior: WEDGE INTER-INTRA (0.7.92).**

**0.7.92** — **WEDGE INTER-INTRA PREDICTION.** The second (and
final) interintra variant: a single-ref inter block with the interintra flag AND wedge_interintra==1 blends
its inter MC with an INTRA prediction through a WEDGE mask from the compound codebook (0.7.90) rather than a
smooth mask (0.7.91) — completing the masked-interintra family (every AV1 interintra mode now decodes). Small
delta reusing verified machinery. av1_mc.cyr: av1_mc_pred_interintra gains is_wedge/wedge_idx params — the
WEDGE branch builds the codebook mask on LUMA only (plane 0) at the NOMINAL block size with wedge_sign forced
0 (interintra never signals a sign) and CHROMA SUBSAMPLES the plane-0 mask via av1_diffwtd_mask_at (exactly
like compound wedge — UNLIKE smooth, which regenerates per plane); the blend is the same FINAL-precision
Round2(m*intra + (64-m)*inter, 6) — no ib, no Clip1 — reused verbatim from 0.7.91. Un-gate both lanes for
WEDGE interintra (the wedge_interintra==0 reject removed from both; overhang + non-SIMPLE motion stay, gates
still mirror); the decode dispatch threads av1_interintra_wedge + av1_interintra_wedge_idx (wedge_idx is
entropy-bounded [0,15] → shape*16+idx ∈ [0,47] never OOBs the 48-entry codebook). 3-source verified
(interintra.md §3). THE PROOF (tests/av1_mc_driver.tcyr, av1_intertile.tcyr): a LUMA orchestration test
building the wedge mask INDEPENDENTLY (av1_wedge_mask_build) + integer-MV-0 inter + av1_intra_predict into a
temp frame, recomputing the blend (catches wrong mask/shift/operand without sharing the MC blend); a 4:2:0
CHROMA case whose oracle 2x2-averages the luma mask MANUALLY (independent of av1_diffwtd_mask_at), run over
BOTH a row-invariant VERTICAL wedge (idx6) AND an OBLIQUE wedge (idx1=O63, band crossing the bottom-right
quadrant) so the plane==0 build-guard is witnessed; a decode round-trip (32x32 via SPLIT, WEDGE idx0/idx6)
equal to the oracle AND differing from pure-inter. Mutations, 0 survivors: the is_wedge mask-build branch,
the subsampled chroma read, the forced wedge_sign, the decode-dispatch wedge threading, and the plane==0
build guard each go red. THE REVIEW (worktree-isolated, patch-applied): the wedge-interintra delta CLEAN —
build/read branches match, plane-0-before-chroma ordering guaranteed by the decode plane loop (Av1_McMask
survives the intervening intra/inter calls), gates mirror + codebook index bounded, SMOOTH unregressed; no
correctness/memory-safety findings. One mutation-coverage gap flagged + closed: the sole chroma case (idx6)
is a row-invariant wedge whose constant bottom-right quadrant lets a mask erroneously rebuilt-at-chroma
reproduce the correct subsamples — the added oblique idx1 case makes the plane==0 guard fail red under
mutation. Next: **OBMC/warp + the temporal scan**. **Prior: SMOOTH INTER-INTRA (0.7.91).**

**0.7.91** — **SMOOTH INTER-INTRA PREDICTION.** A single-ref
inter block with the interintra flag (ref1==INTRA) blends its inter MC prediction with an INTRA prediction
of the same block via a smooth mask. Unlike compound (two inter preds at intermediate precision), inter-intra
crosses the inter/intra boundary — the keyframe intra predictor (av1_intra_predict) is invoked UNCHANGED from
the inter tile path. Scope = SMOOTH interintra (II_DC/V/H/SMOOTH); WEDGE interintra deferred to 0.7.92; a
frame-edge OVERHANG is refused (av1_intra_predict writes the NOMINAL block, no write-clamp). av1_mc.cyr:
av1_ii_weight (the 128-entry Ii_Weights_1d monotone 60..1 table) + av1_ii_smooth_mask_build (sizeScale =
128/Max(w,h); II_DC=flat 32, II_V=row Ii_Weights[i*scale], II_H=col [j*scale], II_SMOOTH=[Min(i,j)*scale];
m weights INTRA). CHROMA REGENERATES the mask at the chroma block size, NOT subsampled from luma (a cross-
source discrepancy — 4:2:0 32x32 V chroma row0 = 60, not the averaged 56). av1_mc_pred_interintra: inter ->
Av1_McOut at FINAL precision (av1_mc_pred_core compound=0), intra -> frame (av1_intra_predict; II_SMOOTH->
SMOOTH_PRED=9), blend reads intra back = Round2(m*intra + (64-m)*inter, 6) — NO ib, NO Clip1 (both preds at
pixel precision, convex combo stays in range; the compound ib+6/Clip1 combine would corrupt it). Un-gate both
lanes for SMOOTH interintra. 3-source verified (interintra.md). THE PROOF (tests/av1_mc_driver.tcyr,
av1_intertile.tcyr): the smooth mask vs a 28-checksum pin (size x mode) vs the new spec-literal
scripts/refs/interintra_ref.py; an orchestration test running av1_intra_predict INDEPENDENTLY into a temp
frame + integer-MV-0 inter (== ref pixel) + the ref-verified mask, recomputing the blend (catches wrong
shift/clip/operand-order without sharing the blend); a 4:2:0 CHROMA case witnessing regeneration; a decode
round-trip (32x32 via SPLIT, DC/V/SMOOTH) equal to the oracle AND differing from pure-inter. Mutations, 0
survivors: the blend shift/operand/mode-remap/chroma-regen/inter-precision die in the driver's INDEPENDENT
orchestration oracle (the round-trip shares av1_mc_pred_interintra), the decode dispatch dies in the
round-trip. THE REVIEW (2 dims, worktree-isolated): math CLEAN (Ii_Weights + V/H orientation + chroma regen +
blend precision + mode remap), invocation+gate+memory-safety CLEAN (av1_intra_predict arg positions +
avail_u/avail_l wiring, intra-then-inter-then-blend ordering no-clobber, overhang gate sufficient incl.
chroma, buffers bounded). One CONFIRMED finding FIXED: (F1) the encode gate mirrored the wedge+motion rejects
but NOT the decode's overhang reject (an overhanging interintra block would encode but decode-reject) — the
encode gate now mirrors it in full. Next: **WEDGE interintra (0.7.92), OBMC/warp + the temporal scan**.
**Prior: COMPOUND WEDGE (masked) (0.7.90).**
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

## Source (40 `[lib]` modules, dependency order)

| Module | Family | Surface |
|--------|--------|---------|
| `src/drishti.cyr` | core `dr_` | error record + code bands, `drishti_version()` → 806, format sniff |
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
| `src/av1_mv.cyr` | `av1_` | motion-vector prediction (spec 7.10.2) — **foundation** (0.7.62): **Av1Mv** (row,col) MV representation (1/8-luma-sample units; av1_mv_new/row/col/set); **av1_lower_mv_precision** + **av1_lower_mv_comp** (7.10.2.10); **av1_setup_global_mv** (7.10.2.1 — the global-motion MV candidate: 2×3 affine projection of the block center through gm_type/gm_params, rounded with the symmetric av1_round2_signed). **candidate stack** (0.7.63): **Av1MvStack** (RefStackMv[8][2][2] + WeightStack[8] + NumMvFound/NewMvCount; av1_mv_stack_new/reset/num/newmv_count/weight/row/col); **av1_mv_stack_add** (dedup-or-append core of search stack 7.10.2.8/9 — lower + weight-accumulate-or-append capped at 8 + NewMvCount); **av1_mv_stack_sort** + **_swap** (stable descending sort 7.10.2.13); **av1_has_newmv**. **spatial scans** (0.7.64): **Av1MiRec** per-4×4 MI grid (av1_mv_grid_new/cell/set) + **Av1MvCtx** scan context (av1_mvctx_* + is_inside); **av1_mv_scan_row**/**_scan_col** (7.10.2.2/3 — end4/parity/len-step/useStep16/is_inside break); **av1_mv_scan_point** (7.10.2.4 — corner probe gated on is_inside+avail); **av1_add_ref_mv_candidate** (7.10.2.7) + **av1_mv_search_stack**/**_compound_search_stack** (7.10.2.8/9 — is_inter + single/compound ref-match dispatch + GLOBALMV substitution). **find_mv_stack** (0.7.65): **av1_find_mv_stack** (7.10.2 driver — scan sequence + REF_CAT_LEVEL bonus + Close/TotalMatches + two-region sort); **av1_mv_extra_search**/**_add_extra_mv_candidate**/**_store_combined** (7.10.2.11/12 — fill-to-2 + sign-bias + global fill + compound combine); **av1_mv_context_and_clamping** (7.10.2.14 — DrlCtxStack/New/Ref/ZeroMvContext); **av1_clamp_mv_row**/**_col** (spec 6). The MI grid is populated by inter mode-info; the temporal-MV arc is COMPLETE (av1_mv.cyr also holds av1_mv_save_field 0.7.102, Div_Mult/av1_get_mv_projection/av1_motion_field_estimation 0.7.103, av1_temporal_scan/av1_add_tpl_ref_mv 0.7.104, + the warp models av1_warp_estimation/av1_setup_shear/av1_warp_model_from_global) — no find_mv_stack deferral remains  **MI-GRID POPULATION** (0.7.74): **av1_mi_store_mode** (5.11.4 storage loop 1 — YModes/RefFrames/Mvs across the block's bw4 x bh4 footprint; Mvs only when inter, Mvs[1] only when compound) + **av1_mi_store_final** (loop 2 — IsInters/MiSizes + the `avail` marker); writes CLIPPED to the grid (blocks may overhang the frame edge) + a MiSize guard before the Num_4x4_Blocks_* table load. This CLOSES the producer->consumer loop: the scans above now read what the decoder stored  (0.7.77) Av1MiRec grew 80→112 with the inter-only CompGroupIdxs / CompoundIdxs / InterpFilters[0..1] the neighbour CDF contexts read, written by av1_mi_store_mode exactly where spec 5.11.4 loop 1 does (CompGroupIdxs/CompoundIdxs gated on !use_intrabc; InterpFilters not)  **WARP SAMPLES** (0.7.79): **av1_has_overlappable_candidates** (8x8-granularity x4|1 probe, frame-clipped) + **av1_warp_add_sample** (7.10.4.2 — block-top-left snap, the Clip3(16,112,..) MV-delta threshold, the keep-the-first-large special case) + **av1_find_warp_samples** (7.10.4.1) + the Av1WarpSamples record — the leaves read_motion_mode's OBMC/LOCALWARP gating needs |
| `src/av1_intermode.cyr` | `av1_` | inter mode-info (spec 5.11.23+), bitstream-read layer — **MV component decode** (0.7.66): the nine MV CDF tables (mv_joint/sign/class/class0_bit/class0_fr/class0_hp/fr/hp/bit, §10 defaults in a 286-entry [MvCtx][comp] context; av1_mvcdf_new/blob + accessors); **av1_read_mv**/**_read_mv_component** (5.11.32 — mv_joint dispatch → per-component sign/class/magnitude split, force_int/allow_hp defaults, PredMv add) + paired encoder. **single-prediction mode reads** (0.7.67): the New_Mv/Zero_Mv/Ref_Mv/Drl_Mode CDFs (§10, 51-entry blob av1_imcdf_new/blob); **av1_read_inter_mode** (new_mv/zero_mv/ref_mv → NEWMV/GLOBALMV/NEARESTMV/NEARMV via the find_mv_stack contexts); **av1_read_drl_idx** (RefMvIdx via drl_mode + DrlCtxStack + NumMvFound); **av1_assign_mv_single** (PredMv from RefStackMv[pos]/GlobalMvs + read_mv for NEWMV → the block's Mv) + paired encoders — composes find_mv_stack (0.7.65) + read_mv (0.7.66). **reference-selection reads** (0.7.68): the Is_Inter[4]/Single_Ref[3][6] CDFs (§10, 66-entry blob av1_refcdf_new/blob); **av1_read_is_inter** (the @@is_inter symbol 5.11.30) + **av1_read_single_ref** (the single_ref_p1..p6 tree → RefFrame[0]∈LAST..ALTREF 5.11.25, RefFrame[1]=NONE) + paired encoders; the neighbour-count CDF contexts (8.3) are caller inputs. **compound references** (0.7.69): the Comp_Mode[5]/Comp_Ref_Type[5]/Comp_Ref[3][3]/Comp_Bwd_Ref[3][2]/Uni_Comp_Ref[3][3] CDFs (§10, blob 66→168); **av1_read_comp_mode** (single vs compound) + **av1_read_compound_ref** (comp_ref_type → unidir 4 same-direction pairs / bidir fwd RefFrame[0] + bwd RefFrame[1], all 16 pairs 5.11.25) + paired encoders. **compound mode path** (0.7.70): the 8-symbol **Compound_Mode** CDF (§10, blob 51→123) + Compound_Mode_Ctx_Map; **av1_read_compound_mode** (compound_mode → YMode); **av1_get_mode** (per-list mode split); **av1_assign_mv_compound** (two-list assign via per-list av1_assign_mv_list) + read_drl_idx extended to compound. **interp filter + motion mode** (0.7.71): the 3-symbol **Interp_Filter[16][4]** CDF (§10, blob 123→341) + **av1_read_interp_filter**; the MiSize-indexed motion-mode reads **av1_read_motion_mode** (SIMPLE/OBMC/LOCALWARP, Motion_Mode[22][4]) + **av1_read_use_obmc** (binary, Use_Obmc[22][3]) + paired writers (av1_imcdf_interp/motionmode/useobmc accessors + av1_imcdf_put3). **inter-intra reads** (0.7.72): a NEW **av1_iicdf** blob (464 i64) tiling the Inter_Intra[3]/Inter_Intra_Mode[3]/Wedge_Inter_Intra[22]/Wedge_Index[22][16] CDFs (§10); **av1_read_interintra** (binary) + **av1_read_interintra_mode** (4-sym II_DC/V/H/SMOOTH), both ctx=Size_Group[MiSize]-1 (reusing av1_size_group); **av1_read_wedge_interintra** (binary) + **av1_read_wedge_index** (16-sym, MiSize-indexed, shared with compound_type) + paired writers (av1_iicdf_put16 + av1_iicdf_wedge_unif). **read_compound_type** (0.7.73): the full 5.11.29 DRIVER — **av1_read_comp_group_idx**/**av1_read_compound_idx** (binary, 6 ctx) + **av1_read_compound_type_sym** (binary, COMPOUND_TYPES=2, symbol IS the enum) + **av1_read_compound_type** composing them with the shared wedge_index + wedge_sign/mask_type L(1) literals (Wedge_Bits[MiSize]==0 forces DIFFWTD; the non-compound path reads NO symbol — compound_type falls out of interintra/wedge_interintra); Wedge_Bits[22] + the av1_comptype_* record; blob 464→566; paired encoder-inverse. EVERY 5.11.23 INTER SYMBOL READ IS IN — but the 5.11.15 OUTER DISPATCH still rejects segmentation / delta-q / delta-lf / the intra fork (av1_intermode.cyr), so an inter FRAME does not decode  **NEIGHBOUR CDF CONTEXTS** (0.7.75): **av1_nbctx_setup** (5.11.15 — the eight Above/Left RefFrame/Intra/Single values from the MI grid; unavailable defaults are ASYMMETRIC: RefFrame[0]→INTRA_FRAME, RefFrame[1]→NONE) + **av1_check_backward** / **av1_count_refs** / **av1_ref_count_ctx** (§9 leaves) + **av1_is_inter_ctx** and **av1_comp_mode_ctx** — the FIRST un-deferral: these now feed av1_read_is_inter (0.7.68) / av1_read_comp_mode (0.7.69) for real. The single_ref/comp_ref family + the contexts needing CompGroupIdxs/CompoundIdxs/InterpFilters are later bites  **REFERENCE-CONTEXT FAMILY** (0.7.76): the seven ref_count_ctx derivations (**av1_comp_ref_ctx** / **_p1** / **_p2**, **av1_comp_bwdref_ctx** / **_p1**, **av1_single_ref_p1_ctx**, **av1_uni_comp_ref_p1_ctx**) + **av1_is_samedir_ref_pair** + **av1_comp_ref_type_ctx** (the only non-count one) + the fillers **av1_single_ref_ctxs** / **av1_comp_ref_ctxs**, which populate the refctx[6] / Av1CompCtxIdx records av1_read_single_ref (0.7.68) / av1_read_compound_ref (0.7.69) take — the reference reads' contexts are no longer caller inputs. single_ref_p2..p6 / uni_comp_ref / uni_comp_ref_p2 are the spec's ALIASES, expressed by CALLING the aliased fn so they cannot drift  **THE LAST CDF CONTEXTS** (0.7.77): Av1NbCtx grew 80→144 caching the neighbour CompGroupIdxs/CompoundIdxs/InterpFilters; **av1_comp_group_idx_ctx** (clamped to 5), **av1_compound_idx_ctx** (ALTREF bump 1 not 3, NO clamp; fwd_eq_bck is caller frame-state) and **av1_interp_filter_ctx** (4-wide bank by (dir, is-compound) + the neighbours' agreed filter type). **EVERY inter CDF context is now derived** — the caller supplies only AvailU/AvailL + the order-hint distances, as the spec does  **THE GATING ORCHESTRATORS** (0.7.78): **av1_read_interintra_mode** (the full 5.11.28 gate + the Av1InterIntraRec side-effects; leaf renamed av1_read_interintra_mode_sym to break a SILENT duplicate-name shadow) + **av1_needs_interp_filter** + **av1_read_interp_filters** (the 5.11.23 tail: SWITCHABLE / dual-filter / mirror / EIGHTTAP) + paired inverses — the gating 0.7.71/0.7.72 left to 'the caller'  **READ_MOTION_MODE DRIVER** (0.7.80): **av1_read_motion_mode** (the full 5.11.27 gate over the 0.7.71 _sym leaves + the 0.7.79 warp-sample leaves + av1_is_scaled; early SIMPLE consumes NO symbol; find_warp_samples always runs before the @@use_obmc-vs-@@motion_mode split) + **av1_write_motion_mode** (gate-replaying inverse); the 0.7.71 leaves renamed av1_read/write_motion_mode_sym  **READ_REF_FRAMES DISPATCHER** (0.7.81): **av1_read_ref_frames** (5.11.25 — skip_mode/SkipModeFrame + the two segmentation fixed paths + the reference_select && min(bw4,bh4)>=2 comp_mode gate into the 0.7.68/0.7.69 trees with derived contexts; persistent ctx scratch av1_rrf_scratch) + **av1_write_ref_frames** (gate-replaying inverse)  **INTER_BLOCK_MODE_INFO** (0.7.82): **av1_inter_block_mode_info** (5.11.23, THE ORCHESTRATOR — composes read_ref_frames → find_mv_stack (refs + global-MV candidates installed here) → YMode → DRL → assign_mv → interintra (side-effect applied between stages) → motion_mode (post-ii ref1) → compound_type → the interp tail; Av1InterBlock output record) + **av1_write_inter_block_mode_info** + the av1_write_assign_mv_* family  **INTER_FRAME_MODE_INFO** (0.7.83): the Skip_Mode CDF + **av1_read_skip_mode(_sym)** (5.11.11 full gate) + **av1_read_is_inter** (5.11.15 selection; leaf renamed _sym) + **Av1BlockInfo** + **av1_inter_frame_mode_info** (the outer dispatch: nbctx preamble → skip_mode → skip → cdef splice → is_inter → the 5.11.23 fork; segmentation/delta/intra-fork gate UNSUPPORTED consuming nothing, roadmap.md) + inverse |
| `src/av1_dpb.cyr` | `av1_` | decoded-picture buffer / ref-frame ring (spec 7.20 + 7.21) — **Av1Dpb** 8-slot pixel FrameStore (av1_dpb_new/frame/valid/count); **reference frame update** (7.20): av1_dpb_store (pixel half — stores a decoded frame into every refresh_frame_flags slot) + av1_dpb_update (full process: pixel store + the metadata half av1_frame_update_refs); **reference frame loading** (7.21): av1_dpb_load (serves show_existing_frame from FrameStore[frame_to_show_map_idx]); **av1_dpb_ref_frame** (the inter/MC hook: LAST..ALTREF → ref_frame_idx → the stored DrFrame av1_mc_pred_block reads); **av1_decode_stream** (multi-frame OBU walk — decodes every coded frame into the DPB, serves show_existing, returns the last shown frame; av1_decode_obus stays the single-frame entry). PIXEL ring only; the saved-MV half is IN (AV1REF_SAVED_MF in av1_frame.cyr + the av1_frame_dec_finish save hook, 0.7.102); saved-CDF/segment-id + full 7.21 metadata reload remain later bites |
| `src/av1_cdef.cyr` | `av1_` | CDEF (7.15) — kernels (direction/variance + constrain + tap filter + tables) **and the driver**: av1_cdef_process (outer loop) / av1_cdef_block (7.15.1 copy + idx/skip gates + var-scaled luma + chroma) + av1_cdef_frame_new + av1_cdef_coverage_ok (MI-grid guard: rejects, never OOBs). Consumes the CdefIdx grid + Skips + fh strengths |
| `src/av1_superres.cyr` | `av1_` | superres upscaling (7.16) — Upscale_Filter[64][8] (dav1d resize filter negated to spec form; row-sum/integer-pel/mirror + per-phase position-checksum verified) + av1_superres_filter_pixel (one sample: phase/base/edge-clamp + Round2(sum,7) + Clip1) + av1_superres_upscale_row (the row loop, == dav1d resize_c) + av1_superres_step / av1_superres_x0 (dx/mx0 geometry, == dav1d scale_fac + get_upscale_x0) + av1_superres_upscale_frame (per-plane/row upscale into a new frame) + av1_superres_upscale_new (used by the in-loop pipeline to lift a downscaled frame to UpscaledWidth between CDEF and LR) — all reference-confirmed against dav1d; superres decodes end-to-end |
| `src/av1_mc.cyr` | `av1_` | inter prediction (motion comp) — Subpel_Filters[6][15][8] (dav1d_mc_subpel_filters: REGULAR/SMOOTH/SHARP + 2 w≤4 variants + scaled-bilinear; dav1d convention, rows sum 64; verified by row-sum/mirror-symmetry/independent position-checksum) + av1_subpel_filter accessor + **av1_mc_put_8tap** (2-pass 8-tap MC kernel == dav1d put_8tap_c: integer/H/V/H+V, dav1d intermediate precision, persistent mid scratch, reference-tested) + **av1_mc_emu_edge** (frame-boundary block fetch == dav1d emu_edge_c: out-of-frame reads clamp to the edge, reference-tested) + **av1_mc_pred_block** (the MC driver, spec 7.11.3.1 steps 10+13: unscaled 1/16-pel MV split av1_mc_pos16 → emu_edge gather → put_8tap → Clip1 into a DrFrame; single-ref/translation-only/non-compound/unscaled base case, scaled/BILINEAR MC rejected (compound + warp now in); spec-literal-reference-tested; 5-slice review → 3 defects fixed) + persistent scratch (av1_mc_drv_scratch / av1_mc_mid_scratch). now also ALL compound (AVERAGE/DISTANCE/DIFFWTD/WEDGE) + inter-intra + all four warp forms (av1_warp_affine_8x8/av1_warp_pred_block/_gen + warp-filter table) + OBMC + av1_mc_pred_compound; every MC geometry, motion mode, compound/masked form, interpolation filter and reference geometry is in (scaled-reference MC wired 0.7.110, BILINEAR 0.7.108); an inter FRAME still does not decode, because segmentation / delta-q / delta-lf / an intra block inside an inter frame all reject the tile |
| `src/av1_intertile.cyr` | `av1_` | INTER tile decode (0.7.84+) — **av1_decode_block_inter** (the per-block inter prediction driver: sets up the MV context + inter mode-info, then per plane dispatches translation MC / compound (av1_mc_pred_compound) / inter-intra (av1_mc_pred_interintra_w) / warp — LOCALWARP + GLOBALWARP + inter-intra warp-blend + compound-global warp; the per-plane useWarp gate, the warp-model build LOCALWARP-via-warp_estimation / GLOBALWARP+compound-via-warp_model_from_global) + **av1_residual_inter_encode** (non-skip + var-tx inter residual, given-residual encoder) + **av1_decode_inter_tile** / **av1_encode_inter_tile** (the tile drivers) + **av1_tile_set_inter_ctx** (frame-start setup incl. the use_ref_frame_mvs-gated motion_field_estimation hook, 0.7.103). Only scaled-reference/BILINEAR MC remains for inter frames to decode end-to-end |
| `src/av1_lr.cyr` | `av1_` | loop restoration (7.17) — filter kernels (Wiener 7.17.5/6/7 + self-guided/SGR 7.17.2/3) **and the driver**: av1_lr_process (7.17.1 copy + stripe loop) / av1_lr_restore_block (7.17.2 stripe geometry + Wiener/SGR dispatch) + count_units + Av1LrParams (per-unit LrType/LrWiener/LrSgrSet/LrSgrXqd) **and the bitstream read** (5.11.57): read_lr_unit (type CDFs + Wiener-coeff / SGR-set-xqd subexp + RefLrWiener/RefSgrXqd predictor) + read_lr (per-SB unit-range geometry) + the decode_tile wiring (AV1TILE_LRPARAMS, 0.7.39). Inert until a frame-level driver attaches the params |
| `src/h264_nal.cyr` | `h264_` | Annex-B scan, NAL hdr, EPB strip/insert, composer |
| `src/h264_ps.cyr` | `h264_` | SPS (full, incl. High branch + crop) / PPS (minimal) |
| `src/h265_nal.cyr` | `h265_` | strict Annex-B scan, 2-byte NAL hdr, RBSP extract |
| `src/h265_ps.cyr` | `h265_` | PTL, VPS/SPS/PPS + crop math + bomb guard |
| `src/vpx_bool.cyr` | `vbool_` | RFC 6386 boolean coder, decoder + encoder |
| `src/vp8.cyr` | `vp8_` | frame tag/keyframe header parse + builder + writer |
| `src/vp9.cyr` | `vp9_` | uncompressed header parse |

`src/main.cyr` is the include-wiring root (no code).

## Gates

- `make build` — smoke exercises one real operation per family, exit 0
- `make test` — per-suite counts are NOT duplicated here; the current totals live in the newest version entry above, which is refreshed every cut (run `make test` for the current
  per-suite breakdown — the biggest suites are av1_intermode ~4,255, av1_recon ~4,209,
  av1_coeffs ~3,851, av1_coeffcdf ~3,450, av1_mv ~2,157, av1_mc_driver ~703, av1_intertile
  ~660; an exact per-suite list is deliberately not pinned here since it moves every bite)
- `make fuzz` — **1,140 assertions**, no crash/hang, all exits known codes
- `make bench` — bitreader/VLC numbers in CHANGELOG
- `make fmt-check` — exit 0; `make lint` — exit 0, clean for **every** module
  (80/80 targets report 0 untracked deferrals + 0 warnings), not just the AV1
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
> **Where we are (0.7.106):** keyframes decode end-to-end, AND inter frames decode NEARLY
> end-to-end. IN: the inter tile decode (0.7.84+), the full MV-prediction arc including the
> COMPLETE temporal-MV arc (producer 0.7.102 → `motion_field_estimation` 0.7.103 → the temporal
> scan 0.7.104), ALL compound prediction (AVERAGE/DISTANCE/DIFFWTD/WEDGE, 0.7.87–90), inter-intra
> (SMOOTH + WEDGE, 0.7.91–92), and ALL FOUR warp forms — LOCALWARP (0.7.93–98), GLOBALWARP
> (0.7.100), OBMC (0.7.101), inter-intra warp-blend (0.7.105), compound-global warp (0.7.106).
>
> **The next bite** (each is one bite; read
> [`docs/guides/verification.md`](../guides/verification.md) first): the ONLY remaining
> inter-prediction track is **scaled-reference / BILINEAR MC** — when a reference plane's dims
> differ from the current plane's (`av1_is_scaled != 0`), the MV is scaled to the ref grid and a
> BILINEAR filter is used (spec 7.11.3.3). `av1_mc_pred_block` / `av1_warp_pred_gen` currently
> handle only the unscaled base case and reject the scaled path; wiring it makes inter frames
> decode end-to-end. **This is the last inter-prediction milestone.**
>
> **Then (non-inter):** the deferred feature-gated reads in inter frames (segmentation map,
> delta-q/lf), film-grain synthesis (7.18.3), conformance vectors, and the encode lane.
>
> **Remaining to AV1 100%:** ~15–30 patches (inter: primitives done; inter FRAMES blocked on segmentation / delta-q / delta-lf / the intra fork · film grain 2–3 · the
> deferred feature-gated list a few · conformance 3–8 · the encode lane 5–10 · close-out audit 1–2).
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

**The AV1 inter layer — NEARLY COMPLETE** (every MC geometry, motion mode, compound/masked form, interpolation filter and reference geometry is in (scaled-reference MC wired 0.7.110, BILINEAR 0.7.108); an inter FRAME still does not decode, because segmentation / delta-q / delta-lf / an intra block inside an inter frame all reject the tile; the
full list of what is now IN, in build order): the MC leaf kernels
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
(inter_block_mode_info, 0.7.82) — the complete per-block inter mode-info decode is ONE CALL now.
inter_frame_mode_info (5.11.15, 0.7.83), the inter tile decode (0.7.84+), the temporal-MV arc (0.7.102–104),
compound (0.7.87–90), inter-intra (0.7.91–92), and all four warp forms + OBMC (0.7.93–106) are ALL now in.
What is NOT in: **scaled-reference/BILINEAR MC** (the last inter-prediction track — a scaled ref uses a
scaled MV + a BILINEAR filter, spec 7.11.3.3); plus film-grain synthesis; then conformance + the encode-lane
completion. (In-loop filters — deblocking,
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
