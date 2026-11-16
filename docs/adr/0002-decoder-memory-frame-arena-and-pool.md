# 0002 — Decoder memory: a frame arena and a frame pool, not per-object freeing

**Status**: Accepted
**Date**: 2026-11-15

## Context

drishti allocates from the Cyrius stdlib allocator, a bump allocator with no `free`. That was harmless while
drishti decoded a frame or two per process. It is not harmless for a streaming decoder. 0.8.5 measured every
decoded frame allocating ~35–60 bytes per pixel that nothing ever reclaimed: ~5.7 MB for a 352x288 frame, which
extrapolates to ~100 MB for a 1080p one. The allocations were tiles, MI grids, CDF contexts, per-block records, the
reconstruction and its CDEF, loop-restoration and upscaled copies. A long or large stream ends in a real out-of-memory.

Almost all of that memory is dead once its frame is decoded. A few things outlive the frame:
- the reconstructed frames the reference slots hold;
- the blocks the slots save (motion field, CDF bundle, segmentation map, film-grain parameters);
- the sequence header, the camera header in large-scale tile mode, and the shown frame until the caller reads it;
- the lazily-built tables and persistent scratch.

Before 0.8.5 those were pointers into the same never-freed memory, so nothing had to know which was which.

## Decision

**A streaming decoder serves each frame's working memory from an arena it rewinds at every frame start, takes its
frames from a pool it sweeps at every frame start, and keeps only what outlives a frame.**

- **The arena.** `dr_alloc` is the one allocation funnel (0.8.5 bite 7). While `av1_decoder_decode` runs it is
  scoped to the decoder's `DrArena`. The arena is a chain of chunks that `dr_arena_reset` rewinds, keeping the chain,
  so a stream settles at its high-water mark. Allocations are zeroed, as fresh bump memory always was.
- **The frame pool.** While the pool is active, `dr_frame_new` takes from the decoder's `DrFramePool`. At each frame
  start the decoder sweeps it, then roots what it still holds: the eight reference slots, the last decoded and last
  shown frames, the anchors, and the grain output. A free frame whose plane buffers are large enough is laid out
  again and zeroed.
- **Kept memory.** What outlives a frame is allocated with `dr_alloc_keep` or inside
  `dr_persist_begin` / `dr_persist_end`.
- **Slot copies.** A reference slot's saved blocks are the slot's own copies, made at the save. They used to be
  pointers to the frame decoder's buffers.

The returned frame is valid until the next `av1_decoder_decode` call on the same decoder.

## Consequences

- **Positive** — a decoder's memory is bounded. Every committed reproducer, fed four times through one decoder,
  takes no bytes from the global allocator after its second pass (`make conformance`, "the memory bound"). The
  bound needs no `free` and no ownership tracking at ~200 allocation sites: only the escapes are marked, and they
  were few.
- **Negative** — every allocation that outlives a frame must be kept. One that is not is a use-after-reset: a
  silent wrong picture, not a crash. `make conformance` poisons the arena at every reset (0xA5) and checks every
  output against its reference, so a missed escape shows as an md5 mismatch. Mutation testing confirmed it for each
  root and each copy. The returned frame's lifetime shortens from "for ever" to "until the next call", which is an
  API contract change. Saving copies costs a memcpy per refreshed slot: 63 KB for a CDF bundle, more for a
  segmentation map.
- **Neutral** — the arena's high-water mark includes per-block scratch that could be persistent (as CDEF, deblocking
  and loop restoration's became in bite 7); hoisting the rest would shrink it. The one-shot entry points
  (`av1_decode_frame`, `av1_decode_obus`) are not scoped and still take from the global allocator; the streaming
  decoder is the bounded API.

## Alternatives considered

- **A real allocator with `free`** (a free list, or refcounting). Every one of ~200 allocation sites would need a
  matching release on every path, error paths included. drishti's error paths abandon records by design, so every
  error path would have to be rewritten. That is a large, error-prone change for no benefit over freeing a whole
  frame at once.
- **`alloc_reset` per frame** (the stdlib's whole-heap reset). It also frees the decoder, the lazily-built tables
  and the application's own memory.
- **Two arenas, alternating per frame.** An object would then survive exactly one extra frame. But a single
  `av1_decoder_decode` call can span several frames (a hidden frame plus a shown one, or two spatial layers). The
  OBU iterator, the shown frame and the sequence header would die mid-call.
- **Frames copied into slot-owned buffers, no pool.** That means a whole-frame copy per refreshed slot (eight on a
  keyframe), where the pool costs nothing beyond its sweep.
- **Persistent per-block scratch alone** (bite 7's approach). It bounds only the per-block allocations. The
  frame-sized ones (frames, grids, CDF contexts) dominate, and they are per frame by nature.
