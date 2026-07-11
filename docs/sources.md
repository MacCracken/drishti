# drishti — Sources

> Last Updated: 2026-07-10

The citation index for drishti's algorithmic and domain content. AGNOS
codec crates carry a sources file so every nontrivial parse/coding step
is traceable to a spec or primary reference, and so a future maintainer
can re-derive (or audit) any of it. Entries are grouped by module
family. Discipline: the SPEC is the derivation; implementations are
cross-checks — multiple of them, never a single source
(redesign-don't-reinvent).

## Core (`src/drishti.cyr`, `src/bits.cyr`, `src/ivf.cyr`)

- **AV1 Bitstream & Decoding Process Specification** v1.0.0 w/ Errata 1
  (AOMedia) — 4.10.3 uvlc(), 4.10.5 leb128() (the ≤8-byte / ≤32-bit
  conformance bounds `dr_leb128_read` enforces).
- **ITU-T Rec. H.264** — 9.1/9.1.1 ue(v)/se(v) exp-Golomb parsing
  process (shared verbatim by H.265 9.2) — `dr_ue_read`/`dr_se_read`
  and the writer inverses.
- **IVF container** — the de-facto libvpx/AOM test-bench format
  (32-byte `DKIF` header + 12-byte frame headers); layout cross-checked
  against libvpx `ivfdec.c`/`ivfenc.c` and dav1d's `tools/input/ivf.c`.

## AV1

- **"AV1 Bitstream & Decoding Process Specification"** v1.0.0 with Errata 1, Alliance for Open Media, 2019 — authoritative. Sections used through 0.7.1 (cited inline in the modules): 4.10.3 uvlc(), 4.10.5 leb128(), 4.10.6 su(n), 4.10.7 ns(n), 5.3.1 open_bitstream_unit(), 5.3.2 obu_header(), 5.3.3 obu_extension_header(), 5.5.1 sequence_header_obu(), 5.5.2 color_config(), 5.5.3 timing_info(), 5.5.4 decoder_model_info(), 5.5.5 operating_parameters_info(), 5.9.2 uncompressed_header(), 5.9.3 tile_log2(), 5.9.4 get_relative_dist(), 5.9.5 frame_size(), 5.9.6 render_size(), 5.9.7 frame_size_with_refs(), 5.9.8 superres_params(), 5.9.9 compute_image_size(), 5.9.10 read_interpolation_filter(), 5.9.11 loop_filter_params(), 5.9.12 quantization_params(), 5.9.13 read_delta_q(), 5.9.14 segmentation_params(), 5.9.15 tile_info(), 5.9.17 delta_q_params(), 5.9.18 delta_lf_params(), 5.9.19 cdef_params(), 5.9.20 lr_params(), 5.9.21 read_tx_mode(), 5.9.22 frame_reference_mode(), 5.9.23 skip_mode_params(), 5.9.24 global_motion_params(), 5.9.25-5.9.28 read_global_param + subexp decode, 5.9.29 inverse_recenter(), 5.9.30 film_grain_params(), 5.9.31 temporal_point_info(), 6.2.2/6.2.3 OBU semantics (forbidden bit must be 0; reserved bits decoder-ignored), 6.4.1 sequence-header semantics (reserved profiles; reduced implies still), 7.8 set_frame_refs process, 7.12.2 get_qindex, 7.20 reference frame update, 7.21 reference frame loading.
- **dav1d** (VideoLAN) — `src/obu.c` (`dav1d_parse_obus`, `parse_seq_hdr`, `parse_frame_hdr`) — decode cross-check: forbidden-bit rejection, reserved-bit tolerance, sequence- and frame-header field order, the set_frame_refs / global-motion subexp / tile-info branches.
- **libaom** (AOMedia reference codec) — `av1/common/obu_util.c` (`aom_read_obu_header`), `av1/decoder/obu.c` (`read_sequence_header_obu`), `av1/decoder/decodeframe.c` (`read_uncompressed_header`, `setup_frame_size`, `set_frame_refs`) — independent second cross-check of the same surfaces.
- **AV1 symbol (arithmetic) coder** — spec section 8.2 is authoritative for the DECODER: 8.2.2 init_symbol(), 8.2.3 exit_symbol(), 8.2.4 read_bool(), 8.2.5 read_literal(), 8.2.6 read_symbol() (the multi-symbol decode + CDF adaptation), with EC_PROB_SHIFT/EC_MIN_PROB from section 3. The paired ENCODER (the encode-lane seed) is the exact inverse of that decode process; its range-coder normalization + carry flush is cross-checked against **rav1e** `src/ec.rs` (`WriterBase::store` / `done`) and the daala `od_ec_enc` design.
- **AV1 inverse transform** — spec section 7.13 is authoritative (`src/av1_itx.cyr`): 7.13.2.1 butterflies B/H + cos128/sin128/brev + Cos128_Lookup, 7.13.2.2/3 inverse DCT permutation + the 31-step process (sizes 4-64), 7.13.2.4-9 inverse ADST (4/8/16) + permutations, 7.13.2.10 inverse Walsh-Hadamard, 7.13.2.11-15 identity transforms, 7.13.3 the 2D driver; Round2 from section 4; Tx_Width_Log2 / Tx_Height_Log2 / Transform_Row_Shift from the additional-tables annex. Transcribed verbatim from the spec pseudocode and cross-checked by an adversarial spec review.
- **AV1 intra prediction** — spec sections 7.11.2 + 7.11.5 are authoritative (`src/av1_intra.cyr`): 7.11.2.1 predict_intra (reference-sample construction + dispatch + writeback), 7.11.2.2 basic/PAETH, 7.11.2.3 recursive filter-intra, 7.11.2.4 directional (all four angle quadrants), 7.11.2.5 DC, 7.11.2.6 smooth, the intra edge filter/upsample machinery 7.11.2.7/9/10/11/12, and 7.11.5 chroma-from-luma (CfL); Dr_Intra_Derivative / Intra_Edge_Kernel / Sm_Weights / Mode_To_Angle / Intra_Filter_Taps / Tx_Width_Log2 / Tx_Height_Log2 from the additional-tables annex; Round2 / Round2Signed from section 4; the intra-mode enum from the semantics. The CfL alpha derivation (read_cfl_alphas, 5.11.45 → CflAlphaU/V) and MaxLumaW/MaxLumaH, plus the get_filter_type neighbour-mode computation (7.11.2.8), are caller inputs until block/mode-info decode lands. Cross-checked by adversarial spec reviews (non-directional in 0.7.6, directional in 0.7.8, filter-intra in 0.7.9, chroma-from-luma in 0.7.10 — the last against **libaom** `av1/common/cfl.c` (`cfl_luma_subsampling_*`, `subtract_average`, `cfl_predict_lbd`) and **dav1d** `src/ipred_tmpl.c` (`cfl_pred`) as multi-source cross-checks).
- **AV1 dequantization** — spec section 7.12.2 is authoritative (`src/av1_quant.cyr`): the `Dc_Qlookup[3][256]` / `Ac_Qlookup[3][256]` quantizer tables (8/10/12-bit rows), `dc_q`/`ac_q` (the `Q_lookup[(BitDepth-8)>>1][Clip3(0,255,b)]` lookup), `get_qindex` (base_q_idx / delta-q / segment ALT_Q selection), and `get_dc_quant`/`get_ac_quant` (the per-plane `DeltaQ*Dc`/`DeltaQ*Ac`). The tables were transcribed by direct extraction from the spec markdown and cross-checked against **libaom** `av1/common/quant_common.c` (`dc_qlookup`/`ac_qlookup`, `av1_get_dc_quant`/`av1_get_ac_quant`, `get_qindex`); an adversarial review diffed every one of the 2×768 values against the spec. The reconstruct process (7.12.3) that consumes these lands in a later 0.7.x sub-bite.
- **AV1 reconstruct process** — spec section 7.12.3 is authoritative (`src/av1_recon.cyr`): the per-coefficient dequantization (`dq = Quant·q`, `dq2 = sign·((|dq| & 0xFFFFFF)/dqDenom)`, the `±2^(7+BitDepth)` clamp), `dqDenom` (2 for the 32-class, 4 for the 64-class transforms), the 2D inverse transform invocation (7.13.3), and the `flipUD`/`flipLR` (FLIPADST) residual add with `Clip1`. Cross-checked against **libaom** (`av1/decoder/decodeframe.c` `inverse_transform_block` + the `dqcoeff` dequant with the magnitude mask + large-transform shift, and the FLIPADST handling in `av1/common/av1_inv_txfm2d`). The quantizer-matrix path (7.12.3 step 1b) is deferred; the `Quant[]` coefficient array + resolved `q_dc`/`q_ac` are caller inputs until the `coeffs()` decode lands. An adversarial review verified the dequant math, the flip/dqDenom, the transform integration, and the known-answers (reusing the inverse-transform DC/IDTX/WHT vectors as oracles).
- **AV1 coefficient scan orders** — spec section 5.11.41 is authoritative (`src/av1_scan.cyr`): the `get_scan` / `get_default_scan` / `get_mrow_scan` / `get_mcol_scan` selection and the 32 `Default_Scan_*` / `Mrow_Scan_*` / `Mcol_Scan_*` tables from the additional-tables annex. Tables extracted from the spec markdown and cross-checked against **libaom** `av1/common/scan.c` (`av1_scan_orders`, the `default_scan_*` / `mrow_scan_*` / `mcol_scan_*` arrays); an adversarial review diffed every scan value and verified the size/type → scan selection. Each table is validated as a permutation of `0..len-1`. The `coeffs()` reading loop that walks these scans lands in a later 0.7.x sub-bite.
- **AV1 coefficient level contexts** — spec section 8.3.2 (CDF selection process) is authoritative (`src/av1_coeff.cyr`): `get_tx_class`, the `coeff_base` / `coeff_base_eob` context (`get_coeff_base_ctx`), the `coeff_br` context (`get_br_ctx`), and the `eob_pt` context, with the `Coeff_Base_Ctx_Offset` / `Coeff_Base_Pos_Ctx_Offset` / `Sig_Ref_Diff_Offset` / `Mag_Ref_Offset_With_Tx_Class` / `Adjusted_Tx_Size` tables. Cross-checked against **libaom** `av1/common/txb_common.h` (`get_nz_map_ctx` / the base-context offset, `get_br_ctx`, and the reference-offset tables); an adversarial review diffed every `Coeff_Base_Ctx_Offset` value and re-derived the context math. The `txb_skip` / `dc_sign` contexts (which need the per-tile neighbour arrays) and the `coeffs()` reading loop land in later 0.7.x sub-bites.
- **AV1 default coefficient CDFs** — the additional-tables annex is authoritative (`src/av1_coeffcdf.cyr`): the `Default_Txb_Skip_Cdf`, `Default_Eob_Pt_{16..1024}_Cdf`, `Default_Eob_Extra_Cdf`, `Default_Dc_Sign_Cdf`, and `Default_Coeff_Base_Eob_Cdf` initial adaptive-CDF tables (the `Default_Coeff_Base_Cdf` / `Default_Coeff_Br_Cdf` families land in later sub-bites), across the 4 `COEFF_CDF_Q_CTXS` quantizer buckets. Stored in the symbol coder's forward-cumulative format (N freqs ending in 32768 + a 0 count). Extracted from the spec (evaluating the `128 * x` products) and cross-checked against **libaom** `av1/common/token_cdfs.h` (accounting for libaom's AOM_CDF inverse-value convention); an adversarial review diffed every value and validated CDF structure.
- **rav1e** (Xiph) — encode-lane lineage; the 0.7.x encoder bring-up derives its structure from rav1e's keyframe path rather than libaom's, and the symbol-encoder byte/carry mechanics mirror `WriterBase` in `src/ec.rs`.

## H.264/AVC

- **ITU-T Rec. H.264 — Advanced video coding for generic audiovisual services** — AUTHORITATIVE. Sections used: 7.3.1/7.4.1 + Table 7-1 (NAL unit syntax/semantics), 7.4.1.1 (emulation prevention encapsulation), Annex B B.1.1/B.1.2 (byte-stream format, zero_byte, leading/trailing_zero_8bits), 7.3.2.1.1/7.4.2.1.1 (SPS syntax/semantics, CropUnitX/Y, Table 6-1 SubWidthC/SubHeightC), 7.3.2.1.1.1/7.4.2.1.1.1 (scaling_list, delta_scale range), 7.3.2.2/7.4.2.2 (PPS), 9.1/9.1.1 (ue(v)/se(v) exp-Golomb).
- **RFC 6184 — RTP Payload Format for H.264 Video** — §1.3 NAL header field recap; cross-check for header bit layout and type semantics.
- **openh264** (Cisco) — `codec/decoder/core/src/au_parser.cpp` ParseSps/ParsePps and bit-reader EPB handling; primary decoder cross-check (the implementation drishti's H.264 family replaces).
- **x264** — SPS/PPS serialization order (`encoder/set.c`); encode-side field-order cross-check.
- **JM reference software** (ITU/ISO) — `ldecod` InterpretSPS/InterpretPPS; reference-decoder semantics cross-check.
- **ffmpeg** — `libavcodec/h2645_parse.c`; start-code resync and 4-byte zero_byte attribution behavior cross-check.

## H.265/HEVC

- **ITU-T Rec. H.265 (HEVC)** — authoritative. Sections used at 0.7.0: 7.3.1.2 / 7.4.2.2 (two-byte NAL unit header semantics), Table 7-1 (nal_unit_type), Annex B B.2.2 (byte-stream NAL unit decoding), 7.3.1.1 / 7.4.2 (emulation_prevention_three_byte), 7.3.3 / 7.4.4 (profile_tier_level incl. the 43+1 reserved constraint tail), 7.3.2.1 / 7.4.3.1 (VPS), 7.3.2.2 / 7.4.3.2.1 (SPS + conformance-window crop math), 7.3.2.3 / 7.4.3.3.1 (PPS), Table 6-1 (SubWidthC / SubHeightC), A.4.1 / A.4.2 + Table A.8 (level limits — the dimension bomb guard).
- **libde265** (`nal.cc`, `nal-parser.cc`, `vps.cc`, `sps.cc`, `pps.cc`) — cross-check for NAL header layout, EPB behavior (incl. trailing-EPB strip), and parameter-set field ordering. The library this family replaces.
- **ffmpeg** (`libavcodec/h2645_parse.c`, `hevc_ps.c`, `hevc_parse.c`) — second cross-check for Annex-B scanning and PS parsing; drishti is deliberately stricter (rejects non-zero bytes before start codes instead of resyncing).
- **HM reference model** — planned conformance-vector source for the 0.9.x battery (not yet consumed).
- Real-stream sanity anchor: parameter-set headers pack to the canonical on-wire bytes `40 01` (VPS) / `42 01` (SPS) / `44 01` (PPS), asserted in the suite.

## VP8/VP9

- **RFC 6386 — "VP8 Data Format and Decoding Guide"** — authoritative
  for VP8, and code-as-spec (it carries the reference implementation).
  Sections used at 0.7.0: 7.1 (range-subdivision theory), 7.3
  (bool_decoder / bool_encoder / read_literal / flush_bool_encoder /
  add_one_to_output — ported verbatim, then bounds-hardened), 9.1
  (uncompressed data chunk: frame tag, start code, dimensions), 9.2
  (version number semantics, 0-3 defined), 9.x sign-magnitude coding
  of signed header fields (e.g. 9.6 delta_q).
- **"VP9 Bitstream & Decoding Process Specification"** v0.7
  (Grange / de Rivaz / Hunt, Google) — authoritative for VP9. Sections
  used: 6.2 uncompressed_header(), 6.2.1 frame_sync_code(), 6.2.2
  color_config(), 6.2.3 frame_size(), 6.2.4 render_size(), 7.2 frame
  type semantics, 7.2.2 color_space enumeration, 9.2 bool decoding
  (identical coder to VP8's — one implementation serves both).
- **libvpx** — `vp8/decoder/dboolhuff.h` (`vp8dx_decode_bool`),
  `vp8/encoder/boolhuff.c` (`vp8_encode_bool`),
  `vp9/decoder/vp9_decodeframe.c` (`read_uncompressed_header`,
  `read_bitdepth_colorspace_sampling`) — cross-check for the coder
  arithmetic, carry propagation, and the VP9 header rejection set
  ("4:4:4 color not supported in profile 0 or 2"). The library this
  family replaces.
- **ffmpeg** — `libavcodec/vp8.c` / `vp9.c` header parsers — second
  cross-check of field order and the profile bit split.
