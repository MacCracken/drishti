# Spec-literal reference ports

Python ports transcribed **directly from the AV1 spec text**, never from drishti's
Cyrius. They generate the known answers and digests the Cyrius suites assert against, so
the ground truth stays *independent* of the code under test — a self-consistent bug in
drishti cannot make a test pass, because the expected values did not come from drishti.

Run one to regenerate its numbers:

```sh
python3 scripts/refs/nbctx_ref.py
```

Each port's docstring quotes the exact spec pseudocode it transcribes, with the source
file and section, so it can be re-derived and re-checked against the spec independently.

| Port | Covers | Asserted by |
|------|--------|-------------|
| `warp_samples_ref.py` | `find_warp_samples` / `add_sample` (7.10.4) + `has_overlappable_candidates` | `tests/av1_mv.tcyr` (`test_find_warp_samples`, `test_has_overlappable_candidates`, `test_warp_nonsquare_and_clamp`) |
| `mv_ref.py` | the MV-prediction foundation: `setup_global_mv` (7.10.2.1), `lower_mv_precision` (7.10.2.10) and `Round2Signed`, spec-literal, plus libaom's `gm_get_motion_vector` / `lower_mv_precision` transcribed and ASSERTED equal to the spec on 64,579 legal inputs; it records the two places they differ, both inputs no legal header produces (`allow_high_precision_mv` with `force_integer_mv`, and an odd low-precision translation, which one test case is) | `tests/av1_mv.tcyr` (`test_setup_global_mv`, `test_lower_mv_precision`, `test_round2_signed`), `tests/av1_intermode.tcyr` (`test_inter_block_review_hardening`) |
| `find_mv_stack_ref.py` | the spatial MV candidate list (7.10.2 without the temporal scan): `scan_row` / `scan_col` / `scan_point`, `add_ref_mv_candidate`, the search stacks, sorting, extra search, context and clamping, `clamp_mv_row` / `_col`. Spec only, deliberately: libaom's and dav1d's forms do not follow the spec call for call (the composition is checked by the bit-exact corpus); the arithmetic cases are derived by hand | `tests/av1_mv.tcyr` (S1..S17, D1..D12) |
| `nbctx_ref.py` | neighbour CDF contexts — the 5.11.15 `inter_frame_mode_info` preamble + §9 `is_inter` / `comp_mode` ctx, `check_backward`, `count_refs`, `ref_count_ctx` | `tests/av1_intermode.tcyr` (`test_nbctx_known_answers`, `test_nbctx_full_enumeration`) |
| `motion_mode_ref.py` | `read_motion_mode` (5.11.27) branch decision + `is_scaled` | `tests/av1_intermode.tcyr` (`test_is_scaled`, `test_read_motion_mode_gate`, `test_motion_mode_driver_state`) |
| `ref_frames_ref.py` | `read_ref_frames` (5.11.25) dispatch + `seg_feature_active` (5.11.14) | `tests/av1_intermode.tcyr` (`test_seg_feature_active`, `test_read_ref_frames_dispatch`, `test_read_ref_frames_tree`) |
| `inter_block_ref.py` | `inter_block_mode_info` (5.11.23) symbol schedule — group order/presence, `get_mode`, `has_nearmv`, the DRL read counts | `tests/av1_intermode.tcyr` (`test_inter_block_single`, `test_inter_block_compound`, `test_inter_block_interintra`, `test_inter_block_seg_and_errors`) |
| `inter_frame_ref.py` | `inter_frame_mode_info` (5.11.15) outer dispatch — the `read_skip_mode` gate (5.11.11), the skip forcing, the `is_inter` selection, the outer schedules | `tests/av1_intermode.tcyr` (`test_skip_mode_leaf`, `test_is_inter_dispatch`, `test_inter_frame_mode_info`) |
| `bilinear_mc_ref.py` | BILINEAR motion compensation (7.11.3.4) + the whole unscaled single-ref translation MC path; written in the **spec** convention (16 phases, rows summing to 128) as a cross-convention check on drishti's halved dav1d one. Table machine-generated from the digest-pinned spec markdown; self-validates by reproducing all 17 pre-existing driver KATs first | `tests/av1_mc_driver.tcyr` (`test_mc_pred_bilinear`), `tests/av1_mc.tcyr` (`test_filter_set_selection`) |
| `mc_subpel_ref.py` | drishti's sub-pel filter table (7.11.3.4 `Subpel_Filters` in dav1d's form: halved, phase 0 dropped, sets permuted) derived from the spec table `bilinear_mc_ref` machine-generates — every tap asserted even, so the halving is exact — and its 90 position-weighted checksums; `--dav1d PATH` also checks it against dav1d's own `dav1d_mc_subpel_filters` (`src/tables.c`) entry for entry, parsed by designator | `tests/av1_mc.tcyr` (`test_subpel_checksum`) |
| `mc_put8tap_ref.py` | the `put_8tap` kernel, twice: the spec's two-pass convolve (7.11.3.4: 128-sum taps, both passes always, `InterRound0` / `InterRound1`) and dav1d's `put_8tap_c` branch for branch (copy / H / V / H+V, `intermediate_bits`, the H-only rounding constant, the `w <= 4` set) — ASSERTED equal on 6,108 blocks (every phase pair x filter pair at 8x8 and 4x4, plus a seeded sweep at 8 / 10 / 12 bit). Eight known answers, two pixels by hand; the two H-only rounding-boundary cases are shown to change under a wrong constant | `tests/av1_mc_kernel.tcyr` (`test_put_8tap`) |
| `emu_edge_ref.py` | the frame-boundary block fetch, twice: the spec's per-sample `ref[Clip3(0, lastY, y)][Clip3(0, lastX, x)]` and dav1d's `emu_edge_c` (copy the visible part, extend, replicate rows; extensions clipped to `bw - 1` / `bh - 1`) — ASSERTED equal on 186,624 fetches (every plane and block of 1..6 samples a side at every position from fully outside to fully outside); five known answers, one by hand | `tests/av1_mc_emu_edge.tcyr` |
| `upscale_filter_ref.py` | the superres `Upscale_Filter[64][8]` (7.16) — the spec's table, checked against the spec markdown — and its 64 position-weighted checksums; `--dav1d PATH` checks dav1d's `dav1d_resize_filter` is that table negated, entry for entry | `tests/av1_superres.tcyr` (`test_upscale_filter_position_checksum`) |
| `superres_upscale_ref.py` | superres upscaling (7.16), the spec's form (`superres_ref.py`) against dav1d's: `resize_c`'s split `src_x` / `mx` row loop, and `scale_fac` / `get_upscale_x0` — ASSERTED equal on every (downscaled, upscaled) width pair superres can produce up to 1024 and on 20,000 random rows; reproduces the row, geometry, chain, whole-frame and MI-clamp known answers (the last of which `superres_ref.py` printed but never asserted) | `tests/av1_superres.tcyr` (`test_superres_upscale_row`, `test_superres_geometry`, `test_superres_upscale_frame`, `test_superres_mi_clamp`) |
| `scaled_geom_ref.py` | the motion vector scaling process (7.11.3.3) — scale factors, `startX`/`startY`, `stepX`/`stepY`, `lastX`/`lastY`, `intermediateHeight` — cross-checked against libaom's different algebraic form of `startX` over 2688 combinations | `tests/av1_mc.tcyr` (`test_scaled_geometry`, `test_scaled_geometry_bounds`) |
| `scaled_mc_ref.py` | the scaled convolve (7.11.3.4 with a non-unit step) — imports the geometry from `scaled_geom_ref` and the table from `bilinear_mc_ref` so each is transcribed exactly once | `tests/av1_mc_driver.tcyr` (`test_mc_scaled_known_answers`) |
| `superres_ref.py` | the superres upscaling process (7.16) — geometry, the MI-grid tap clamp (`maxX = (MiCols >> subX) * MI_SIZE - 1`), the 8-tap `Upscale_Filter` (checked against the spec markdown when `build/spec-dl/` is present); its fixture puts unlike values in the overhang columns so a visible-width clamp shows | `tests/av1_superres.tcyr` (`test_superres_mi_clamp`) |
| `superres_width_ref.py` | the superres DOWNSCALED width: 5.9.8's formula floored at Min(16, UpscaledWidth) (Annex A: FrameWidth >= 16), transcribed separately from libaom's `calculate_scaled_size_helper` and dav1d's `src/obu.c`, ASSERTED equal on every UpscaledWidth 1..65536 at every denominator 9..16 and never to change a conforming width; the per-denominator count of floored widths is derived by hand for 9 and 16, and a 13-case table pins the unit test | `tests/av1_superres.tcyr` (`test_superres_width_table`, `test_superres_width_sweep`) |
| `symbol_exit_ref.py` | the symbol decoder's exit process (8.2.4) on top of a transcription of init_symbol (8.2.2), read_bool (8.2.3) and read_symbol (8.2.6): byte strings read through k read_bool calls, then the verdict (conforming / SymbolMaxBits < -14 / trailing bit 0 / a 1 in the padding) and trailingBitPosition. Every case is derived BY HAND in the port (one-byte and two-byte families whose reads take one bit each) and ASSERTED; my first, unasserted, labels for the multi-read cases were wrong | `tests/av1_symbol.tcyr` (`test_sym_exit_known`) |
| `qm_ref.py` | the quantizer matrices (7.12.3 step 1b; `Quantizer_Matrix` / `Qm_Offset`, 9.5.3): reads all 100,320 entries from the spec markdown (`build/spec-dl/`, required), proves the 9.5.2 derivation reproduces every one (the 32x32s are symmetric, each 16x32 is its 32x16 transposed), checks the table against libaom's `iwt_matrix_ref` — stored TRANSPOSED (`j * th + i`), so its rectangular regions differ at 48,538 entries read directly — and `--emit` generates `src/av1_qm.cyr`'s packed fill lines; plus the step-1 dequantisation on five fixtures | `tests/av1_qm.tcyr` (`test_qm_offset`, `test_qm_table`, `test_qm_select`, `test_qm_dequant`) |
| `grain_ref.py` | film grain synthesis (7.18.3: the LFSR, the generate-grain AR filter, the scaling lookup, the add-noise process with the spec's full `noiseStripe` / `noiseImage` arrays); `Gaussian_Sequence` read from the spec markdown (`--emit` generates `src/av1_grain.cyr`'s fill lines). `--crosscheck` validates the PORT against libaom: it applies the synthesis to `aomdec --skip-film-grain` output with the parameters vector-probe prints and compares with `aomdec`'s grained output — matched every frame of 22 streams (all 16 `--film-grain-test` sets, 8/10/12-bit, every format, show_existing, superres) | `tests/av1_grain.tcyr` (`test_grain_gauss`, `test_grain_rand`, `test_grain_fixtures`) |
| `intrabc_ref.py` | intra block copy's vector rules: `is_mv_valid` with `use_intrabc` (6.10.25: whole-sample, inside the tile, the 4-superblock delay and the wavefront `gradient`, the per-axis chroma pulls) and `assign_mv( 0 )`'s fallback predictor (5.11.26). Every boundary case carries its expectation and is ASSERTED, so a mislabelled case fails the port itself; a 4000-case LCG sweep gives a count and a digest. It also documents the one clause that is redundant for legal (superblock-aligned) tiles | `tests/av1_intrabc.tcyr` (`test_ibc_default_pred`, `test_ibc_dv_boundary`, `test_ibc_dv_sweep`) |
| `lst_ref.py` | large scale tile's syntax and placement: `tile_list_obu` / `tile_list_entry` (5.12.1 / 5.12.2) read bit by bit with `f(n)`, the 6.11.1 count limit and the 7.3.1 output-capacity limit, and the 7.3.1 raster placement (`destX` / `destY`, chroma shifted by subsampling). Every truncation and limit case and every placement is ASSERTED; the end-to-end decode's known answers come from libaom's own `lightfield_tile_list_decoder` in `make conformance`, not from a port | `tests/av1_lst.tcyr` (`test_lst_parse`, `test_lst_dest`) |
| `oppoint_ref.py` | operating point selection and `drop_obu` (5.3.1 / 5.5.1 / 6.4.1): the drop rule and `choose_operating_point`'s fall-back to point 0. 21 boundary cases and 6 choice cases, each ASSERTED; an exhaustive sweep (every 12-bit `operating_point_idc` x obu_type x extension flag x `temporal_id` x `spatial_id`, 4,194,304 OBUs) whose dropped count, 1,375,808, is derived by hand in the port (not taken from its output) and whose FNV-1a digest is pinned | `tests/av1_oppoint.tcyr` (`test_op_drop_cases`, `test_op_drop_sweep`, `test_op_choose`) |
| `warp_ls_bounds_ref.py` | the warp estimation's least-squares sums (7.11.3.8) are bounded by geometry: it enumerates every warp-eligible block size, neighbour size and aligned neighbour position the 7.10.4 scan visits (source offsets are multiples of 8, at most 1024), then every per-sample term over the `LS_MV_MAX` filter's range, and ASSERTS eight samples stay inside libaom's asserted `[LS_MAT_MIN, LS_MAT_MAX]` (no clamp exists anywhere: libaom's are debug asserts, the spec and dav1d bound nothing), that det is always a multiple of 16 (so `divShift >= 2`), and the solve's int64 headroom. Every extreme is derived by hand and asserted; canaries show the asserts fire. The empirical side is the instrumented, assert-enabled libaom in `ref/` (`AOMLS` print in `find_affine_int`, built without `NDEBUG`) over the corpus: 0 aborts, largest sum 709,332 | `tests/av1_mv.tcyr` (`test_warp_ls_bounds`) |

## Why these live in the repo

Earlier bites (0.7.52–0.7.65) generated ports named in `CHANGELOG.md` / `docs/sources.md` —
`mvscan_ref.py`, `mvdriver_ref.py`, `mv_ref.py`, `mc_driver_ref.py`, `emu_edge.py`,
`mc_put8tap.py`, `mc_subpel.py`, `resize_ref.py`, `upscale_geom.py`, `sr_ref.py` — under a
temporary scratch path that is wiped between sessions. **Those files are gone.** Committing
ports here fixes that going forward, and the lost ones are being restored:

- **Motion compensation — restored (0.8.5).** `mc_subpel_ref.py`, `mc_put8tap_ref.py` and
  `emu_edge_ref.py` replace `mc_subpel.py`, `mc_put8tap.py` and `emu_edge.py`, and
  `bilinear_mc_ref.py` already re-derives `mc_driver_ref.py`'s 17 driver known answers
  before it prints anything. The originals each transcribed dav1d alone; each replacement
  transcribes the SPEC and dav1d and asserts them equal, so the MC suites' known answers are
  now spec answers. The restoration found one gap the originals had left: dav1d's H-only
  rounding constant survived a mutation against all six kernel cases, and two boundary
  cases now pin it.
- **Motion-vector prediction and superres — restored (0.8.5).** `mv_ref.py` (the same
  name, a new port) and `find_mv_stack_ref.py` replace `mv_ref.py`, `mvscan_ref.py` and
  `mvdriver_ref.py`; `upscale_filter_ref.py` and `superres_upscale_ref.py` replace the
  checksum script, `resize_ref.py`, `upscale_geom.py` and `sr_ref.py`. The global-MV and
  superres ports assert libaom's or dav1d's form equal to the spec's; `find_mv_stack_ref.py`
  is spec-only (its docstring says why). This restoration found five Cyrius mutants that
  survived `tests/av1_mv.tcyr`: three parity terms of the far-row / far-column scans, whose
  fixtures put one MV over the cell a wrong probe would hit, and both branches of compound
  extra search's combine that no case took. New and corrected cases (S14, S15 with decoys;
  S17, D11, D12) now kill them.

No citation in `src/`, `tests/` or `docs/` points at a lost generator any more; the
CHANGELOG's history keeps the old names.

To be precise about what was and wasn't lost, because it matters: the ports are
transcriptions, not the authority. **The real oracle is the AV1 spec** — public,
versioned, and not reapable — and the suites' known answers remain re-derivable from it
without these files. (The 0.7.75 review demonstrated exactly this: a reviewer without
`nbctx_ref.py` re-derived all 11 of its digest constants from the spec pseudocode and
matched every one.) So a lost port is a retype, not an unverifiable claim.

What committing them buys is cheapness and explicitness: a port pins *which* pseudocode a
test's constants came from, makes regeneration a command instead of an exercise, and keeps
the derivation reviewable next to the code. That is worth a few kilobytes.
