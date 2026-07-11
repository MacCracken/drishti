# drishti

**दृष्टि (drishti — sight, vision) — sovereign video codecs for AGNOS.**
One library, four codec families, pure [Cyrius](https://github.com/MacCracken/cyrius):
**no C, no FFI, no libav\*.** The video sibling of
[shravan](https://github.com/MacCracken/shravan) (audio codecs): one
repo, codec families as flat modules behind a single distlib bundle.

| Family | Lanes | Replaces | Modules |
|--------|-------|----------|---------|
| **AV1** | decode + encode | dav1d + rav1e | `src/av1_obu.cyr`, `src/av1_seq.cyr` |
| **H.264/AVC** | decode + encode | openh264 | `src/h264_nal.cyr`, `src/h264_ps.cyr` |
| **H.265/HEVC** | decode only | libde265 | `src/h265_nal.cyr`, `src/h265_ps.cyr` |
| **VP8/VP9** | decode + encode | libvpx | `src/vpx_bool.cyr`, `src/vp8.cyr`, `src/vp9.cyr` |

Shared core (`src/drishti.cyr`, `src/bits.cyr`, `src/ivf.cyr`): error
records + format sniff, an MSB-first bitreader/bitwriter with leb128 /
uvlc / exp-Golomb (the VLCs of all four families), and the IVF
test-bench container.

## Status — 0.7.1 (AV1 decode arc open)

The bitstream/container/header layer of every family is built, spec-
derived, and adversarially tested (3,349 suite assertions + 1,140 fuzz
assertions, all green). The 0.7.x AV1 arc has opened with the full
uncompressed frame header:

- **AV1** — OBU framing (parse / walk / write) + full-fidelity
  sequence-header parse + the complete uncompressed frame header
  (5.9.2, all frame types, cursor-true) with the reference-frame state
  machine (set_frame_refs, frame_size_with_refs, ref update)
- **H.264** — Annex-B scan, NAL headers, emulation-prevention both
  directions, full SPS (incl. High-profile branch + crop math), PPS
- **H.265** — Annex-B scan, two-byte NAL headers, profile_tier_level,
  VPS/SPS/PPS with crop math and dimension-bomb guards
- **VP8/VP9** — the RFC 6386 boolean arithmetic coder (decoder AND
  encoder, bounds-hardened), VP8 frame framing + byte-exact writer,
  VP9 uncompressed header

Pixels come next: the road to 1.0 is **one minor arc per codec** —
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
  throughout, fuzzed from day one.

## License

GPL-3.0-only
