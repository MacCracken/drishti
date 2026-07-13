# drishti — Roadmap

> Milestone plan through v1.0. State lives in [`state.md`](state.md);
> this file is the sequencing — what ships, in what order.
>
> **Shape of the repo**: ONE repo, codec families as flat `[lib]`
> modules (the shravan model — [ADR 0001](../adr/0001-one-repo-module-per-codec.md)).
> The path to 1.0 is **one minor arc per codec** — each family gets a
> full minor line to go from "bitstream/header layer" (all shipped at
> **0.7.0**) to **100%** (decode conformance-clean + encode
> round-trip-clean, where encode is in charter) — followed by a
> cross-family **audit** arc and a **freeze/documentation** arc before
> the 1.0.0 close-out.

## The path to 1.0 — minor arc per codec

| Arc | Owner | Target | Charter |
|-----|-------|--------|---------|
| **0.7.x** | **AV1** | decode + encode → 100% | replaces dav1d + rav1e |
| **0.8.x** | **H.264/AVC** | decode + encode → 100% | replaces openh264 |
| **0.9.x** | **H.265/HEVC** | decode → 100% | replaces libde265 (encode out of charter) |
| **0.10.x** | **VP8/VP9** | decode + encode → 100% | replaces libvpx |
| **0.11.x** | **Audit** | cross-family security + correctness | find → adversarially verify → harden |
| **0.12.x** | **Freeze + docs** | API freeze, benchmarks, consumer | no behavior change |
| **1.0.0** | **Close-out** | clean cut, all criteria green | — |

> **Why 0.7.0 as the baseline** (not 0.1.0): the shared substrate plus
> every family's full bitstream/container/header layer is a large,
> already-hardened surface (2,220 suite + 1,140 fuzz assertions) —
> "almost ready for v1, but not quite." The remaining distance is the
> per-codec decode/encode completion arcs below. Minor versions run
> past 9 by SemVer (`0.10.0 > 0.9.0`).

## v1.0 criteria (ecosystem standard)

- [ ] All four families at their charter target (AV1 dec+enc, H.264
      dec+enc, H.265 dec, VP8/VP9 dec+enc), each conformance-clean
      (decode) / round-trip-clean (encode) — arcs 0.7.x–0.10.x
- [ ] Security audit pass (`docs/audit/YYYY-MM-DD-audit.md`) — arc 0.11.x
- [ ] Public API frozen — `docs/api.md`, every exported symbol
      documented and tested — arc 0.12.x
- [ ] Benchmarks captured (`docs/benchmarks.md`) — arc 0.12.x
- [ ] At least one downstream consumer green (tarang / tazama / jalwa /
      aethersafta) — arc 0.12.x
- [ ] CHANGELOG complete from 0.7.0 onward

## 0.7.0 — baseline (done, this cut)

Shipped for all four families at once, so the arcs below start from a
common floor:

- **Shared core** (`dr_`): error record + per-family code bands, format
  sniff; MSB-first bitreader/bitwriter with sticky-error discipline;
  leb128 (AV1 4.10.5), uvlc (4.10.3), exp-Golomb ue/se (H.264 9.1 /
  H.265 9.2) — read AND write (the encode-lane seed); IVF read/write;
  the `dr_br_set_err` / `dr_bw_set_err` latch seam.
- **AV1**: OBU parse/walk/write + sequence-header parse (both paths).
- **H.264**: Annex-B scan, NAL headers, EPB both directions, full SPS
  (incl. High branch + crop) + PPS.
- **H.265**: strict Annex-B scan, two-byte NAL headers, profile_tier_level,
  VPS/SPS/PPS with crop math + dimension-bomb guard.
- **VP8/VP9**: the RFC 6386 boolean coder (decode + encode), VP8 framing
  + writer, VP9 uncompressed header.

## Shared substrate — grows *within* the arcs (demand-gated)

Not its own arc; these land inside whichever codec arc first needs them:

- **YUV frame-buffer / plane types** — **done (0.7.3)**: `src/frame.cyr`,
  the shared `DrFrame` planar-frame record (1/3 planes, 16-bit samples
  for 8/10/12-bit, subsampling, padding border, `dr_clip1`). Landed with
  the AV1 intra-decode milestone; VP8/H.26x reuse it.
- **Entropy-coder consolidation watch** — CABAC (H.264/H.265),
  multi-symbol adaptive-CDF (AV1), and the boolean coder (VP8/VP9) stay
  per-family until real overlap proves out. Do NOT unify speculatively.
- **Conformance-vector harness** — a shared runner lands with the first
  family's conformance sub-arc, then the others reuse it.
- **Container scope** — IVF is the test-bench container; MP4/WebM demux
  is out of scope for drishti (a future container lib's job).

## Upstream workaround watch

- **`dr_ashr` arithmetic-shift shim** — **RESOLVED (0.7.7)**. cyrius 6.4.46
  added a dedicated arithmetic (sign-preserving) right shift `>>>`
  (`>>` stays LOGICAL — note the convention is the reverse of JS/Java).
  The `dr_ashr` shim (added 0.7.5) was deleted and its call sites
  (inverse-transform `Round2`/WHT, `av1_read_global_param`) now use `>>>`;
  the toolchain pin moved to 6.4.46. Upstream issue
  `cyrius/docs/development/issues/2026-07-10-drishti-runtime-shift-logical-not-arithmetic.md`
  is closed. The transform/gm known-answers are unchanged.

---

## 0.7.x — AV1 → 100% (decode + encode; replaces dav1d + rav1e)

Baseline (0.7.0): OBU layer + sequence header.

- **frame-header OBU** — **done (0.7.1)**: full `uncompressed_header()`
  (5.9.2) for every frame type (key / inter / intra-only / switch /
  show_existing), cursor-true; the ref-frame state machine
  (`set_frame_refs` 7.8, `frame_size_with_refs`, reference update 7.20,
  `mark_ref_frames`); frame-size overrides + superres + render size;
  full-fidelity `Av1Seq` growth; the shared `su(n)`/`ns(n)` descriptors.
- **entropy decoder** — **done (0.7.2)**: the multi-symbol adaptive-CDF
  arithmetic (symbol) decoder (spec 8.2 — init_symbol / read_symbol +
  CDF adaptation / read_bool / read_literal / exit_symbol), plus the
  paired symbol encoder (encode-lane seed) so every path round-trips.
- **intra still-picture decode — MILESTONE** — partition tree, intra
  prediction modes, inverse transforms, reconstruction (profile-0
  keyframes: first pixels out). Sub-bites: YUV frame buffer **(done
  0.7.3)** → inverse transforms **(done 0.7.4)**: DCT 4-64 / ADST 4-16 /
  identity / WHT + the 2D driver (`src/av1_itx.cyr`) → intra prediction
  **(done 0.7.6-0.7.10: `src/av1_intra.cyr` — non-directional
  DC/PAETH/SMOOTH×3 + V/H; the full angled directional prediction + intra
  edge filter/upsample/corner; recursive filter-intra (7.11.2.3);
  chroma-from-luma (7.11.5). The 7.11.2 + 7.11.5 intra layer is
  complete.)** → dequantization **(done 0.7.11: `src/av1_quant.cyr` —
  Dc/Ac Qlookup + get_qindex/get_dc_quant/get_ac_quant, 7.12.2)** → the
  reconstruct glue **(done 0.7.12: `src/av1_recon.cyr` — dequant →
  inverse transform → FLIPADST-flipped residual add, 7.12.3; first pixels
  from a coefficient array)** → coefficient decode **(done 0.7.13-0.7.18 —
  0.7.13: `src/av1_scan.cyr`, the scan orders + get_scan (5.11.41);
  0.7.14: `src/av1_coeff.cyr`, the level contexts get_tx_class /
  get_coeff_base_ctx / get_br_ctx (8.3.2); 0.7.15-0.7.16:
  `src/av1_coeffcdf.cyr`, all 7 default coefficient CDF families (txb_skip
  / eob_pt / eob_extra / dc_sign / coeff_base_eob / coeff_base / coeff_br);
  0.7.17: `src/av1_coeffs.cyr`, the coeffs() reading loop (5.11.39) — a
  transform block decodes end-to-end, round-trip tested; 0.7.18: the
  adaptive per-tile CDF context (`av1_ccdf_*`) so decode works with CDF
  adaptation on — both `disable_cdf_update` modes complete)** → the
  block/partition decode **(in progress — 7-bite arc: 0.7.19
  `src/av1_noncoeffcdf.cyr` the non-coeff CDF tables; 0.7.20
  `src/av1_modeinfo.cyr` the intra mode-info reads (skip / y+uv mode / CfL /
  angle / filter-intra decode + inverse encode) with the shared block-size
  conversion tables; 0.7.21 `src/av1_txsize.cyr` the intra transform-size
  read (`read_tx_size` / `tx_depth` decode + inverse encode + the
  Max_Tx_Size_Rect / Max_Tx_Depth / Split_Tx_Size tables); 0.7.22
  `src/av1_txtype.cyr` the transform-type derivation (`compute_tx_type` /
  `transform_type` / `get_tx_set`) spliced into the coeffs loop, retiring the
  PlaneTxType caller-input; 0.7.23 `src/av1_residual.cyr` the residual driver
  (`residual()` / `transform_block()`) composing predict_intra → coeffs() →
  reconstruct() per tx block into a DrFrame — a transform block decodes to
  pixels; 0.7.24 `src/av1_partition.cyr` the partition tree
  (`decode_partition` / `decode_block`, all 10 partition types + the block
  orchestration + MI grids + encode lane) — a full partition tree round-trips;
  0.7.25 `src/av1_tile.cyr` the tile/frame loop (`decode_tile` + the
  CDF/symbol wiring) driving decode_partition over a tile into a DrFrame = the
  **first fully decoded keyframe** — the intra still-picture decode MILESTONE
  is complete)**.
- **inter + filters** — motion compensation, deblocking, CDEF, loop
  restoration, film-grain synthesis. **In progress**: the deblocking loop
  filter is complete (`src/av1_deblock.cyr` — kernels in 0.7.27, the edge loop
  + main driver + LoopfilterTxSizes in 0.7.28). CDEF (7.15) is **complete**: the
  kernels (`src/av1_cdef.cyr` — 7.15.2 direction search + 7.15.3 constrain/
  filter) landed in 0.7.29; the process + block process (7.15.1) + the
  `CdefFrame`/`CdefIdx` wiring landed in 0.7.30 — a deblocked frame derings into
  a fresh `CdefFrame`. The 0.7.30 driver enforces the CDEF frame contract via a
  coverage guard (`av1_cdef_coverage_ok`): it rejects with `DR_ERR_BOUNDS` any
  frame that doesn't cover the MI grid (`MiCols*4 x MiRows*4`), and
  `av1_cdef_frame_new` allocates the `CdefFrame` with border >= 8 so it always
  does. The `read_cdef` (5.11.56) / `clear_cdef` syntax primitives (the `cdef_idx`
  bitstream read) landed in 0.7.31 (`av1_modeinfo.cyr`, round-trip tested), and
  0.7.32 wired them into `intra_frame_mode_info` (after `read_skip`) + the
  `decode_tile`/`encode_tile` SB loop, guarded by a per-tile CDEF context
  (`av1_tile_set_cdef_ctx`). The **frame-header activation** helper
  (`av1_activate_intra_filters`, 0.7.41) now calls `set_cdef_ctx` straight from the
  parsed header; **still open**: no OBU / `tile_group_obu` walk feeds real tile bytes
  into it yet, so the splice is exercised only in tests until that driver stage lands
  (0.7.4x). Loop
  restoration (7.17) is **complete** (`src/av1_lr.cyr`): both filter kernels — the
  **Wiener** separable 7-tap (0.7.33) and the **self-guided / SGR** box filter
  (7.17.2/7.17.3, 0.7.34) — plus the stripe-loop process/loop_restore_block driver
  (7.17.1/2, 0.7.35). **The in-loop filter layer's pixel processes are done**
  (deblocking + CDEF + loop restoration all have kernels + drivers). `read_lr`
  (5.11.57) is split (bigger than `read_cdef`): the symbol-coder subexp-bool
  primitives (`NS`/`decode_subexp_bool`/signed-with-ref + `av1_recenter`) landed in
  0.7.36; the restoration-type CDFs + `read_lr_unit` (per-unit type + Wiener /
  SGR-xqd reads + the Ref predictor) landed in 0.7.37; the `read_lr` per-superblock
  geometry (the unit-range loop, incl. superres) landed in 0.7.38, and the
  `decode_tile` wiring (`read_lr` + the per-tile `av1_lr_ref_reset`, guarded by
  `AV1TILE_LRPARAMS`) landed in 0.7.39 — **loop restoration is complete through the
  decode-tile layer** and round-trip-tested end-to-end (unlike CDEF, verified only at
  the mode-info level). The three filters are now **chained** by the in-loop filter
  pipeline (`src/av1_decode.cyr`, `av1_apply_loop_filters`, 0.7.40 — deblock -> CDEF
  -> LR in spec-7.4 order), and the **frame-header filter activation** step landed in
  0.7.41 (`av1_lr_params_from_fh` builds the `Av1LrParams` from the header;
  `av1_activate_intra_filters` attaches it + the CDEF context to a decode tile —
  end-to-end tested by decoding a keyframe tile with header-derived LR params), and
  **tile-group OBU parsing** (`av1_tile_group_parse`, spec 5.11.1) landed in 0.7.42.
  The **frame-level driver** `av1_decode_frame` landed in 0.7.43 (parsed headers ->
  pixels), and the **OBU-stream walk** `av1_decode_obus` landed in 0.7.44 — it parses
  the seq (`av1_seq_parse`) + fh (`av1_frame_parse_uncompressed_header`) from raw OBU
  bytes and drives `av1_decode_frame`, so a full `TD + SEQUENCE_HEADER + FRAME_HEADER
  + TILE_GROUP` stream **decodes from raw bytes to pixels end-to-end**. 0.7.45 added
  the **combined FRAME OBU (type 6)** — the common real-stream form (frame header +
  tile group in one OBU); the walk byte-splits off the tile group (spec 5.10) and
  decodes it, so both OBU forms decode end-to-end. **The raw-bitstream-to-pixels loop
  is closed.** The four remaining AV1-decode capabilities (user directive: pursue
  ALL, don't drop any) — **(1) multi-tile** (per-tile MI origins; invasive but
  table-free), **(2) superres** upscaling (7.16; needs the `Upscale_Filter` table),
  **(3) inter** prediction (the big arc; needs the interpolation-filter tables), and
  **(4) 10-bit** (mostly done — the pixel pipeline already threads `bit_depth`). Doing
  the table-free ones first (10-bit landed 0.7.46; **multi-tile is COMPLETE**:
  frame-addressed MI grids 0.7.47, tile-window origins 0.7.48, driver + first 2-tile
  decode 0.7.49, tile-relative coeff-context + intra-reference rebases 0.7.50,
  multi-tile-**group** frames 0.7.51); superres + inter remain BLOCKED on their
  coefficient tables from the user. See memory `av1-decode-remaining-tracks`.
- **conformance + 10/12-bit** — libaom/Argon vector runs, 10/12-bit paths
  (unblocked 0.7.46), fuzz hardening.
- **ENCODE lane** — intra keyframe encoder (rav1e lineage) growing from
  the `av1_obu_write_header` seed; gate = own-decoder round-trip, then
  cross-decoder (dav1d/libaom).
- **AV1 100%** = decode conformance-clean + encode round-trip-clean →
  close 0.7.x.

## 0.8.x — H.264/AVC → 100% (decode + encode; replaces openh264)

Baseline (0.7.0): NAL layer + parameter sets.

- **slice + CAVLC** — slice header parse + CAVLC residual entropy (9.2);
  pic_order_cnt_type 1; PPS High tail (transform_8x8, pic scaling
  matrix, second_chroma_qp_index_offset via more_rbsp_data()).
- **intra I-frame decode — MILESTONE** — Intra_4x4 / Intra_16x16
  prediction, inverse 4×4 transform + dequant (8.5), reconstruction to
  planar YUV.
- **P slices** — ref pic lists, quarter-pel luma / eighth-pel chroma
  motion compensation (8.4), deblocking filter (8.7).
- **CABAC + High** — CABAC entropy decode (9.3) + High-profile 8×8
  transform path.
- **conformance** — ITU/JM test-vector sweep, fuzz corpus expansion.
- **ENCODE lane** — Baseline intra encoder (SPS/PPS emission already
  seeded by the composer + core VLC writers) → P-frame encode.
- **H.264 100%** = decode conformance-clean + encode round-trip-clean →
  close 0.8.x.

## 0.9.x — H.265/HEVC → 100% (decode only; replaces libde265)

Baseline (0.7.0): NAL layer + parameter sets. Encode is explicitly OUT
of this family's charter (ADR 0001).

- **slice plumbing** — slice_segment_header parse (7.3.6), remaining PPS
  tail (tiles / deblocking / scaling-list flags), CABAC engine + context
  init (9.3.2), parameter-set store keyed by vps/sps/pps ids.
- **intra-only decode — MILESTONE** — CTU quadtree walk (7.3.8), all 35
  intra prediction modes (8.4), inverse 4/8/16/32 transforms +
  reconstruction: real Main-profile still-picture streams end to end.
- **inter + loop filters** — motion compensation (8.5), deblocking
  (8.7.2), SAO (8.7.3): full Main-profile P/B-frame decode.
- **Main10 + conformance** — 10-bit code paths, HM conformance-vector
  battery, fuzz hardening of the slice/CTU layers.
- **H.265 100%** = Main + Main10 decode conformance-clean → close 0.9.x.

## 0.10.x — VP8/VP9 → 100% (decode + encode; replaces libvpx)

Baseline (0.7.0): the boolean coder (decode + encode) + frame headers.

- **VP8 keyframe decode — MILESTONE** — header partition (mode/prob
  decode), token/residual decode, dequant, inverse WHT/DCT, intra
  prediction, loop filter: first pixels (RFC 6386 §§10-15).
- **VP8 inter** — MV decode (§17), motion compensation (§18),
  golden/altref reference state.
- **VP9 keyframe decode** — superblock partition trees, tree probs,
  transforms (VP9 spec §§8-9).
- **VP9 inter + loop filter**.
- **conformance** — libvpx test-vector sweep, fuzz hardening.
- **ENCODE lane** — VP8 keyframe encoder first (RFC 6386's reference
  code makes VP8 the natural encode entry), growing from the 0.7.0
  bool-encoder + frame-tag-writer seeds; gate = own-decoder round-trip,
  then libvpx cross-decode.
- **VP8/VP9 100%** = decode conformance-clean + encode round-trip-clean
  → close 0.10.x.

## 0.11.x — Audit phase (cross-family)

No new features — a security + correctness pass over the whole,
now-complete codec surface, the standard AGNOS pattern (find →
adversarially verify reachability → harden):

- Untrusted-input hardening sweep across every decoder (all four
  families are now full decoders, not just header parsers): re-audit
  every entropy/transform/prediction loop bound, every allocation from
  a stream-derived size, every table index.
- Fuzz-corpus expansion to the decode paths (0.7.0 fuzzed the header
  layer; now the full decoders get corpora).
- Allocation audit — allocation confined to `*_init` / one-shot setup;
  hot decode/encode paths allocation-free.
- The report: `docs/audit/YYYY-MM-DD-audit.md`, findings fixed/guarded,
  sound paths verified. Ticks the v1.0 security-audit criterion.

## 0.12.x — Freeze + documentation phase

No behavior change — close the remaining v1.0 criteria:

- **API freeze** — `docs/api.md`: every exported symbol documented,
  the stable 1.x surface declared, internals marked out-of-freeze;
  `STABILITY.md`.
- **Benchmarks** — `docs/benchmarks.md`: decode/encode throughput per
  family with methodology + reproduction (0.7.0's bitreader/VLC numbers
  extended to whole-frame decode).
- **Downstream consumer green** — at least one of tarang / tazama /
  jalwa / aethersafta (or a bundled `examples/` consumer) decoding a
  real stream through the public API.
- **CHANGELOG** complete + gap-free from 0.7.0; `SECURITY.md` current.

## 1.0.0 — close-out

The clean cut once 0.7.x–0.12.x are all green: no code change from the
last 0.12.x, all six v1.0 criteria met, `api.md` freeze in force for
the 1.x line (minors add only). drishti becomes a v1.0+ crate and moves
to the applications libs registry.

## Out of scope (for v1.0)

- MP4 / WebM / Matroska demuxing — container work beyond IVF belongs to
  a future container lib, not drishti.
- HEVC encode — no sovereign x265-replacement is registered; re-enters
  via the crate registry or not at all.
- Hardware acceleration — drishti is the CPU reference; a GPU path is a
  post-1.0 lever behind mabda.
- Audio — that's shravan.
