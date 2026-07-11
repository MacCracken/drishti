# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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
