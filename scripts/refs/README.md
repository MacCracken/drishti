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
| `nbctx_ref.py` | neighbour CDF contexts — the 5.11.15 `inter_frame_mode_info` preamble + §9 `is_inter` / `comp_mode` ctx, `check_backward`, `count_refs`, `ref_count_ctx` | `tests/av1_intermode.tcyr` (`test_nbctx_known_answers`, `test_nbctx_full_enumeration`) |
| `motion_mode_ref.py` | `read_motion_mode` (5.11.27) branch decision + `is_scaled` | `tests/av1_intermode.tcyr` (`test_is_scaled`, `test_read_motion_mode_gate`, `test_motion_mode_driver_state`) |
| `ref_frames_ref.py` | `read_ref_frames` (5.11.25) dispatch + `seg_feature_active` (5.11.14) | `tests/av1_intermode.tcyr` (`test_seg_feature_active`, `test_read_ref_frames_dispatch`, `test_read_ref_frames_tree`) |
| `inter_block_ref.py` | `inter_block_mode_info` (5.11.23) symbol schedule — group order/presence, `get_mode`, `has_nearmv`, the DRL read counts | `tests/av1_intermode.tcyr` (`test_inter_block_single`, `test_inter_block_compound`, `test_inter_block_interintra`, `test_inter_block_seg_and_errors`) |
| `inter_frame_ref.py` | `inter_frame_mode_info` (5.11.15) outer dispatch — the `read_skip_mode` gate (5.11.11), the skip forcing, the `is_inter` selection, the outer schedules | `tests/av1_intermode.tcyr` (`test_skip_mode_leaf`, `test_is_inter_dispatch`, `test_inter_frame_mode_info`) |
| `bilinear_mc_ref.py` | BILINEAR motion compensation (7.11.3.4) + the whole unscaled single-ref translation MC path; written in the **spec** convention (16 phases, rows summing to 128) as a cross-convention check on drishti's halved dav1d one. Table machine-generated from the digest-pinned spec markdown; self-validates by reproducing all 17 pre-existing driver KATs first | `tests/av1_mc_driver.tcyr` (`test_mc_pred_bilinear`), `tests/av1_mc.tcyr` (`test_filter_set_selection`) |
| `scaled_geom_ref.py` | the motion vector scaling process (7.11.3.3) — scale factors, `startX`/`startY`, `stepX`/`stepY`, `lastX`/`lastY`, `intermediateHeight` — cross-checked against libaom's different algebraic form of `startX` over 2688 combinations | `tests/av1_mc.tcyr` (`test_scaled_geometry`, `test_scaled_geometry_bounds`) |
| `scaled_mc_ref.py` | the scaled convolve (7.11.3.4 with a non-unit step) — imports the geometry from `scaled_geom_ref` and the table from `bilinear_mc_ref` so each is transcribed exactly once | `tests/av1_mc_driver.tcyr` (`test_mc_scaled_known_answers`) |
| `superres_ref.py` | the superres upscaling process (7.16) — geometry, the MI-grid tap clamp (`maxX = (MiCols >> subX) * MI_SIZE - 1`), the 8-tap `Upscale_Filter` (checked against the spec markdown when `build/spec-dl/` is present); its fixture puts unlike values in the overhang columns so a visible-width clamp shows | `tests/av1_superres.tcyr` (`test_superres_mi_clamp`) |
| `qm_ref.py` | the quantizer matrices (7.12.3 step 1b; `Quantizer_Matrix` / `Qm_Offset`, 9.5.3): reads all 100,320 entries from the spec markdown (`build/spec-dl/`, required), proves the 9.5.2 derivation reproduces every one (the 32x32s are symmetric, each 16x32 is its 32x16 transposed), checks the table against libaom's `iwt_matrix_ref` — stored TRANSPOSED (`j * th + i`), so its rectangular regions differ at 48,538 entries read directly — and `--emit` generates `src/av1_qm.cyr`'s packed fill lines; plus the step-1 dequantisation on five fixtures | `tests/av1_qm.tcyr` (`test_qm_offset`, `test_qm_table`, `test_qm_select`, `test_qm_dequant`) |
| `grain_ref.py` | film grain synthesis (7.18.3: the LFSR, the generate-grain AR filter, the scaling lookup, the add-noise process with the spec's full `noiseStripe` / `noiseImage` arrays); `Gaussian_Sequence` read from the spec markdown (`--emit` generates `src/av1_grain.cyr`'s fill lines). `--crosscheck` validates the PORT against libaom: it applies the synthesis to `aomdec --skip-film-grain` output with the parameters vector-probe prints and compares with `aomdec`'s grained output — matched every frame of 22 streams (all 16 `--film-grain-test` sets, 8/10/12-bit, every format, show_existing, superres) | `tests/av1_grain.tcyr` (`test_grain_gauss`, `test_grain_rand`, `test_grain_fixtures`) |

## Why these live in the repo

Earlier bites (0.7.52–0.7.65) generated ports named in `CHANGELOG.md` / `docs/sources.md` —
`mvscan_ref.py`, `mvdriver_ref.py`, `mv_ref.py`, `mc_driver_ref.py`, `emu_edge.py`,
`mc_put8tap.py`, `resize_ref.py`, `upscale_geom.py` — under a temporary scratch path that
is wiped between sessions. **Those files are gone, and the docs citing them point at
nothing.** Committing new ports here fixes that going forward; the dead citations are
flagged for the 0.7.x doc-claim audit on the roadmap.

To be precise about what was and wasn't lost, because it matters: the ports are
transcriptions, not the authority. **The real oracle is the AV1 spec** — public,
versioned, and not reapable — and the suites' known answers remain re-derivable from it
without these files. (The 0.7.75 review demonstrated exactly this: a reviewer without
`nbctx_ref.py` re-derived all 11 of its digest constants from the spec pseudocode and
matched every one.) So a lost port is a retype, not an unverifiable claim.

What committing them buys is cheapness and explicitness: a port pins *which* pseudocode a
test's constants came from, makes regeneration a command instead of an exercise, and keeps
the derivation reviewable next to the code. That is worth a few kilobytes.
