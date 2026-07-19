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
  block/partition decode **(done 0.7.19–0.7.25 — 7-bite arc: 0.7.19
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
  parsed header, and the OBU / `tile_group_obu` walk (0.7.42–0.7.45) feeds real tile
  bytes into it — a keyframe decodes raw OBU bytes to pixels end-to-end through the full
  CDEF-inclusive loop-filter chain. Loop
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
  multi-tile-**group** frames 0.7.51); **superres COMPLETE** (7.16 — 0.7.52–0.7.56, a
  use_superres keyframe decodes end-to-end, reference-confirmed against dav1d). **INTER
  nearly complete** (the last of the four tracks, and the biggest — every warp form, the
  temporal-MV arc, compound and inter-intra are in; only scaled-reference/BILINEAR MC
  remains — 7.11.3: the Subpel_Filters
  table 0.7.57, the `put_8tap` 8-tap MC kernel 0.7.58 (reference-confirmed vs dav1d
  `put_8tap_c`), the `emu_edge` frame-boundary block fetch 0.7.59 (reference-confirmed vs
  dav1d `emu_edge_c`), and the **MC driver** `av1_mc_pred_block` 0.7.60 (spec 7.11.3.1
  steps 10+13: the unscaled 1/16-pel MV split → `emu_edge` gather → `put_8tap` → `Clip1`
  into the `DrFrame`, for the single-ref/translation-only/non-compound/unscaled base case;
  spec-literal-reference-tested; a 5-slice adversarial review found + fixed 3 defects — a
  critical i64-overflow guard bypass, a major scaled-chroma-ref acceptance, and a minor
  per-call arena alloc), and the **reference-frame buffer / DPB** `av1_dpb.cyr` 0.7.61 (spec
  7.20 reference frame update + 7.21 loading: the 8-slot pixel `FrameStore` + `av1_dpb_store`/
  `_update`/`_load`, the `av1_dpb_ref_frame` inter hook mapping `ref_frame_idx` to the stored
  frame the MC driver reads, and the `av1_decode_stream` multi-frame OBU walk; a 5-slice
  adversarial review returned no findings), the **MV-prediction foundation** `av1_mv.cyr`
  0.7.62 (spec 7.10.2: the `Av1Mv` (row,col) representation + `av1_lower_mv_precision` 7.10.2.10 +
  `av1_setup_global_mv` 7.10.2.1 — the global-motion MV candidate, the leaf-first entry to the
  MV-pred arc), the **MV candidate stack** `av1_mv.cyr` 0.7.63 (`Av1MvStack` + `av1_mv_stack_add`
  — the dedup-or-append core of the search-stack processes 7.10.2.8/9 — + the stable
  `av1_mv_stack_sort` 7.10.2.13 + `has_newmv`), the **spatial neighbour scans** `av1_mv.cyr`
  0.7.64 (`av1_mv_scan_row`/`_col`/`_point` 7.10.2.2/3/4 + `av1_add_ref_mv_candidate` 7.10.2.7 + the
  search-stack selection preambles, over the `Av1MvCtx`/`Av1MiRec` grid), and the **`find_mv_stack`
  driver** `av1_mv.cyr` 0.7.65 (`av1_find_mv_stack` 7.10.2 + `av1_mv_extra_search`/`_add_extra`
  7.10.2.11/12 + `av1_mv_context_and_clamping` 7.10.2.14 + `av1_clamp_mv_row`/`_col` — the full
  candidate list + entropy contexts, temporal deferred), the **inter mode-info MV component
  decode** `av1_intermode.cyr` 0.7.66 (the MV CDF family + `av1_read_mv`/`_read_mv_component` 5.11.32 +
  the paired encoder — turning the entropy stream + PredMv into a Mv), the **single-prediction
  inter mode reads** `av1_intermode.cyr` 0.7.67 (`av1_read_inter_mode`/`_read_drl_idx`/
  `av1_assign_mv_single` 5.11.32 + the New/Zero/Ref/Drl CDFs — composing the find_mv_stack contexts +
  candidate stack + read_mv into a decoded inter YMode + Mv), the **reference-selection reads**
  `av1_intermode.cyr` 0.7.68 (`av1_read_is_inter` 5.11.30 + `av1_read_single_ref` 5.11.25 + the
  Is_Inter/Single_Ref CDFs — the single RefFrame[0] decode), the **compound reference path**
  `av1_intermode.cyr` 0.7.69 (`av1_read_comp_mode` + `av1_read_compound_ref` 5.11.25 + the Comp_Mode/
  Comp_Ref_Type/Comp_Ref/Comp_Bwd_Ref/Uni_Comp_Ref CDFs — all 16 compound reference pairs), and the
  **compound mode path** `av1_intermode.cyr` 0.7.70 (`av1_read_compound_mode` + `av1_get_mode` +
  `av1_assign_mv_compound` 5.11.32 + the Compound_Mode CDF — the two-list mode/MV decode), the **interp
  filter + motion mode reads** `av1_intermode.cyr` 0.7.71 (`av1_read_interp_filter` 5.11.30 +
  `av1_read_motion_mode`/`av1_read_use_obmc` 5.11.27 + the Interp_Filter/Motion_Mode/Use_Obmc CDFs), and the
  **inter-intra reads** `av1_intermode.cyr` 0.7.72 (`av1_read_interintra`/`_interintra_mode`/
  `_wedge_interintra`/`_wedge_index` 5.11.28 + the new av1_iicdf blob), and **read_compound_type**
  `av1_intermode.cyr` 0.7.73 (the full 5.11.29 driver — `av1_read_comp_group_idx`/`_compound_idx`/
  `_compound_type_sym` + `av1_read_compound_type` composing them with the shared wedge_index +
  wedge_sign/mask_type literals, Wedge_Bits, the av1_comptype_* record; all bites' adversarial reviews
  returned no findings), and the **MI-grid population** `av1_mv.cyr` 0.7.74 (`av1_mi_store_mode` /
  `av1_mi_store_final` — the 5.11.4 decode_block storage loops, writing a decoded block's mode info across
  its bw4 x bh4 footprint, clipped to the frame; this CLOSES the producer->consumer loop the scans depend on)
  are in, and the **neighbour CDF contexts** `av1_intermode.cyr` 0.7.75 (`av1_nbctx_setup` 5.11.15 +
  `av1_check_backward`/`av1_count_refs`/`av1_ref_count_ctx` + `av1_is_inter_ctx`/`av1_comp_mode_ctx` — the
  FIRST un-deferral, feeding the 0.7.68/0.7.69 reads for real now the grid is populated) — **THE INTER
  MODE-INFO BITSTREAM-READ LAYER IS COMPLETE and the grid it feeds is populated**, and the **reference-context
  family** `av1_intermode.cyr` 0.7.76 (the seven ref_count_ctx derivations + `av1_comp_ref_type_ctx` + the
  `av1_single_ref_ctxs` / `av1_comp_ref_ctxs` fillers — the reference reads' contexts are no longer caller
  inputs) is in too, and the **last three contexts** `av1_intermode.cyr` 0.7.77 (comp_group_idx /
  compound_idx / interp_filter + the Av1MiRec grid fields they read — **every inter CDF context is now
  derived**; the caller supplies only AvailU/AvailL + the order-hint distances, as the spec does), and the
  **gating orchestrators** `av1_intermode.cyr` 0.7.78 (`av1_read_interintra_mode` 5.11.28 +
  `av1_needs_interp_filter` / `av1_read_interp_filters` 5.11.23 — the gating 0.7.71/0.7.72 deferred to "the
  caller") and the **warp-sample leaves** `av1_mv.cyr` 0.7.79 (`find_warp_samples` / `add_sample` 7.10.4 +
  `has_overlappable_candidates` — what read_motion_mode's OBMC/LOCALWARP gating needs) are in, and the
  **read_motion_mode gating driver + is_scaled** 0.7.80 (`av1_read_motion_mode` — the full 5.11.27 gate over
  the _sym leaves + warp samples + `av1_is_scaled` `av1_frame.cyr`, with the gate-replaying encoder inverse;
  the last gating orchestrator) and the **read_ref_frames dispatcher + seg_feature_active** 0.7.81
  (`av1_read_ref_frames` — the 5.11.25 dispatch: skip_mode / segmentation fixed paths / the comp_mode gate
  into the 0.7.68/0.7.69 trees; + `av1_seg_feature_active` 5.11.14 `av1_frame.cyr`) and the **5.11.23
  ORCHESTRATOR itself** 0.7.82 (`av1_inter_block_mode_info` — the complete per-block inter mode-info
  decode as one call, with the Av1InterBlock record + the full encoder inverse) and the **5.11.15
  OUTER DISPATCH** 0.7.83 (`av1_inter_frame_mode_info` + `read_skip_mode` 5.11.11 + the is_inter
  selection; segmentation reads / delta-q/lf / the intra fork remain hard-gated deferrals of this
  list) are in too, and **THE INTER TILE DECODE 0.7.84 — THE MILESTONE, REACHED**
  (`src/av1_intertile.cyr`: a genuine skip-path inter frame decodes end-to-end, raw bytes →
  motion-compensated pixels from the DPB, through `av1_decode_stream`), and **THE NON-SKIP INTER
  RESIDUAL 0.7.85 — UNIFORM-TX** (`av1_transform_block_inter`/`av1_residual_inter`: `inter_tx_type`
  reads + inter coeffs + reconstruct-onto-MC; non-skip inter blocks decode with a real residual,
  TX_MODE_LARGEST scope; the inter transform-type CDF/inverse/membership tables land in
  `av1_txtype`/`av1_noncoeffcdf`), and **THE VAR-TX INTER RESIDUAL 0.7.86** (`av1_read_var_tx_size` +
  the `txfm_split` CDF/ctx + `av1_transform_tree` + the per-4x4 `TxTypes` grid — TX_MODE_SELECT non-skip
  inter blocks now decode, each luma transform-partition leaf reconstructed onto the MC prediction; the
  encode inverse + a per-leaf plan land too), **COMPOUND AVERAGE INTER PREDICTION 0.7.87**
  (`av1_mc_pred_compound` + the `put_8tap` prep/`ib` precision path — a two-reference block predicts from
  BOTH refs and averages them; scope `COMPOUND_AVERAGE` only), and **COMPOUND DISTANCE (jnt) 0.7.88**
  (`av1_dist_wtd_fwd` 7.11.3.15 order-hint weights + the generalized weighted combine — `compound_idx==0`
  blends the two predictions by distance; masked wedge/diffwtd still refused), and **COMPOUND DIFFWTD
  (masked) 0.7.89** (`av1_diffwtd_mask_build` 7.11.3.12 per-pixel difference mask + the 7.11.3.14 mask
  blend + chroma subsampling — `comp_group_idx==1 && type==DIFFWTD` blends by a difference mask), and
  **COMPOUND WEDGE (masked) 0.7.90** (`av1_wedge_master_tbl` + `av1_wedge_cb_tbl` + `av1_wedge_mask_build`
  7.11.3.11 — a codebook wedge mask (oriented soft boundary) via the master oblique/vertical planes + the
  3×16 codebook; closes the masked family, both DIFFWTD + WEDGE in scope), and **SMOOTH INTER-INTRA 0.7.91**
  (`av1_ii_smooth_mask_build` 7.11.3.13 + `av1_mc_pred_interintra` — a single-ref inter block blends its MC
  with an INTRA prediction (the keyframe `av1_intra_predict` invoked from the inter path) via a smooth mask;
  final-precision blend, chroma-regenerated mask; overhang refused), and **WEDGE INTER-INTRA 0.7.92**
  (the `is_wedge` branch of `av1_mc_pred_interintra` — the second interintra variant blends the MC with an
  INTRA prediction through a WEDGE mask from the compound codebook 7.11.3.11, built on LUMA at the nominal
  size with `wedge_sign` forced 0 and chroma SUBSAMPLING the luma mask (unlike smooth's per-plane regen);
  reuses the verified codebook + the final-precision blend — **closes the masked-interintra family, every
  AV1 interintra mode now decodes**), and **WARP ESTIMATION 0.7.93** (`av1_warp_estimation` 7.11.3.8 +
  `av1_resolve_divisor` 7.11.3.7 + the lazy `Div_Lut[257]` — the least-squares solve turning the
  find_warp_samples CandList into a 6-param affine LocalWarpParams + LocalValid; a pure derivation like
  setup_global_mv, NOT yet wired to pixels — LOCALWARP stays gated until warp MC; the libaom LS_MAT
  accumulator clamp is DEFERRED as un-witnessable here), and **SETUP SHEAR 0.7.94** (`av1_setup_shear`
  7.11.3.6 — the warp model → shear params `alpha/beta/gamma/delta` + a `warpValid` realizability flag;
  reuses the 0.7.93 `resolve_divisor` on `wmmat[2]` (RAW output, not the determinant), reduces to multiples
  of `1<<WARP_PARAM_REDUCE_BITS`, rejects when `4|alpha|+7|beta|` or `4|gamma|+4|delta|` >= `1<<16`; a pure
  derivation, un-defers the 0.7.93 shear-realizability check), and **WARP FILTER TABLE 0.7.95**
  (`av1_warp_filter` — the `Warped_Filters[193][8]` signed 8-tap interpolation table 7.11.3.5, machine-
  generated from a re-fetched dav1d `src/tables.c` and MD5-anchored; the last table needed before the
  per-pixel warp; NOT yet consumed), and **BLOCK WARP KERNEL 0.7.96** (`av1_warp_affine_8x8` 7.11.3.5 —
  the per-8x8 warp motion-compensation kernel: a two-pass separable filter applying the shear params through
  Warped_Filters, `Round2(·,7−ib)` H into a signed mid then `Clip1(Round2(·,7+ib))` V — the FULL 7±ib rounds
  because the warp table sums to 128, NOT put_8tap's 6±ib; verified standalone against the cached dav1d
  `warp_affine_8x8_c`; NOT yet wired), and **WARP PREDICTION DRIVER 0.7.97** (`av1_warp_pred_block` 7.11.3.5 —
  per 8x8 sub-block projects the block centre through the wmmat to the source position + the sub-pixel phase
  seeds (`mx=(sx4−4α−7β)&~0x3f`), gathers the 15x15 padded reference via `emu_edge`, runs the 0.7.96 kernel,
  writes back cropped; luma + subsampled chroma; verified standalone against the cached dav1d `warp_affine`
  driver; the whole warp pixel path is now assembled), and **LOCALWARP DECODES TO PIXELS 0.7.98** (the warp
  milestone — the inter tile decode builds the local warp model (`warp_estimation`→`setup_shear`) and predicts
  each plane through `av1_warp_pred_block`, with the per-plane useWarp gate (nominal ≥8 warps, else translation)
  and the load-bearing `det==0`→translation fallback; a LOCALWARP inter block decodes end-to-end to warped
  pixels). DEFERRED to
  the conformance era: the `fwd_eq_bck` compound_idx CDF-context term (5.11.29) — it shifts one binary
  symbol's context, un-witnessable by a self-consistent round-trip, so it lands with external jnt vectors,
  not on the pre-conformance decode lane; likewise the warp `LS_MAT`-clamp. The three 0.7.98-review test-coverage
  witnesses (MINOR, code was already verified-correct) are **CLOSED in 0.7.99** via a nested-SPLIT harness: the
  8×8-chroma-boundary useWarp gate (16×16-luma block, chroma `nw==8` warps), the 4×4-chroma translation fallback
  (8×8-luma block, chroma `nw==4` translates), and the edge-overhang nominal-vs-clamped gate (16×16 block
  bottom-cut in a 32×28 frame) — each mutation-verified. **GLOBALWARP 0.7.100** (useWarp==2 — a single-ref
  GLOBALMV block whose reference carries a `GmType>TRANSLATION` global model warps with `gm_params`: the model
  is `av1_warp_model_from_global` (gm_params ARE wmmat, so no least-squares) → `setup_shear`, reusing the same
  per-plane useWarp gate + `av1_warp_pred_block`; gated `!force_integer_mv && !is_scaled` per dav1d
  `gmv_warp_allowed`; the `Mv[0]==global MV` translation fallback covers useWarp==0; a GLOBALMV **inter-intra**
  block that would warp is REJECTED, not silently translation-blended — the review caught that), and
  **OBMC 0.7.101** (overlapped block MC, spec 7.11.3.9/10 — the SECOND motion mode: an OBMC block's own MC
  is smoothed at the top/left edges with the above-row + left-col neighbours via a raised-cosine `Obmc_Mask`;
  `av1_obmc_predict` two-pass scan + `av1_obmc_overlap` blend, gated per the spec asymmetry (above pass has a
  residual-size gate, left pass none); verified pixel-exact vs a spec-literal `obmc_ref.py`), and the
  **TEMPORAL-MV arc** (3 bites, the last find_mv_stack deferral): **Bite 1 / producer 0.7.102** (`av1_mv_save_field`
  — save each inter frame's per-8x8 motion field into the DPB it refreshes, spec 7.19/7.20; `AV1REF_SAVED_MF`
  storage + the `av1_frame_dec_finish` hook; output-neutral, KAT vs a spec-literal `tmvs_save_ref.py`), and
  **Bite 2 / motion_field_estimation 0.7.103** (spec 7.9 — 2a: `Div_Mult[32]` + `av1_get_mv_projection` +
  `av1_get_block_position`/`project` as KAT'd leaves; 2b: `av1_mv_projection` (7.9.2 per-ref) +
  `av1_motion_field_estimation` (7.9.1 useLast/refStamp driver) + the reusable `MotionFieldMvs` scratch + the
  `av1_tile_set_inter_ctx` frame-start hook behind `use_ref_frame_mvs`; still output-neutral), and
  **Bite 3 / the scan 0.7.104** (spec 7.10.2.5/6 — `av1_temporal_scan` + `av1_add_tpl_ref_mv`: find_mv_stack
  reads `MotionFieldMvs`, folds projected temporal MVs into the candidate stack + derives `ZeroMvContext`,
  gated on `use_ref_frame_mvs`; the FIRST output-changing temporal bite — closes the temporal-MV arc), and
  **inter-intra warp-blend 0.7.105** (spec 7.11.3.1 — a GLOBALWARP inter-intra block warps the inter part per
  plane into `Av1_McOut` then runs the unchanged mask blend; un-defers the 0.7.100 `is_ii && warp_valid`
  reject; `av1_warp_pred_gen` + `av1_mc_pred_interintra_w`), and **compound GLOBAL_GLOBALMV warp 0.7.106**
  (spec 7.11.3.5 isCompound — each ref warps at INTERMEDIATE precision into `Av1_McTmp`/`Av1_McOut` then the
  existing combine; a latent-mis-decode fix that lifts the `is_comp==0` restriction; `av1_warp_affine_8x8` +
  `compound` flag + a dedicated `Av1_McWarp8` kernel scratch). Then scaled-reference/BILINEAR MC — the LAST
  inter-prediction track before inter frames decode end-to-end; all table-free bar the warp filter +
  Obmc_Mask + Div_Mult, dav1d `mc_tmpl.c` / `refmvs.c` references in hand).
  See memory `av1-decode-remaining-tracks`.
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
