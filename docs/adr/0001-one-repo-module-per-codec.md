# ADR 0001: One repo, module-per-codec (the shravan model)

- **Status**: Accepted
- **Date**: 2026-07-10
- **Deciders**: user (repo shape + AV1 lane merge), Claude (execution)

## Context

The crate registry (agnosticos
`docs/development/planning/shared-crates.md` § *Video Codec Projects*)
planned FIVE standalone repos: `drishti-av1` (dav1d-replacement),
`drishti-rav1e` (rav1e-replacement), `drishti-h264` (openh264-
replacement), `drishti-h265` (libde265-replacement), `drishti-vpx`
(libvpx-replacement), "each an independent repo following the shravan
model."

But the shravan model, read literally, is the opposite shape: shravan
is ONE repo where every audio codec (FLAC, Ogg, MP3, Opus, AAC, …)
lives as a flat `[lib]` module behind one distlib bundle. Scaffolding
began on the five-repo plan (2026-07-10) and immediately surfaced the
cost: four copies of a bitreader, two copies of exp-Golomb, two copies
of an IVF container module, five manifests/doc-trees/CI pipelines to
keep in sync.

## Decision

1. **One repo — `drishti` (दृष्टि, sight/vision)** — the video sibling
   of shravan, with codec families as flat `[lib]` modules:
   `src/av1_*.cyr`, `src/h264_*.cyr`, `src/h265_*.cyr`,
   `src/vpx_bool.cyr` + `src/vp8.cyr` + `src/vp9.cyr` over a shared
   core (`src/drishti.cyr`, `src/bits.cyr`, `src/ivf.cyr`). The five
   planned `drishti-*` repos are superseded (user decision 2026-07-10).
2. **Family charters** (what each replaces):
   - **AV1 — decode AND encode**, absorbing the registry's separate
     dav1d-replacement and rav1e-replacement rows into one charter.
     0.1.x lands the substrate both lanes share (OBU parse/walk/write,
     sequence header); the encode lane grows from the
     `av1_obu_write_header` seed, gated on own-decoder then
     cross-decoder round-trips.
   - **H.264/AVC — decode AND encode**, replacing openh264. The
     Annex-B NAL layer is bidirectional from day one (scan/strip for
     decode, EPB-insert/compose for encode); ITU-T Rec. H.264 is the
     single authoritative source, openh264/x264/JM/ffmpeg cross-checks
     only.
   - **H.265/HEVC — DECODE-ONLY**, replacing libde265, targeting
     Main/Main10 conformance-clean decode at 1.0. Encode is explicitly
     out of scope — no sovereign x265-replacement is registered; any
     future HEVC encode lane re-enters through the crate registry, not
     by growing inside this family.
   - **VP8/VP9 — decode AND encode**, replacing libvpx. The shared
     boolean coder (RFC 6386 7.3; the VP9 spec's 9.2 coder is
     identical) is built first as the family foundation.

## Consequences

- **Shared substrate is real, not speculative**: one bitreader, one
  leb128/uvlc/exp-Golomb implementation, one bit-writer (the encode
  seed), one IVF module — used by all families on day one. Entropy
  coders (CABAC / adaptive-CDF / boolean) deliberately stay
  per-family until real overlap proves out.
- **One namespace** — Cyrius has no module-private scoping and
  silently shadows duplicate fn names, so per-family prefixes are a
  hard rule (`dr_` core, `av1_`, `h264_`, `h265_`, `vbool_`, `vp8_`,
  `vp9_`) and error codes live in reserved per-family bands
  (`src/drishti.cyr`).
- **One dist bundle** — consumers (tarang, tazama, jalwa, aethersafta)
  pull `dist/drishti.cyr` and get every codec; no five-way version
  matrix.
- **One version line** — a cut ships whatever family bites landed;
  per-family phase plans live in
  [`roadmap.md`](../development/roadmap.md).
- The registry's *Video Codec Projects* table collapses to a single
  `drishti` row (updated in agnosticos alongside this scaffold).
