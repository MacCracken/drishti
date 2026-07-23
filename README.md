# drishti

**दृष्टि (drishti — sight, vision) — sovereign video codecs for AGNOS.**
One library, four codec families, pure [Cyrius](https://github.com/MacCracken/cyrius):
**no C, no FFI, no libav\*.** The video sibling of
[shravan](https://github.com/MacCracken/shravan) (audio codecs): one
repo, codec families as flat modules behind a single distlib bundle.

| Family | Lanes | Replaces | Modules |
|--------|-------|----------|---------|
| **AV1** | decode + encode | dav1d + rav1e | 29 × `src/av1_*.cyr` — keyframes decode to pixels; every inter-prediction PRIMITIVE is in (all four warp forms, OBMC, compound and masked modes, the temporal-MV arc, every interpolation filter, scaled references) — SIX published libaom conformance vectors decode their keyframe bit-exactly (0.7.126); segmentation decodes (0.7.125); inter FRAMES still diverge (reconstruction rounding + an entropy desync), and delta-q/delta-lf still reject |
| **H.264/AVC** | decode + encode | openh264 | `src/h264_nal.cyr`, `src/h264_ps.cyr` — bitstream/header layer |
| **H.265/HEVC** | decode only | libde265 | `src/h265_nal.cyr`, `src/h265_ps.cyr` — bitstream/header layer |
| **VP8/VP9** | decode + encode | libvpx | `src/vpx_bool.cyr`, `src/vp8.cyr`, `src/vp9.cyr` — bitstream/header layer |

Per-module surface: [`docs/development/state.md`](docs/development/state.md). Only AV1 has
gone past the header layer so far — the other three are at their 0.7.0 baseline, awaiting
their arcs (0.8.x–0.10.x).

Shared core (`src/drishti.cyr`, `src/bits.cyr`, `src/ivf.cyr`): error
records + format sniff, an MSB-first bitreader/bitwriter with leb128 /
uvlc / exp-Golomb (the VLCs of all four families), and the IVF
test-bench container.

## Status — 0.7.125 (AV1: a complete profile-0 KEYFRAME decoder; MINIMAL inter frames also decode end-to-end from real bytes with WITNESSED motion — single-ref forward-only (0.7.119), a realistic order-hint header, a COMPOUND / backward-reference frame (0.7.120), and the sign-bias MV negation witnessed to reach pixels. Cross-frame CDF inheritance (7.20/7.21) is implemented + witnessed (0.7.121). As of 0.7.123 an **intra block inside an inter frame decodes to PIXELS** — the mode-info fork (0.7.122) plus the reconstruction (intra predict + residual, reusing the keyframe `av1_residual`; a DC intra block with a residual round-trips to a DC-predict + reconstruct oracle, and as of 0.7.124 a DIRECTIONAL intra block in a mixed tile correctly reads its inter neighbour’s above-right via BlockDecoded). As of 0.7.125 **SEGMENTATION decodes end-to-end to PIXELS** on both lanes (0.7.125 D1) — the segment-id map (5.11.9/10/11 spatial predictor) is read and per-segment `SEG_LVL_ALT_Q` reaches the dequant, so a 2-segment frame reconstructs different pixels per segment; the temporal-predicted / whole-map-copy / feature-inheritance configs (which need a DPB-saved seg map) still reject cleanly. The "encoder" is a plan-driven bitstream writer. As of 0.7.126 **SIX PUBLISHED libaom conformance vectors decode their keyframe BIT-EXACTLY** against libaom's own reference MD5s (`make conformance`) — 128x128 superblocks (libaom's default, and previously a blanket reject) now decode. Known keyframe gaps: the lossless path and loop restoration; inter frames still diverge. See docs/development/roadmap.md "HONEST STATUS" for the phased, checkable remainder — no "% done" is printed)

The bitstream/container/header layer of every family is built, spec-
derived, and adversarially tested (30,085 suite assertions + 7,410 fuzz
assertions, all green). The 0.7.x AV1 arc has reached its first
milestone — **profile-0 AV1 keyframes decode end-to-end to pixels, from raw
OBU bytes** — and the **in-loop filter layer is complete**: the **deblocking
loop filter** (`av1_deblock.cyr` — kernels + the whole-frame edge loop/driver),
the **CDEF** filter (`av1_cdef.cyr` — kernels + driver + the wired `cdef_idx`
read), and **loop restoration** (`av1_lr.cyr`, spec 7.17 — both **Wiener** +
**self-guided/SGR** kernels, the stripe-loop driver, the full `read_lr` bitstream
parse, and the `decode_tile` wiring) are all done and **chained** by the in-loop
filter pipeline (`av1_decode.cyr`, `av1_apply_loop_filters`), with **superres**
(spec 7.16) upscaling spliced in between CDEF and LR. The **frame-header filter
activation** step (`av1_lr_params_from_fh` + `av1_activate_intra_filters`) builds
the LR params and attaches the CDEF context straight from the parsed header.
The **tile-group OBU parser** (`av1_tile_group_parse`, spec 5.11.1) extracts each
tile's byte range (bounds-checked against hostile sizes), and the **frame-level
driver** (`av1_decode_frame`) ties it all together: from a parsed sequence + frame
header + the tile-group payload it assembles, decodes, and filters a keyframe
**all the way to pixels** — now for **multi-tile** frames (0.7.47–0.7.51) and
**use_superres** streams too. The **OBU-stream walk** (`av1_decode_obus`) closes the
loop: it parses the sequence + frame headers from raw OBU bytes and drives
`av1_decode_frame`, handling **both** the separate-OBU form (TD + sequence-header +
frame-header + tile-group OBUs) **and** the combined FRAME OBU (type 6 — the common
real-stream form; it byte-splits off the tile group per spec 5.10). A complete
keyframe bitstream decodes **from raw bytes all the way to pixels** — both forms
verified end-to-end, at 8/10/12-bit, single- and multi-tile, with or without
superres. **Inter prediction — every PRIMITIVE is in** (this section previously claimed "only
scaled-reference / BILINEAR MC remains"; both landed at 0.7.108/0.7.110, and the real remaining work is
not a primitive — see below): the leaf motion-compensation kernels (`av1_mc.cyr`: **Subpel_Filters**
0.7.57, **`put_8tap`** 0.7.58, **`emu_edge`** 0.7.59, each reference-confirmed against
dav1d) plus the **MC driver** (0.7.60), the **reference-frame buffer/DPB** + multi-frame
decode (`av1_dpb.cyr` 0.7.61), the complete **MV-prediction** arc (`av1_mv.cyr` 0.7.62–0.7.65),
the **complete inter mode-info bitstream-read layer** (`av1_intermode.cyr` 0.7.66–0.7.73), the
**MI-grid population** (0.7.74), **ALL the neighbour CDF contexts** (0.7.75–0.7.77), the **inter tile
decode** (0.7.84+), the three **motion modes** (LOCALWARP / GLOBALWARP / OBMC), the **temporal-MV arc**
(0.7.102–0.7.104), **inter-intra warp-blend** (0.7.105), **compound-global warp** (0.7.106), **BILINEAR**
(0.7.108) and **scaled-reference MC** (0.7.110). **As of 0.7.119 a MINIMAL inter frame decodes end-to-end
with witnessed motion** (single-ref, forward-only, degenerate/no-order-hint header) — the first time these
primitives ran from real bytes and moved pixels. What actually remains before a real `.ivf` decodes: the
**realistic order-hint header**, **compound / backward references** (needs `RefFrameSignBias`, never
derived), **cross-frame CDF inheritance**, the **intra-block fork** inside an inter frame, **segmentation**
and **delta-q/lf** — none of which is a "primitive." The honest, phased, checkable breakdown is in
[`docs/development/roadmap.md`](docs/development/roadmap.md) under **HONEST STATUS**.
The frame header, the entropy substrate, the shared YUV frame buffer, the
inverse transforms, the full intra-prediction layer, the dequantizer,
the reconstruct glue, the **coefficient reading loop** (with adaptive
CDFs), the block-decode CDF tables, the intra **mode-info reads**, the
**transform-size read**, the **transform-type derivation**, the
**residual driver**, the **partition tree**, and the **tile/frame loop**
(`decode_tile` driving a whole keyframe into a `DrFrame`) are in:

- **AV1** — OBU framing (parse / walk / write) + full-fidelity
  sequence-header parse + the complete uncompressed frame header
  (5.9.2, all frame types, cursor-true) with the reference-frame state
  machine (set_frame_refs, frame_size_with_refs, ref update) + the
  multi-symbol adaptive-CDF arithmetic (symbol) coder (spec 8.2,
  decoder + encoder) + the inverse transform block (spec 7.13: DCT /
  ADST / identity / WHT + the 2D driver) + the complete intra prediction
  layer (spec 7.11.2 + 7.11.5: DC / PAETH / SMOOTH + full directional with
  the intra edge filter/upsample + recursive filter-intra + chroma-from-
  luma, into the shared frame buffer) + the dequantizer (spec 7.12.2:
  Dc/Ac Qlookup + get_dc_quant/get_ac_quant) + the reconstruct process
  (spec 7.12.3: dequant → inverse transform → residual add → pixels) + the
  coefficient scan orders (spec 5.11.41: get_scan + the 32 scan tables) +
  the coefficient level contexts (spec 8.3.2: get_coeff_base_ctx / get_br_ctx)
  + all seven default coefficient CDF families (txb_skip / eob / dc_sign /
  coeff_base / coeff_br) + the coeffs() reading loop (spec 5.11.39: decode +
  inverse encode + the adaptive per-tile CDF context, round-trip tested) +
  the default non-coeff CDF tables (partition / mode / tx / CfL …) + the
  intra mode-info reads (spec 5.11.16 `intra_frame_mode_info`: skip / y+uv
  mode / CfL alphas / angle-delta / filter-intra, decode + inverse encode)
  with the shared block-size conversion tables + the intra transform-size
  read (spec 5.11.15 `read_tx_size`: the tx_depth split of Max_Tx_Size_Rect,
  decode + inverse encode) + the transform-type derivation (spec 5.11.48/40
  `compute_tx_type`: `intra_tx_type` read + `get_tx_set` + `Mode_To_Txfm`,
  spliced into the coeffs loop) + the residual driver (spec 5.11.34/36
  `residual()` / `transform_block()`: predict_intra → coeffs() → reconstruct()
  per tx block, with CfL + the BlockDecoded availability grid) — a transform
  block now decodes to pixels end-to-end — + the partition tree (spec 5.11.4/5
  `decode_partition` / `decode_block`: the recursive superblock partition + the
  per-block mode-info → tx-size → residual orchestration + MI grids, with a
  paired encode lane) + the tile/frame loop (spec 5.11.2 `decode_tile`: the
  superblock loop + CDF-context / symbol init, driving a whole keyframe into a
  `DrFrame`) — **a profile-0 AV1 keyframe decodes end-to-end to pixels** — + the
  **in-loop filter layer** (deblocking 7.14 / CDEF 7.15 / loop restoration 7.17,
  chained in `av1_apply_loop_filters`) + **superres** upscaling (spec 7.16) +
  **multi-tile** frames (frame-addressed MI grids + tile-group accumulation) +
  **8/10/12-bit** + **inter prediction** primitives complete (the MC kernels + driver, the DPB,
  the full MV-prediction + temporal-MV arc, all compound + inter-intra prediction, and all
  four warp forms + OBMC — every MC geometry, motion mode, compound/masked form, interpolation filter and reference geometry is in (scaled-reference MC wired 0.7.110, BILINEAR 0.7.108); an inter FRAME still does not decode, because segmentation / delta-q / delta-lf / an intra block inside an inter frame all reject the tile)
- **H.264** — Annex-B scan, NAL headers, emulation-prevention both
  directions, full SPS (incl. High-profile branch + crop math), PPS
- **H.265** — Annex-B scan, two-byte NAL headers, profile_tier_level,
  VPS/SPS/PPS with crop math and dimension-bomb guards
- **VP8/VP9** — the RFC 6386 boolean arithmetic coder (decoder AND
  encoder, bounds-hardened), VP8 frame framing + byte-exact writer,
  VP9 uncompressed header

A profile-0 AV1 **keyframe** decodes end-to-end to pixels — single- or
multi-tile, with or without superres, at 8/10/12-bit — through the full
in-loop filter chain. That is where the decoder actually is: a complete
**keyframe** decoder. The inter-prediction machinery (MC, all four warp
forms, OBMC, compound, temporal MVs, scaled references, BILINEAR) is built
as **primitives** but **no real inter frame decodes yet** — a non-key frame
rejects at cross-frame CDF inheritance and the intra-block fork. Conformance
vectors and a real encoder have **not been started** (what ships as "encode"
is a plan-driven bitstream writer, not an encoder). The honest, phased,
checkable breakdown — and why no "% done" is printed — is in
[`docs/development/roadmap.md`](docs/development/roadmap.md) under
**HONEST STATUS**. The road to 1.0 is **one minor arc per codec** —
**0.7.x** brings AV1 to 100%, **0.8.x** H.264, **0.9.x** H.265,
**0.10.x** VP8/VP9 — then a cross-family **audit** arc (0.11.x) and a
**freeze/documentation** arc (0.12.x) before the 1.0.0 close-out.
Encode lanes grow from the writer seeds already shipped. Full plan:
[`docs/development/roadmap.md`](docs/development/roadmap.md).

## Build

```sh
cyrius deps                                          # resolve stdlib deps into lib/
make build                                           # link-check (programs/smoke.cyr — exercises all families)
make test                                            # every tests/*.tcyr suite
make fuzz                                            # fuzz harness (tests/*.fcyr)
make bench                                           # benchmarks (tests/*.bcyr)
make dist                                            # regenerate dist/drishti.cyr
```

Consumers (tarang, tazama, jalwa, aethersafta) pull `dist/drishti.cyr`
via a `[deps.drishti]` entry pointing at a git tag.

## Design

- **One repo, module-per-codec** — see
  [ADR 0001](docs/adr/0001-one-repo-module-per-codec.md) for why the
  five planned `drishti-*` repos collapsed into this one.
- **Spec-first, multi-source** — every parse step is derived from the
  spec (sections cited inline) and cross-checked against multiple
  implementations, never ported from one. Citations:
  [`docs/sources.md`](docs/sources.md).
- **Trust no input byte** — encoded video is hostile data: every
  length checked, lying headers rejected, sticky error discipline
  throughout, fuzz-tested from day one at the container/VLC layer (tests/drishti.fcyr), and the AV1 decode path since 0.7.118 (tests/av1_decode.fcyr — mutated OBU streams into av1_decode_obus / av1_decode_stream).

## License

GPL-3.0-only
