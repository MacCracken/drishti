# 001 — Inside a decoder, `dr_alloc` memory dies at the next frame start

**True since 0.8.5** ([ADR 0002](../adr/0002-decoder-memory-frame-arena-and-pool.md)).

While `av1_decoder_decode` runs, every `dr_alloc` is served from the decoder's frame arena (`dr_alloc_scope`). The
arena is rewound when the next frame starts: a frame header (`FRAME_HEADER` or `FRAME`, outside large-scale tile
mode), a tile list, or a call with no frame pending. **Anything allocated with `dr_alloc` during a decode is
therefore dead by the next frame**, whatever pointer still refers to it.

So a new allocation that must outlive its frame has to say so:

| It is... | Allocate it with |
|---|---|
| a lazily-built table or persistent scratch, cached in a module global | `dr_alloc_keep` |
| an object graph built by code that calls plain `dr_alloc` (a context, a model) | `dr_persist_begin()` … `dr_persist_end()` |
| something a reference slot keeps | the slot setters (`av1_ref_set_saved_*`), which copy into the slot's own buffer |
| something the decoder keeps (a header) | a decoder-owned buffer (`av1_decoder_own_copy`) |
| a frame | `dr_frame_new`: the decoder's pool owns it, and the decoder roots it if it must survive the next frame start |

Three more things follow from this and are easy to break:

- **Read an OBU's header fields before any frame start.** `av1_obu_next` allocates the OBU record in the arena,
  so a frame start in the same loop iteration reclaims it. `av1_decoder_decode_in` copies `ext`, `tid` and `sid`
  into locals for that reason.
- **The returned frame is valid until the next call** on the same decoder. A frame no root holds is reused by a
  later frame.
- **A pooled frame is rooted only if `av1_decoder_frame_start` says so.** A new kind of frame the decoder keeps
  across frames (beyond the slots, the last decoded and last shown frames, the anchors and the grain output) needs
  a root there.

Outside a decoder call nothing changes: `dr_alloc` is the stdlib allocator, as it always was, and so are the
encoder lanes and the one-shot entry points (`av1_decode_frame`, `av1_decode_obus`).

**How a mistake shows up.** `make conformance` poisons the arena at every reset, filling it with 0xA5. It then
checks every output against its reference, including the memory-bound section, which feeds each committed
reproducer four times through one decoder. A pointer into reclaimed memory reads garbage, and an md5 fails. A
missed escape is a wrong picture, not a crash, so run `make conformance` after touching anything a decoder
allocates.
