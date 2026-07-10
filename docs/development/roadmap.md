# drishti — Roadmap

> Milestone plan through v1.0. State lives in [`state.md`](state.md);
> this file is the sequencing — what ships, in what order, against
> what dependency gates.
>
> **Shape of the repo**: ONE repo, codec families as flat `[lib]`
> modules (the shravan model — see
> [ADR 0001](../adr/0001-one-repo-module-per-codec.md)). Each family
> phases below independently, but the repo cuts one version line; a
> cut ships whatever family bites landed.

## v1.0 criteria (ecosystem standard)

- [ ] Public API frozen — every exported symbol documented and tested
- [ ] All four families at their charter milestone (AV1 dec+enc, H.264
      dec+enc, H.265 dec, VP8/VP9 dec+enc) with conformance vectors green
- [ ] Benchmarks captured in `docs/benchmarks.md`
- [ ] At least one downstream consumer green (tarang / tazama / jalwa /
      aethersafta)
- [ ] CHANGELOG complete from v0.1.0 onward
- [ ] Security audit pass (`docs/audit/YYYY-MM-DD-audit.md`)

## Shared substrate (`drishti.cyr` / `bits.cyr` / `ivf.cyr`, prefix `dr_`)

- **0.1.x (THIS CUT, done)**: error record + family code bands, format
  sniff; MSB-first bitreader with sticky-error discipline; leb128
  read/write (AV1 4.10.5), uvlc (4.10.3), exp-Golomb ue/se read
  (H.264 9.1 / H.265 9.2) + bit writer with ue/se/leb128 write (the
  encode-lane seed); IVF container read/write (AV01/VP80/VP90); the
  external sticky-latch seam `dr_br_set_err` / `dr_bw_set_err` for
  family modules.
- **Later, demand-gated**:
  - **Entropy-coder consolidation watch** — CABAC (H.264/H.265),
    multi-symbol adaptive-CDF (AV1), and the boolean coder (VP8/VP9)
    stay per-family until real overlap proves out; do NOT unify
    speculatively.
  - **YUV frame-buffer / plane types** — a shared planar-frame record
    once two families emit pixels (their 0.3.x-0.4.x eras).
  - **Conformance-vector harness** — a shared runner once the first
    family reaches its conformance phase.
  - **Container growth** — IVF is the test-bench container; MP4/WebM
    demux is out of scope for drishti (a future container lib's job).

## AV1 — decode + encode (`src/av1_*.cyr`, prefix `av1_`)

Replaces **dav1d** (decode) and **rav1e** (encode) in one family — the registry's two planned repos merged here (2026-07-10).

- **0.1.x — OBU layer + sequence header** (THIS CUT, done): OBU header parse (spec 5.3.2/5.3.3, forbidden-bit rejection, reserved-bit tolerance per 6.2.2/6.2.3), leb128 obu_size (4.10.5 via core), OBU buffer walk (iterator, no-size-field tail OBUs, clean-END sentinel), `av1_obu_write_header` encode seed; `sequence_header_obu` summary parse (5.5.1) on both the reduced-still-picture and full operating-points paths (timing/decoder-model/operating-parameters skipped bit-exactly), color_config (5.5.2) → {profile, width, height, bitdepth 8/10/12, mono, still}. 185 assertions incl. adversarial vectors.
- **0.2.x — frame-header OBU**: uncompressed frame header parse, ref-frame state machine, frame-size overrides / superres, full-fidelity Av1Seq record growth.
- **0.3.x — entropy decoder**: multi-symbol adaptive-CDF arithmetic decoder (daala lineage) — the substrate every tile decode needs.
- **0.4.x — intra still-picture decode MILESTONE**: partition tree, intra prediction modes, inverse transforms; first pixels out (profile 0 keyframes).
- **0.5.x — inter + filters**: motion compensation, deblocking, CDEF, loop restoration, film grain synthesis.
- **0.6.x — conformance**: libaom/Argon vector runs, 10-bit paths, fuzz hardening.
- **0.7.x — ENCODE lane bring-up**: intra keyframe encoder (rav1e lineage) growing from the 0.1.x OBU-writer seed; gate = own-decoder round-trip first, then cross-decoder (dav1d/libaom) validation.

## H.264/AVC — decode + encode (`src/h264_*.cyr`, prefix `h264_`)

Replaces **openh264**.

- **0.1.x (THIS CUT, done)** — NAL layer + parameter sets. Annex-B byte-stream scan (3-/4-byte start codes with zero_byte attribution, garbage resync, trailing-zero strip, zero-copy yield), NAL header parse (Table 7-1, forbidden_zero_bit enforcement), emulation-prevention in BOTH directions (RBSP strip + EPB insert, round-trip proven), Annex-B composer with 7.4.1 header-semantics enforcement (the encode seed). Full SPS parse (7.3.2.1.1 incl. High-profile branch, scaling-list skip with early-out, computed cropped display dims) + minimal PPS parse (CAVLC/CABAC flag through redundant_pic_cnt_present_flag). 326-assertion suite: hand-built QCIF/1080p-crop/720p-High/interlaced vectors, exp-Golomb cross-check against the core writer, adversarial truncation/lying-value/bomb rejections, end-to-end wrap→scan→unwrap→parse.
- **0.2.x** — slice header parse + CAVLC residual entropy (9.2); pic_order_cnt_type 1 support; PPS High-profile tail (transform_8x8_mode_flag, pic scaling matrix, second_chroma_qp_index_offset via more_rbsp_data()).
- **0.3.x** — **intra I-frame decode MILESTONE**: Intra_4x4 / Intra_16x16 prediction modes, inverse 4x4 transform + dequant (8.5), reconstruction to planar YUV output.
- **0.4.x** — P slices: ref pic lists, quarter-pel luma / eighth-pel chroma motion compensation (8.4), deblocking filter (8.7).
- **0.5.x** — CABAC entropy decode (9.3) + High-profile 8x8 transform path.
- **0.6.x** — conformance: ITU/JM test-vector sweep, fuzz corpus expansion.
- **0.7.x** — ENCODE lane: Baseline intra encoder (SPS/PPS emission already seeded by the composer + core VLC writers) → P-frame encode.

## H.265/HEVC — decode-only (`src/h265_*.cyr`, prefix `h265_`)

Replaces **libde265**. Encode is explicitly OUT of this family's charter (ADR 0001).

- **0.1.x — NAL layer + parameter sets (THIS CUT, done)**: Annex-B byte-stream scan (B.2.2, strict — garbage before a start code is `DR_ERR_BAD_HEADER`, no resync), two-byte NAL unit header (7.3.1.2) with forbidden-bit and temporal-id-plus1 enforcement + VCL/IRAP/IDR predicates, EPB strip / RBSP extraction (7.3.1.1), profile_tier_level incl. sub-layer alignment (7.3.3), minimal VPS (7.3.2.1, reserved-0xffff captured-not-rejected), SPS through the sizing block with computed cropped display dims (7.3.2.2, Table 6-1 chroma-unit crop math, A.4.2 dimension bomb guard at 16888), minimal PPS through cu_qp_delta (7.3.2.3). 276 assertions green standalone, adversarial battery included.
- **0.2.x — slice plumbing**: slice_segment_header parse (7.3.6), remaining PPS tail (tiles / deblocking / scaling-list flags), CABAC engine + context init (9.3.2), parameter-set store keyed by vps/sps/pps ids.
- **0.3.x — intra-only decode MILESTONE**: CTU quadtree walk (7.3.8), all 35 intra prediction modes (8.4), inverse 4/8/16/32 transforms + reconstruction — decodes real Main-profile still-picture streams end to end.
- **0.4.x — inter + loop filters**: motion compensation (8.5), deblocking (8.7.2), SAO (8.7.3) — full Main-profile P/B-frame decode.
- **0.5.x — Main10 + conformance**: 10-bit code paths, HM conformance-vector battery, fuzz hardening of the slice/CTU layers.
- **1.0 — decode charter complete**: Main + Main10 conformance-clean.

## VP8/VP9 — decode + encode (`src/vpx_bool.cyr` + `src/vp8.cyr` + `src/vp9.cyr`, prefixes `vbool_` / `vp8_` / `vp9_`)

Replaces **libvpx**.

- **0.1.x (THIS CUT, done)** — the boolean arithmetic coder, DECODER
  and ENCODER (RFC 6386 7.3 verbatim arithmetic: split subdivision,
  carry-at-renormalization propagation, 4-byte flush), bounds-hardened
  with the core sticky-error discipline (the RFC reference reads
  unchecked past the buffer; this port latches `DR_ERR_TRUNCATED`) —
  the foundation every VP8/VP9 layer sits on, one implementation
  serving both codecs (the VP9 spec's 9.2 bool decoding is the
  identical coder). VP8 frame framing (RFC 6386 9.1: LE-packed 3-byte
  frame tag, keyframe start code + 14-bit dims/scales,
  lying-first_partition_size rejection) with a validated builder +
  byte-exact writer (encode seed). VP9 uncompressed header (spec
  6.2-6.2.4: frame marker, profile bits + profile-3 reserved check,
  show_existing_frame short-circuit, sync code, color config per
  profile incl. the RGB-in-profile-0/2 rejection, frame + render
  size). 287-assertion suite incl. two hand-computed encoder
  known-answer vectors and encode→decode round-trips across the
  probability range.
- **0.2.x — VP8 keyframe decode MILESTONE**: header partition
  (mode/prob decode), token/residual decode, dequant, inverse WHT/DCT,
  intra prediction, loop filter — first pixels out (RFC 6386 §§10-15).
- **0.3.x — VP8 inter frames**: MV decode (§17), motion compensation
  (§18), golden/altref reference state.
- **0.4.x — VP9 keyframe decode**: superblock partition trees, tree
  probs, transforms (VP9 spec §§8-9).
- **0.5.x — VP9 inter + loop filter**.
- **0.6.x — conformance**: libvpx test-vector sweep, fuzz hardening.
- **0.7.x — ENCODE lane**: VP8 keyframe encoder first (RFC 6386's
  reference code makes VP8 the natural encode entry), growing from the
  0.1.x bool-encoder + frame-tag-writer seeds; gate = own-decoder
  round-trip, then libvpx cross-decode.

## Out of scope (for v1.0)

- MP4 / WebM / Matroska demuxing — container work beyond IVF belongs
  to a future container lib, not drishti.
- HEVC encode (no sovereign x265-replacement is registered; re-enters
  via the crate registry or not at all).
- Hardware acceleration — drishti is the CPU reference; a GPU path is
  a post-1.0 lever behind mabda.
- Audio — that's shravan.
