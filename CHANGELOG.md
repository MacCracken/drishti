# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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
