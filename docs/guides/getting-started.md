# Getting started with drishti

## Build

```sh
cyrius deps        # resolve stdlib deps into lib/
make build         # link-check: programs/smoke.cyr exercises every family
make test          # every tests/*.tcyr suite
make fuzz          # fuzz harness
make dist          # regenerate dist/drishti.cyr
```

## Consuming drishti

Consumers pull the single-file bundle from a tag:

```toml
[deps.drishti]
git = "https://github.com/MacCracken/drishti.git"
tag = "0.7.59"   # track the latest release tag
modules = ["dist/drishti.cyr"]
```

The bundle carries all four families; stdlib resolves from YOUR
manifest's `[deps].stdlib` (string, fmt, alloc, io, vec, str,
syscalls, assert).

## Walkthrough: read an IVF file's stream header

IVF is the test-bench container for AV1 and VP8/VP9 streams (fourccs
`AV01` / `VP80` / `VP90`):

```cyrius
var e = 0;
var r = dr_ivf_reader_init(buf, len, &e);      # 32-byte DKIF header
if (r == 0) { return e; }                       # DR_ERR_* on lies/truncation
var hdr = dr_ivf_reader_hdr(r);
# dr_ivf_hdr_* accessors give fourcc/width/height/frames;
# dr_ivf_reader_next(r, ...) walks the 12-byte-header frames.
```

## Walkthrough: parse an H.264 SPS to display dimensions

Annex-B in, cropped display size out — the classic "what resolution is
this stream" question:

```cyrius
# 1. scan the byte stream for NAL units (3-/4-byte start codes)
# 2. keep nal_unit_type 7 (SPS), strip emulation-prevention bytes
# 3. parse the RBSP
var e = 0;
var sps = h264_sps_parse(rbsp, rbsp_len, &e);
if (sps == 0) { return e; }
var w = h264_sps_width(sps);    # cropped display width
var h = h264_sps_height(sps);   # cropped display height
```

The AV1 equivalent is `av1_seq_parse` over a sequence-header OBU
payload (walk OBUs with `av1_obu_*` first); VP8/VP9 use
`vp8_parse_frame_hdr` / `vp9_parse_uncompressed_header` on frame data.

## Error discipline

Every parser returns a record or 0 with a `DR_ERR_*` / family error
code in the `&out_err` slot; bit-level readers/writers latch STICKY
errors (first code wins, later ops become no-ops). Nothing crashes on
hostile input — that's tested, and fuzzed.

## Adding a feature

> **Read [`verification.md`](verification.md) first.** It is the loop below in detail,
> plus the failure modes that shipped green without it — circular tests, aliased
> fixtures, digest blindness, silently-shadowed names. Every one cost a real defect.

1. Pick the bite — [`../development/state.md`](../development/state.md)'s "Picking this
   up cold" block names the next task concretely; the arc plan is in
   [`../development/roadmap.md`](../development/roadmap.md).
2. Derive from the spec; cite sections inline; cross-check ≥2 implementations (dav1d +
   libaom), never port from one; extend [`../sources.md`](../sources.md).
3. Write a **spec-literal reference port** in [`../../scripts/refs/`](../../scripts/refs/)
   — transcribed from the spec *text*, never from the Cyrius — and generate the known
   answers from it. This is what keeps the oracle independent of the code.
4. Keep modules flat (no includes); wire new modules in `src/main.cyr` AND
   `cyrius.cyml [lib].modules`, dependency order; prefix every symbol with the family
   prefix. Grep for the name first — cyrius silently shadows duplicates.
5. Test, then **mutation-verify**: break the code on purpose, confirm the suite goes red,
   restore, confirm green and byte-identical. *A test you have not seen fail is not
   evidence.*
6. Run an adversarial review (a `Workflow` of refute-by-default slices) for anything
   non-trivial.
7. Gate — `make build test fuzz lint fmt-check version-check`, reporting each exit code.
   Set `CYRIUS_NO_WARN_PIN_DRIFT=1 CYRIUS_NO_WARN_SHADOW_LIB=1` for clean output.
8. `make dist` to regenerate the bundle; update CHANGELOG + `../development/state.md` +
   the roadmap.

See [`../adr/template.md`](../adr/template.md) when a non-trivial
design choice deserves an ADR.
