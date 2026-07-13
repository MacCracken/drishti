# drishti — Current State

> Refreshed every release. CLAUDE.md is preferences/process/procedures
> (durable); this file is **state** (volatile) — versions, counts,
> sizes, in-flight work.

## Version

**0.7.63** — cut 2026-07-13, not yet tagged (user's git). **Inter prediction — the MV candidate stack
(spec 7.10.2).** The second bite of the MV-prediction arc: the ordered list of candidate MVs
`find_mv_stack` builds, plus the two operations that manage it. `src/av1_mv.cyr` grows the
**candidate-stack record** `Av1MvStack` (`RefStackMv[8][2][2]` + `WeightStack[8]` + NumMvFound/
NewMvCount, accessors `av1_mv_stack_*`), **`av1_mv_stack_add`** (the dedup-or-append core of the
search-stack processes 7.10.2.8/9: lower the caller-selected candidate to the frame's MV precision,
then add `weight` to a matching entry — single matches list 0, compound requires BOTH lists — or append
it capped at MAX_REF_MV_STACK_SIZE=8, and bump NewMvCount per has_newmv independent of the dedup),
**`av1_mv_stack_sort`** + `av1_mv_stack_swap` (the sorting process 7.10.2.13: a STABLE descending bubble
sort by weight — strict `<` keeps equal weights in insertion order — with the newEnd early-out, over a
caller-given sub-range), **`av1_has_newmv`** (the six NEWMV-carrying modes), and a refactor extracting
**`av1_lower_mv_comp`** (one component through 7.10.2.10) as the single source of truth so the stack-add
lowers raw components without a temp MV (`av1_lower_mv_precision` now delegates; behaviour-preserving).
Verified by 133 assertions (79 new) — single/compound dedup, weight accumulation, NewMvCount even on a
dedup, the full-stack drop, has_newmv over all 12 modes, a stable sort hand-traced against the spec, a
sub-range sort, a compound sort exercising the both-lists swap, and a dedup-after-lowering case. A
**4-slice adversarial spec review** (add / sort+swap / has_newmv+refactor+layout / tests+libaom-dav1d
cross-check, each finding adversarially verified) returned **NO findings** — reviewers hand-traced the
bubble sort for stability, verified the RefStackMv flattening (idx*4+list*2+comp) never OOBs, and
confirmed the lower_mv_comp refactor reproduces 7.10.2.10 component-for-component; the 2 refuted coverage
suggestions were folded in. Only the stack MECHANICS are new; the neighbour scans that FEED it (need the
inter MI grid) + the find_mv_stack driver + entropy contexts are later bites. (`stack` is a reserved
word in cyrius — the handle is named `mvs`.) **Prior: MV-prediction foundation `av1_mv.cyr` 0.7.62;
DPB / ref-frame buffer `av1_dpb.cyr` 0.7.61; MC driver `av1_mc_pred_block` 0.7.60; `emu_edge` 0.7.59;
`put_8tap` 0.7.58; Subpel_Filters 0.7.57; superres 0.7.52–0.7.56; multi-tile 0.7.47–0.7.51; 10-bit
0.7.46 — 3 of 4 decode tracks done, inter underway.** Next on the inter track: the neighbour scans +
the find_mv_stack driver + inter mode-info (then the inter tile decode). The remaining distance to 1.0
is inter + conformance + the encode-lane completion (finishing 0.7.x), then the other per-codec arcs
(0.8.x H.264 → 0.10.x VP8/VP9) + audit (0.11.x) + freeze/docs (0.12.x). See
[`CHANGELOG.md`](../../CHANGELOG.md) + [`roadmap.md`](roadmap.md).

> **Gate discipline** (2026-07-11): `make lint` is part of the green bar and is
> reported by its actual exit code — never folded into "green" while red. A
> >120-char line had silently failed it since the entropy-decoder work; fixed in
> 0.7.29. A full doc-claim audit + deferral squash is scheduled for the 0.7.x
> close-out (see roadmap.md / memory).

## Toolchain

- **Cyrius pin**: `6.4.46` (in `cyrius.cyml [package].cyrius`) — min
  version for the arithmetic-shift operator `>>>`. The pin is the
  *minimum*; a newer installed `cycc` (currently **6.4.62**) compiles
  clean and only emits a harmless drift note. **Set
  `CYRIUS_NO_WARN_PIN_DRIFT=1`** in the env for clean build/test/lint
  output. Bump the pin only when a new toolchain feature is actually used
  (none needed so far past 6.4.46).
- **`lib/`**: materialized by `cyrius deps` — real directory, never a
  symlink, never committed.

## Source (38 `[lib]` modules, dependency order)

| Module | Family | Surface |
|--------|--------|---------|
| `src/drishti.cyr` | core `dr_` | error record + code bands, `drishti_version()` → 759, format sniff |
| `src/bits.cyr` | core `dr_` | MSB-first bitreader/bitwriter, leb128/uvlc/ue/se + su/ns read + write, FloorLog2, bit-skip, sticky-latch seam |
| `src/ivf.cyr` | core `dr_ivf_` | IVF read/write (AV01/VP80/VP90) |
| `src/frame.cyr` | core `dr_frame_` | shared YUV planar-frame buffer (DrFrame): 1/3 planes, 16-bit samples, subsampling, border, dr_clip1 |
| `src/av1_obu.cyr` | `av1_` | OBU parse/walk/write |
| `src/av1_seq.cyr` | `av1_` | sequence_header_obu → full-fidelity Av1Seq |
| `src/av1_frame.cyr` | `av1_` | uncompressed frame header (5.9.2, all frame types) + ref-frame state machine (Av1FrameHeader / Av1RefState) |
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
| `src/av1_mv.cyr` | `av1_` | motion-vector prediction (spec 7.10.2) — **foundation** (0.7.62): **Av1Mv** (row,col) MV representation (1/8-luma-sample units; av1_mv_new/row/col/set); **av1_lower_mv_precision** + **av1_lower_mv_comp** (7.10.2.10); **av1_setup_global_mv** (7.10.2.1 — the global-motion MV candidate: 2×3 affine projection of the block center through gm_type/gm_params, rounded with the symmetric av1_round2_signed). **candidate stack** (0.7.63): **Av1MvStack** (RefStackMv[8][2][2] + WeightStack[8] + NumMvFound/NewMvCount; av1_mv_stack_new/reset/num/newmv_count/weight/row/col); **av1_mv_stack_add** (dedup-or-append core of search stack 7.10.2.8/9 — lower + weight-accumulate-or-append capped at 8 + NewMvCount); **av1_mv_stack_sort** + **_swap** (stable descending sort 7.10.2.13); **av1_has_newmv**. The neighbour scans (need the inter MI grid) + find_mv_stack driver + entropy contexts are later bites |
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

## Gates (all green, 2026-07-13)

- `make build` — smoke exercises one real operation per family, exit 0
- `make test` — 36 suites / **21,332 assertions**: drishti 51 · bits
  1,211 · ivf 889 · frame 73 · av1 185 · av1_frame 140 · av1_symbol 362 ·
  av1_itx 160 · av1_intra 202 · av1_quant 1,569 · av1_recon 4,209 ·
  av1_scan 137 · av1_coeff 47 · av1_coeffcdf 3,450 · av1_coeffs 3,851 ·
  av1_noncoeffcdf 1,820 · av1_modeinfo 344 · av1_txsize 169 · av1_txtype
  142 · av1_residual 64 · av1_partition 216 · av1_tile 33 · av1_deblock 56 ·
  av1_cdef 42 · av1_superres 167 · av1_mc 187 · av1_mc_kernel 10 · av1_mc_emu_edge 15 · av1_mc_driver 157 · av1_mv 133 · av1_dpb 82 · av1_lr 80 · av1_decode 190 · h264 326 · h265 276 · vpx 287
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
  a compound sort + a dedup-after-lowering case — were folded into the suite)

## Dependencies

- stdlib only: string, fmt, alloc, io, vec, str, syscalls, assert, bench
- No external crate deps. No C. No FFI.

## Consumers

None yet — registered targets: tarang, tazama, jalwa, aethersafta
(they arrive at the families' decode milestones).

## In-flight / next

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
+ `av1_setup_global_mv` 7.10.2.1, the global-motion candidate), and the **MV candidate
stack** (`av1_mv.cyr` 0.7.63 — `Av1MvStack` + `av1_mv_stack_add` search-stack dedup/
append 7.10.2.8/9 + the stable `av1_mv_stack_sort` 7.10.2.13 + `has_newmv`) are in; next
the neighbour scans (scan_row/col/point + temporal — which need the inter MI grid) that
FEED the stack + the `find_mv_stack` driver + the NewMv/RefMv/Zero/DRL contexts, then
inter mode-info (then the inter tile decode that lets `av1_decode_stream` decode a genuine
inter frame referencing the DPB through the MC driver), then compound/OBMC/warp +
scaled-reference/BILINEAR MC; plus film-grain synthesis; then conformance + the
encode-lane completion. (In-loop filters — deblocking, CDEF, loop restoration — plus
superres and 10/12-bit are already complete.) The deferred,
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
