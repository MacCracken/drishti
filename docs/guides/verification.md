# How drishti verifies a spec transcription

A how-to for the loop used on every AV1 bite from 0.7.57 onward. It is not ceremony:
each step below exists because skipping it shipped a real defect that the step then
caught. The failures are named so you can judge the technique rather than take it on
faith.

The core problem: **a codec is a transcription, and a transcription can be
self-consistently wrong.** Tests written from the same understanding as the code agree
with the code and prove nothing. Everything here is an attack on that.

## The loop

1. **Derive from the spec, citing the section.** Fetch the actual spec text
   (`AOMediaCodec/av1-spec`, raw.githubusercontent), quote the pseudocode in a comment,
   cross-check against ≥2 implementations (dav1d + libaom). Never port from one.
   Record the citation in [`docs/sources.md`](../sources.md).
2. **Write a spec-literal reference port** in `scripts/refs/` — transcribed from the
   spec *text*, never from the Cyrius. Generate the known answers from it. This is what
   makes the expected values an independent oracle instead of a restatement of the code.
   See [`scripts/refs/README.md`](../../scripts/refs/README.md).
3. **Implement**, family-prefixed, in a flat module.
4. **Mutation-verify every test.** Break the code on purpose; confirm the suite goes red;
   restore and confirm green + byte-identical. **A test you have not seen fail is not
   evidence.** This is the step that pays: it has caught more than the reviews.
5. **Adversarial review** (a `Workflow` with refute-by-default verifiers).
6. **Gate**: `make build test fuzz lint fmt-check version-check` — report per-gate exit
   codes, never collapse to "green" while any is red.

```sh
export CYRIUS_NO_WARN_PIN_DRIFT=1 CYRIUS_NO_WARN_SHADOW_LIB=1   # both warnings are benign
python3 scripts/refs/nbctx_ref.py        # regenerate a port's known answers
```

## The failure modes, and what each costs

Each of these shipped green. Each is now a standing check.

### Circular tests — the fill and the check share an accessor

If `*_fill()` writes a table through the same accessor the test reads it back through, a
base/stride error **cancels out exactly**. At 0.7.73 two shipping-breaking CDF stride
bugs passed the entire 24k-assertion suite.

> **Do:** pin **absolute** offsets in a layout test derived from the documented layout,
> not from the accessor. Assert `accessor(cc, ROW_COUNT) - cc == <next group's base>` —
> that pins base *and* stride *and* row count in one line — and pin the last group's end
> to `*_SIZE`, so a field added later cannot silently overflow the alloc. Assert the
> trailing count/terminator slots too: those are exactly where an overlapping row's
> damage lands.

### Aliased fixtures — two things that always hold the same value

If two independent fields, planes, or arguments never differ in a fixture, **confusing
them is invisible**. This has bitten three times:

| Bite | Aliased | Survived |
|---|---|---|
| 0.7.76 | a `ref_count_ctx(a, b)` pair, where the histogram is symmetric | swapping the pair (inverts ctx 0↔2) passed the whole suite |
| 0.7.77 | `CompGroupIdxs` == `CompoundIdxs` in every fixture | reading the wrong plane, in both readers *and* the writer |
| 0.7.79 | a uniform, **square** fixture (`w4 == h4`) | the top-right probe's `w4`/`h4` swap; the 112 clamp; the 8×8 step |

> **Do:** give independent things **different** values, and **poison** the one a function
> must not read (`1 - v`, `3 - v`). Use a **non-square** block. Cover the boundary
> constant itself — `ref1 == INTRA_FRAME` was the sole input separating `>` from `>=`,
> never exercised, and live (5.11.28 sets exactly that).

### Digest blindness — an exhaustive sum is not exhaustive proof

A sum (and often the per-value histogram) over a **symmetric** sweep is **invariant**
under the very permutation you are trying to catch. Enumerating 26,244 combinations did
not catch a swapped pair, because the distribution was symmetric.

> **Do:** treat digests as a distribution check, not a correctness check. Assert
> **direction** explicitly — drive each context to both its low and high value. The
> poisoned known answers carry the weight; the digest catches what they miss.

### Self-round-trips cannot catch a shared bug

`encode → decode` through the same CDF passes for **any** monotone table ending at 32768.
A wrong default value is fully symmetric and invisible.

> **Do:** diff every default table per-value against §10 (that is the ground truth), and
> keep the round-trip for what it does prove: encoder/decoder inverse-ness.

### Gated code — a closed gate must consume nothing

If reader and writer disagree about how many symbols a *closed* gate consumes, the
arithmetic decoder desyncs **silently**.

> **Do:** write a **marker symbol after the gated block** and assert it decodes. Any
> disagreement fails loudly. (0.7.78.)

### Reused records — every field must be written unconditionally

`av1_nbctx_setup` wrote its cached fields only inside the `avail` branches, so a **reused**
record (one per block, as the tile decode will hold) let an unavailable neighbour inherit
the *previous* block's values. Found at 0.7.77.

> **Do:** default every output field at the top and write it unconditionally. Test by
> decoding into a deliberately **dirtied** record and asserting a fresh-record result.

### Duplicate names shadow silently

Cyrius has no module-private scoping and **silently shadows duplicate `fn` names**
(last-def-wins, warn-only). At 0.7.78 a new driver collided with an existing leaf — no
error. Convention: **leaf = `_sym` suffix, driver = plain name**
(`av1_read_compound_type_sym` / `av1_read_compound_type`).

```sh
grep -hoE '^fn [a-z0-9_]+' src/*.cyr | sort | uniq -d     # must be empty
```

### A symbol desync is not always a misparse — check buffer adjacency first

E2d cost two sessions. A 128-superblock keyframe desynced at `av1_sym_dec_exit`, so the
search went where a desync usually lives: the partition CDF, the bsl-5 alphabet, the
context derivations, the tile geometry. `Default_Partition_W128_Cdf` was cross-checked
byte-identical against four independent sources. All of it was correct. The actual cause
was `av1_clear_cdef` storing `-1` **past the end of the CdefIdx grid**, into whatever the
bump allocator had handed out next — the CDF blob directly on the CDEF-off reproducers, the
CDEF read context then the blob on a CDEF-enabled stream, the MV grid on an inter frame. A
CDF row went non-monotone and the decoder desynced reading a table it had corrupted itself.

Two properties made it invisible. The allocator is a **headerless bump allocator**, so
everything past the bump pointer *is* the blast radius and there is no guard page or header
to trip — and which object gets hit varies with the stream, so the symptom moves. And the
overflow's landing offset is a pure function of the frame's `MiCols * MiRows`, so whether it
desynced depended on whether that stream ever read the poisoned context — which reads as
"content-dependent" and sends you hunting for a content-dependent *parse* bug. The passing
control frame was overflowing too.

> **Do:** when a desync's *preceding* pixels are correct, the fault is in what is read —
> which includes the tables being read from. Before re-deriving a spec table, check whether
> anything writes near the buffer that holds it: `grep` the module's `alloc(` sites, and
> confirm every store into a flattened 2-D grid is bounded on **both** axes. A spec that
> writes a conceptual 2-D array tolerates an out-of-frame write; a flattened one does not.

### A canary must span the blast radius

The bounds witness for the above first used a 16-word canary after the grid. It caught the
in-bounds *row aliasing* and reported green for the actual heap overflow — which reaches 433
words past the grid and so flew clean over a 16-word canary. Found by mutation, not by
review.

> **Do:** compute the maximum out-of-bounds index the defect can reach, size the canary to
> cover it, and **assert that arithmetic in the test** alongside the adjacency assert. Then
> mutate each bound separately — a mutant that breaks only the row bound must redden a
> different assertion than one that breaks only the column bound, or you have one witness
> wearing two hats.

### One geometry cannot pin a two-axis bound

The same witness then passed three more mutants: `<=` on either bound, and the two axes
**swapped**. Its geometry (stride 48, rows 40) was the reproducer's, which felt like the
authoritative choice — but no origin in it evaluates either predicate at exact equality
(`r+16` is 48 against rows 40, strictly greater), so off-by-one survives; and the two bounds
never disagree at any origin, so swapping them changes nothing. A second geometry (stride 80,
rows 48) fixes both: origins exist where `r+16 == rows` and `c+16 == stride` exactly, and the
bounds sit on opposite sides of a superblock boundary so a swap writes out of bounds.

> **Do:** for a bound on two axes, pick the geometry to make the axes **disagree**, and
> include an origin that lands exactly ON each boundary. The geometry that reproduces the bug
> is documentation; it is not automatically the geometry that pins the fix. Mutate `<`→`<=`
> and swap the axes — if either survives, the witness is measuring one axis twice.

### An exhausted corpus is not a correct decoder

The eight published libaom vectors all decoded their keyframe bit-exactly, and the natural
reading was "the keyframe path is externally verified." It wasn't. **Every published height
is a multiple of 16**, and `scripts/conformance.sh`'s generated corpus was hardcoded to
64x64 — so no case in the gate had a bottom block that overhangs the frame. A sweep of 48
ordinary `aomenc` geometries found 20 of them decoding with wrong chroma (E2e), a defect
present the whole time in a code path the corpus structurally could not reach.

This is [[fixture-alignment-monoculture]] again, one level out: the habit of assuming an
*external* corpus is unbiased. libaom's vectors were chosen to exercise *features*, not
geometries.

> **Do:** when a gate goes all-green, ask what its inputs have in COMMON rather than what
> they cover. Vary the axis nobody chose deliberately — dimensions, alignment, subsampling,
> bit depth — and sweep it against the external reference before believing the green. A
> conformance pass bounds the corpus; only a sweep bounds the decoder.

## Running an adversarial review

Spawn a `Workflow` whose slices attack different dimensions (spec fidelity / memory
safety / test adequacy), each finding checked by a **refute-by-default** verifier. Two
hard-won rules:

- **A worktree does not see uncommitted work.** The user handles all git, so a bite is
  always uncommitted when reviewed. At 0.7.76 the worktrees came up at the previous
  release and two slices reported the code "does not exist" — a review of the wrong
  version that reads exactly like a clean pass. Either copy the working-tree files into
  the worktree **and verify they landed**, or skip isolation and snapshot instead.
- **Without isolation, agents mutation-test in your live tree.** At 0.7.73/0.7.74 this
  produced phantom gate failures that were not reproducible. Snapshot
  (`md5sum src/*.cyr tests/*.tcyr > pre.md5`) and never take a gate reading while a
  workflow is in flight.

A review returning "0 confirmed" because the target was absent is **worse than no
review**. Always verify the agents saw the code.

## What good looks like

A bite is done when: the spec section is cited; a committed port generates the known
answers; every test has been **seen to fail** against a deliberate bug; the review's
findings are resolved or refuted on the merits; and all six gates report their real exit
codes, green.
