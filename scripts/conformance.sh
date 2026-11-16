#!/usr/bin/env bash
# drishti conformance gate (Phase E1) — decode AV1 streams drishti did NOT produce
# and compare the pixels against an INDEPENDENT decoder.
#
# WHY THIS EXISTS: every other gate in this repo round-trips drishti's own bitstream
# writer into drishti's own decoder, or compares against an oracle transcribed from
# the same spec reading as the implementation. Both sides then share any misreading,
# so the test passes while the pixels are wrong. This gate breaks that: libaom
# encodes the stream and libaom decodes the reference, so drishti has to match a
# bitstream and an output it had no hand in creating.
#
# A CASE THAT DID NOT RUN IS NOT A PASS (0.8.2). Every case below ends in exactly one of
# three states, and the summary counts all three:
#   matched / known-gap / REGRESSED   — it ran, fresh, and was scored;
#   skipped                           — it could not run here (no libaom, no network);
#   and a case that tried to run but could not be judged (a missing committed fixture, an
#   encoder or reference decoder that produced nothing, a reference with the wrong frame
#   count) is REGRESSED, because a gate that cannot judge has not passed.
# Nothing is ever scored from a previous run's artifacts: every stream, reference and
# output a case reads is deleted before that case produces it.
#
# EXIT CODES: 0 = every case ran and matched; 1 = a regression (or an unjudgeable case);
# 2 = no regression, but at least one case was SKIPPED. The committed tests/repro/*.ivf cases
# run anywhere; the generated + published corpus needs aomenc/aomdec/ffmpeg on PATH (and the
# network for the published vectors, once). On a machine without them, opt in to a partial
# run explicitly with CONFORMANCE_ALLOW_SKIP=1 (exit 0, still printed as INCOMPLETE).
# CONFORMANCE_STRICT=1 is accepted and is now the default behaviour.
#
# Usage: scripts/conformance.sh                       (generate corpus + run)
#        CONFORMANCE_KEEP=1 scripts/...               (keep the generated corpus for inspection)
#        CONFORMANCE_ALLOW_SKIP=1 scripts/...         (accept a partial run, e.g. no libaom)

set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
WORK="${CONFORMANCE_WORK:-build/conformance}"
FRAME_LIMIT=5
# The generated corpus geometry, derived ONCE. The per-frame raw I420 size used to be a
# magic 6144 in check(); it is CORPUS_FRAME now, so changing the corpus dims cannot leave
# the frame slicer silently reading the wrong offsets.
CORPUS_W=64; CORPUS_H=64
CORPUS_Y=$(( CORPUS_W * CORPUS_H ))
CORPUS_C=$(( (CORPUS_W / 2) * (CORPUS_H / 2) ))
CORPUS_FRAME=$(( CORPUS_Y + (2 * CORPUS_C) ))

# EVERY case that needs libaom, declared once. The skip path counts these lists, so a case
# added below cannot run on one machine and silently vanish from the count on another.
GEN_CASES="kf_only seq_filters seq_nofilt"
ODDMI_CASES="160x136:64 160x136:128 288x152:64 288x152:128"
# odd-MI INTER frames (0.8.3), oddmii_WxH_sbS_lagL_cC, 12 frames, every frame hard: MiRows % 4 == 2 and/or
# MiCols % 4 == 2 at both superblock sizes. 264x176 is the WIDTH axis alone (MiRows % 4 == 0).
ODDMII_CASES="oddmii_136x136_sb64_lag19_c6 oddmii_136x136_sb128_lag19_c6 oddmii_200x104_sb64_lag19_c6 \
oddmii_264x152_sb128_lag0_c4 oddmii_264x176_sb128_lag19_c6 oddmii_328x200_sb128_lag19_c8"
SB_CASES="64 128"
# kind_WxH_sbN: dqlf = delta_q + delta_lf, dqonly = delta_q alone (0.8.2).
DELTA_CASES="dqlf_352x288_sb64 dqlf_352x288_sb128 dqonly_352x288_sb64"
# mixed lossless / lossy segments, WxH_sbN (0.8.2).
LL_CASES="ll_352x288_sb64 ll_352x288_sb128 ll_160x136_sb64"
# segmentation on INTER frames, seg_aqA_cqQ_fF at 352x288 sb64 (0.8.2): variance / complexity AQ, whose
# later frames COPY the map and inherit the feature data (update_map 0, update_data 0).
SEGI_CASES="seg_aq1_cq1_f6 seg_aq2_cq20_f6"
# TEMPORAL segmentation, tseg_WxH_bKBPS_cCPU (0.8.2): realtime cyclic-refresh AQ, 9 frames, at least one
# with segmentation_temporal_update = 1 (the seg_id_predicted read against PrevSegmentIds).
TSEG_CASES="tseg_352x288_b150_c8 tseg_160x136_b400_c8 tseg_200x104_b150_c9"
# OTHER ENCODERS, judged against aomdec (+ the dav1d guard) like every other case (0.8.2). libaom's AQ never
# inherits a non-trivial segmentation: its copied maps carry no features. rav1e does — every inter frame
# inherits the keyframe's ALT_Q features through update_data 0 — so it is the external witness for
# load_previous. SVT-AV1's variance AQ re-codes its features on inter frames with a primary reference.
# QUANTIZER MATRICES (0.8.4; held as clean REJECTS 0.8.2 - 0.8.3), KIND_WxH, every frame hard. qm15 signals
# matrices at the flat level 15 (no matrix applies); qmon is libaom's default levels; qm0 the steepest level only;
# qmall levels 0..14 over a 128-SB GOP; qmll a mixed-lossless keyframe (the lossless segments drop to level 15);
# qmiq libaom --tune=iq, whose chroma levels differ from luma; qm444 the same at 4:4:4; qmb10 / qmb12 high bit
# depth; qmmono one plane; qmscr screen content (palette, identity / 1D transforms — which are flat); qmrt
# realtime; qmai all-intra; svtqm SVT-AV1 with a separate chroma level range. Each case's qm_property guard proves
# a matrix applied, plus the property the case exists for.
QM_CASES="qm15_176x144 qmon_176x144 qm0_176x144 qmall_352x288 qmll_352x288 qmiq_176x144 qm444_176x144 \
qmb10_176x144 qmb12_176x144 qmmono_176x144 qmscr_176x144 qmrt_176x144 qmai_176x144 svtqm_176x144"
# FILM GRAIN (0.8.4; before it, grain streams decoded GRAIN-FREE without a word — 0/10 on both published grain
# vectors), KIND_WxH, every frame hard against aomdec, whose default output applies the grain (dav1d's too). fgtN =
# libaom's --film-grain-test=N parameter set N (1..16: AR lags 0-3, chroma from luma, overlap, restricted-range
# clipping, scaling shifts), at the default lag so hidden frames come back through show_existing_frame with their
# saved grain — except 5 / 9 / 11, which re-use a reference's parameters (update_grain 0) and run at lag 0. fgb10 /
# fgb12 / fg444 / fg422 / fgmono the formats and depths; fgsr grain on superres output; fgrs on resized frames;
# fgsvt SVT-AV1 --film-grain; fgrav rav1e --photon-noise; fgid / fgbt clip_to_restricted_range on saturated 4:4:4
# testsrc2 chroma (up to 240) with matrix_coefficients MC_IDENTITY (chroma clips at luma's 235) and BT.709 (at 240).
# Each case's grain_property guard proves grain applied, plus the property the case exists for.
FG_CASES="fgt1_176x144 fgt2_176x144 fgt3_176x144 fgt4_176x144 fgt5_176x144 fgt6_176x144 fgt7_176x144 fgt8_176x144 \
fgt9_176x144 fgt10_176x144 fgt11_176x144 fgt12_176x144 fgt13_176x144 fgt14_176x144 fgt15_176x144 fgt16_176x144 \
fgb10_176x144 fgb12_176x144 fg444_176x144 fg422_176x144 fgmono_176x144 fgsr_352x288 fgrs_352x288 fgsvt_176x144 \
fgrav_176x144 fgid_176x144 fgbt_176x144"
# INTRA BLOCK COPY (0.8.4; REJECTED before), KIND_WxH, every frame hard: libaom screen-content keyframes
# (`--tune-content=screen --enable-intrabc=1`, testsrc2) at the presets that keep intrabc (cpu-used 0..2; it drops at
# 3). Counted with libaom's inspect when the cases were written, the intrabc MI cells per frame run from 8 (4:4:4) to
# over 1,200: ibc / ibc0 the base, ibcodd* odd sizes (the MI-grid read extent), ibc444 / ibc422 / ibcb10 / ibcb12 /
# ibcmono every format and depth, ibcll lossless, ibc128 128x128 superblocks (gradient 6), ibctile four tiles (the
# vector stays in its tile), ibcaq segmentation, ibcgop intrabc keyframes between inter frames. Each case's
# ibc_property guard proves allow_intrabc, plus the property the case exists for.
# LARGE SCALE TILE (0.8.4), lst_WxH_LFWxLFH_bsB: libaom's lightfield tools (built from the libaom checkout in ref/:
# make -C ref/aom-build lightfield_encoder lightfield_bitstream_parsing lightfield_tile_list_decoder) on a W x H light
# field of LFW x LFH mandelbrot views grouped in B x B blocks (one anchor each, >= 4: the tools refuse fewer), and four
# seeded random tile lists of 1..64 entries — out of order, repeated tile windows, every anchor. Scored per anchor and
# per tile list against lightfield_tile_list_decoder's YUV1D output. Skipped (counted) when the tools are not built.
LST_CASES="lst_256x256_4x4_2 lst_384x256_3x3_2 lst_320x192_6x6_2 lst_512x320_4x4_2 lst_448x192_3x2_1"
# SCALABILITY (0.8.4), svcLM[bD]_WxH: libaom's examples/svc_encoder_rtc in layering mode LM (1 = L1T2, 2 = L1T3,
# 5 = L2T1, 6 = L3T1, 7 = L2T3, 8 = L3T3), 12 frames of mandelbrot at bit depth D (default 8), decoded at EVERY
# operating point its sequence header lists (build/conformance-input.op) and judged in two packings:
#  - merged into temporal units by ffmpeg's av1_frame_merge (the payload bytes are checked unchanged): one frame per
#    unit, the highest spatial layer in the operating point — aomdec --oppoint, dav1d --oppoint --alllayers 0;
#  - as written, one IVF frame per layer packet: one frame per packet — dav1d --alllayers 1.
# Every output frame is hard against aomdec, paired by the unit it came from; a unit aomdec shows nothing for must
# show nothing in drishti. svc_property requires extension headers on every frame OBU, the layer counts the mode
# promises, and at every operating point but the first a present layer outside it (else nothing would drop).
SVC_CASES="svc1_320x240 svc2_320x240 svc5_320x240 svc6_320x240 svc7_320x240 svc8_320x240 svc7_350x198 \
svc5b10_320x240"
# The published SVC vectors' operating points past the first (whose frames PUBLISHED scores against libaom's md5s),
# name:last_operating_point, judged like a merged SVC_CASES stream. libaom codes their base layer with NO extension
# header, which 5.3.1 never drops — but no stream can witness that clause: an OBU without the header reads as
# temporal_id = spatial_id = 0, and every operating point holds the base layer, so the bit test keeps it too (a gate
# mutant dropping extension-less OBUs survives here; tests/av1_oppoint.tcyr's sweep kills it).
SVC_PUBLISHED_OPS="av1-1-b8-22-svc-L1T2:1 av1-1-b8-22-svc-L2T1-2:1 av1-1-b8-22-svc-L2T2-2:3"
# INVALID STREAMS (0.8.5): libaom's own fuzz / crash corpus, the 23 streams of test/invalid_file_test.cc
# (kAV1InvalidFileTests, libaom 3.15.3), each with the .res file that test reads (libaom's expected result per input
# unit; name:res-suffix where it is not ".res"). See invcase for what is checked.
INVALID_CASES="invalid-bug-1814 invalid-chromium-906381 invalid-google-142530197 invalid-google-142530197-1 \
invalid-oss-fuzz-9463:res.2 invalid-oss-fuzz-9720 invalid-oss-fuzz-10389:res.4 invalid-oss-fuzz-11523:res.2 \
invalid-oss-fuzz-15363 invalid-oss-fuzz-16437:res.2 invalid-oss-fuzz-24706 invalid-oss-fuzz-9288 invalid-oss-fuzz-9482 \
invalid-oss-fuzz-10061 invalid-oss-fuzz-10117-mc-buf-use-highbd invalid-oss-fuzz-10227 invalid-oss-fuzz-10555 \
invalid-oss-fuzz-10705 invalid-oss-fuzz-10723:res.2 invalid-oss-fuzz-10779 invalid-oss-fuzz-11477 \
invalid-oss-fuzz-11479:res.2 invalid-oss-fuzz-33030"
# Where libaom and dav1d DISAGREE and drishti sides with dav1d, dav1d is the reference: invalid-oss-fuzz-10779 ends in
# an OBU with obu_has_size_field = 0, which libaom refuses outright ("section 5 obu streams must have obu_size field
# set", AOM_CODEC_UNSUP_BITSTREAM) and dav1d, like drishti, reads as running to the end of the unit (5.3.1); the
# unit's frame is then decoded bit-exact by both.
INVALID_DAV1D_REF="invalid-oss-fuzz-10779"
# Units drishti shows differently from libaom AND dav1d, as name:unit, each with its verified cause. A listed unit
# that now matches fails the gate, so this list cannot go stale. Empty since 0.8.5 bite 4. Retired:
#  - invalid-oss-fuzz-10117-mc-buf-use-highbd:1 (bite 3): a 2-wide superres frame, now given the Min(16,
#    UpscaledWidth) floor libaom and dav1d use;
#  - invalid-oss-fuzz-10227:1 (bite 4): a tile ending in ~12.7 KB of non-zero "padding", now refused by the full 8.2.4
#    exit process (trailing bit + zero padding), as libaom (check_trailing_bits_after_symbol_coder) and dav1d refuse.
INVALID_XFAIL_UNITS=""
IBC_CASES="ibc_352x288 ibc0_352x288 ibcodd_349x197 ibcodd_173x101 ibc444_176x144 ibc422_352x288 ibcb10_352x288 \
ibcb12_352x288 ibcmono_352x288 ibcll_352x288 ibc128_352x288 ibctile_640x360 ibcaq_352x288 ibcgop_352x288"
# CROSS-FRAME CDF SAVE (0.8.2), name_WxH: multi-tile streams whose adapting frames save tile
# context_update_tile_id != 0 (libaom names its LARGEST tile), and frame-parallel streams that adapt inside the
# frame but save the INITIAL context (disable_frame_end_update_cdf 1). Every case also has a later frame
# inheriting those CDFs (primary_ref_frame != NONE) — the only place a wrong save shows.
CDF_CASES="mt2c_352x288 mt2x2_640x360 mt2csb128_640x360 mt4crt_640x360 fp_352x288 fp2c_352x288"
# PALETTE (0.8.2), kind_WxH: the STOCK case first — default aomenc settings on ordinary content, where libaom's
# screen-content detector turns allow_screen_content_tools on — then explicit screen tuning on synthetic content
# (chroma palettes, delta-coded V colours, palettes inside inter frames). intrabc stays off: it is roadmap 0.8.4.
PAL_CASES="palstock_640x360 palscreen_320x240 palbars_320x240"
RAV1E_CASES="rav1e_352x288_s6_q100"
SVT_CASES="svt_352x288_p8_crf35"
# SVT-AV1 OPEN GOP (0.8.3): `--irefresh-type 1` codes each GOP start as a hidden INTRA_ONLY frame (frame_type 2)
# shown later through show_existing_frame — the only intra-only frames in the gate. (It is not a show_existing KEY,
# the full 7.21 reload, which no encoder tried emits; that path stays unit-witnessed.)
SVTOPEN_CASES="svtopen_176x144"
# LONG GOPs (0.8.3), kind_WxH, every frame hard: real reference patterns, which need far more frames than the 9
# the harness could decode before it streamed. Each case PROVES its property through vector-probe first (see
# gop_property): the default and 2-pass GOPs show hidden frames, show_existing_frame and a refresh of every one of
# the eight slots; the others show what their flag exists for (repeated keyframes, error-resilient inter frames,
# SWITCH frames, no order hints, no motion-field MVs, the realtime pattern).
GOP_CASES="gopdef_176x144 goplag35_176x144 gop2pass_176x144 gopkf_176x144 goprt_176x144 goperr_176x144 \
gopsf_176x144 gopnoord_176x144 gopnomfmv_176x144 gopc0_176x144"
# SUPERRES (0.8.3), kind_WxH, every frame hard. Each stream must show superres frames whose downscaled width is
# NOT a multiple of 8 — the frames with overhang columns, which 7.16's MI-grid tap clamp reads (see sr_property).
SR_CASES="srfix_352x288 srrand_352x288 srsb128_352x288 srodd_175x99 srtiles_640x360 srrt_352x288 srlr_197x113 \
srresize_352x288"
# SUPERRES AT SMALL WIDTHS (0.8.5), srmin_WxH[_dD][_b10][_eq|_rand], every frame hard: libaom superres encodes whose
# downscaled width the Min(16, UpscaledWidth) floor decides (5.9.8 + Annex A, as libaom and dav1d compute it; see
# av1_superres_downscaled_width). Denominator D (default 16); _eq frames come out as wide as their upscaled width
# (UpscaledWidth <= 16), which libaom and dav1d then do NOT upscale (av1_fh_superres_scaled); _rand uses random
# denominators. Every case failed on the 0.8.5-bite-2 decoder (the bare formula; 24x24 matched only its keyframe,
# 16x16 refused its superres frames). srmin_property proves the floor bites (and, for _eq, equal widths).
SRMIN_CASES="srmin_24x24 srmin_30x40 srmin_17x9 srmin_20x18_d12 srmin_24x24_b10 srmin_16x16_eq srmin_12x12_eq \
srmin_8x16_d9_eq srmin_16x16_b10_eq srmin_28x28_rand"
# THE FULL PUBLISHED CORPUS (0.8.5): every AV1 vector libaom's test/test_vectors.cc lists (kAV1TestVectors,
# libaom 3.15.3) — 240 .ivf here plus the 2 .mkv in PUBLISHED_MKV. The quantizer and size families are generated
# from libaom's naming (quantizer 00..63 at 8 and 10 bits; sizes WxH over {16,18,32,34,64,66} and over
# {196,198,200,202,208,210,224,226}), checked equal to that list when 0.8.5 gated them; PUBLISHED_COUNT guards it.
PUBLISHED="$(for b in b8 b10; do for q in $(seq -w 0 63); do printf 'av1-1-%s-00-quantizer-%s ' "$b" "$q"; done; done
    for s in "16 18 32 34 64 66" "196 198 200 202 208 210 224 226"; do
        for w in $s; do for h in $s; do printf 'av1-1-b8-01-size-%sx%s ' "$w" "$h"; done; done
    done) \
av1-1-b8-02-allintra av1-1-b8-04-cdfupdate av1-1-b8-05-mv av1-1-b8-06-mfmv \
av1-1-b8-16-intra_only-intrabc-extreme-dv av1-1-b8-22-svc-L1T2 av1-1-b8-22-svc-L2T1-2 av1-1-b8-22-svc-L2T2-2 \
av1-1-b8-23-film_grain-50 av1-1-b10-23-film_grain-50 av1-1-b8-24-monochrome av1-1-b10-24-monochrome"
PUBLISHED_COUNT=240
# HIGH BIT DEPTH (0.8.3), kind_WxH, every frame hard. bNN = libaom at NN bits (4:2:0 / 4:4:4 / 4:2:2 / mono, superres +
# LR, random resize at cpu-used 2, cpu-used 0, screen content, 128-SB, realtime, LOSSLESS, near-lossless quality);
# r12* = rav1e, because libaom's aomenc cannot produce 12-bit 4:4:4 or 4:2:2. Each stream proves its bit depth and
# format through vector-probe, plus the property its tool needs (see bd_property).
BD_CASES="b10_176x144 b10444_176x144 b10422_176x144 b10mono_176x144 b10sr_352x288 b10rs_176x144 b10c0_176x144 \
b10scr_320x240 b10sb128_352x288 b10rt_176x144 b10ll_176x144 b10hiq_176x144 b12_176x144 b12mono_176x144 \
b12sr_352x288 b12c0_176x144 b12ll_176x144 r12444_176x144 r12422_176x144"
# CHROMA FORMATS (0.8.3), kind_WxH, every frame hard: monochrome, 4:4:4 (profile 1) and 4:2:2 (profile 2), over
# GOPs, realtime, screen content (chroma palettes), superres + loop restoration, 128-SB and an odd-MI geometry. Each
# stream PROVES its format through vector-probe (num_planes / subsampling), and the restoration cases prove a
# CHROMA plane was restored (lr_type_u/v), not just luma. 4:2:0 is covered by every other section.
FMT_CASES="fmtmono_176x144 fmt444_176x144 fmt422_176x144 fmtmonort_176x144 fmt444rt_176x144 fmt422rt_176x144 \
fmt444scr_320x240 fmt422scr_320x240 fmtmonosr_352x288 fmt444sr_352x288 fmt422sr_352x288 fmt444sb128_352x288 \
fmt422oddmi_136x136"
# THE DIMENSION SWEEP (0.8.3), every frame hard. dim_WxH_sbS: frame sizes from 1x1 up, none a multiple of 8 on both
# axes unless the point is the tiny size itself, at both superblock sizes, each proved by the probe to code exactly
# W x H. rs*: SCALED REFERENCES (--resize-mode), every fixed denominator class, both directions at the 2x limit,
# random sizes with 128-SB / tiles / lookahead / realtime / the slower preset whose edge OBMC blocks exposed the
# visible-plane overlap trim; each proved to change frame size.
DIM_CASES="dim_1x1_sb64 dim_2x2_sb64 dim_3x5_sb64 dim_1x64_sb64 dim_64x1_sb64 dim_8x8_sb64 dim_9x9_sb64 \
dim_33x17_sb64 dim_65x47_sb64 dim_127x129_sb64 dim_175x143_sb64 dim_257x31_sb64 dim_3x5_sb128 dim_129x127_sb128 \
dim_199x113_sb128 dim_31x257_sb128"
RS_CASES="rsfix9_197x113 rsfix12_197x113 rsfix16_197x113 rsup2x_176x144 rsdown2x_176x144 rsrand128_352x288 \
rsrandtiles_640x360 rsrandc2_176x144 rsrandlag_176x144 rsrandrt_176x144"
# libaom's published RESIZE vectors ship as .mkv; they are remuxed losslessly (ffmpeg -c copy) to IVF for the harness
# and scored on every frame like the IVF ones.
PUBLISHED_MKV="av1-1-b8-03-sizeup av1-1-b8-03-sizedown"

pass=0; fail=0; xfail=0; skip=0; skipped_names=""

skip_case() { # name reason
    skip=$((skip+1)); skipped_names="$skipped_names $1"
    echo "  $1: SKIPPED ($2)"
}
# Every libaom-dependent case, marked skipped with one reason. Used when the tools are absent.
skip_external() { # reason
    local c
    for c in $GEN_CASES; do skip_case "$c" "$1"; done
    for c in $ODDMI_CASES; do skip_case "oddmi_${c%%:*}_sb${c##*:}" "$1"; done
    for c in $ODDMII_CASES; do skip_case "$c" "$1"; done
    for c in $SB_CASES; do skip_case "sbrepro_sb$c" "$1"; done
    for c in $DELTA_CASES; do skip_case "$c" "$1"; done
    for c in $LL_CASES; do skip_case "$c" "$1"; done
    for c in $SEGI_CASES; do skip_case "$c" "$1"; done
    for c in $TSEG_CASES; do skip_case "$c" "$1"; done
    for c in $QM_CASES; do skip_case "$c" "$1"; done
    for c in $FG_CASES; do skip_case "$c" "$1"; done
    for c in $IBC_CASES; do skip_case "$c" "$1"; done
    for c in $LST_CASES; do skip_case "$c" "$1"; done
    for c in $SVC_CASES; do skip_case "$c" "$1"; done
    for c in $SVC_PUBLISHED_OPS; do skip_case "${c%%:*}-ops" "$1"; done
    for c in $INVALID_CASES; do skip_case "${c%%:*}" "$1"; done
    for c in $CDF_CASES; do skip_case "$c" "$1"; done
    for c in $PAL_CASES; do skip_case "$c" "$1"; done
    for c in $RAV1E_CASES; do skip_case "$c" "$1"; done
    for c in $SVT_CASES; do skip_case "$c" "$1"; done
    for c in $SVTOPEN_CASES; do skip_case "$c" "$1"; done
    for c in $GOP_CASES; do skip_case "$c" "$1"; done
    for c in $SR_CASES; do skip_case "$c" "$1"; done
    for c in $SRMIN_CASES; do skip_case "$c" "$1"; done
    for c in $FMT_CASES; do skip_case "$c" "$1"; done
    for c in $DIM_CASES; do skip_case "$c" "$1"; done
    for c in $RS_CASES; do skip_case "$c" "$1"; done
    for c in $PUBLISHED_MKV; do skip_case "$c" "$1"; done
    for c in $BD_CASES; do skip_case "$c" "$1"; done
    for c in $PUBLISHED; do skip_case "$c" "$1"; done
}
# The verdict. Exit 0 ONLY when every case ran and matched.
finish() {
    echo "=== matched=$pass  known-gap=$xfail  REGRESSED=$fail  skipped=$skip ==="
    [ "${CONFORMANCE_KEEP:-0}" = "1" ] || rm -f "$WORK"/*.f[0-9] "$WORK"/*.ref
    if [ "$fail" -gt 0 ]; then
        echo "conformance: FAIL — a case regressed or could not be judged"
        exit 1
    fi
    if [ "$skip" -gt 0 ]; then
        echo "conformance: INCOMPLETE — $skip case(s) did not run:$skipped_names"
        if [ "${CONFORMANCE_ALLOW_SKIP:-0}" = "1" ]; then
            echo "  accepted as a partial run (CONFORMANCE_ALLOW_SKIP=1)"
            exit 0
        fi
        echo "  a case that did not run is not a pass; set CONFORMANCE_ALLOW_SKIP=1 to accept a partial run"
        exit 2
    fi
    echo "conformance: OK — every case ran"
    exit 0
}
# Run drishti on one stream. The previous case's input AND outputs are deleted first, so a
# failed copy can never leave the last case's stream (or its frames) in place to be scored
# as this one. Returns 1 if the stream could not be put in place.
run_drishti() { # ivf log
    # the large-scale tile and operating point sidecars (build/conformance-input.lst / .op) are removed for every
    # ordinary run: a leftover one would switch the next stream into large-scale tile mode or another operating point
    rm -f build/conformance-input.ivf build/conformance-input.lst build/conformance-input.op build/conformance-out-*.yuv
    cp "$1" build/conformance-input.ivf 2>/dev/null || return 1
    ./build/drishti-conformance >"$2" 2>&1
    return 0
}
# a scalable stream decoded at operating point op (0.8.4): only that point's layers' OBUs are decoded
run_drishti_op() { # ivf op log
    rm -f build/conformance-input.ivf build/conformance-input.lst build/conformance-input.op build/conformance-out-*.yuv
    cp "$1" build/conformance-input.ivf 2>/dev/null || return 1
    printf '%d\n' "$2" > build/conformance-input.op || return 1
    ./build/drishti-conformance >"$3" 2>&1
    rm -f build/conformance-input.op
    return 0
}
# a large-scale tile file (0.8.4): its first N temporal units are the anchor frames (N in the .lst sidecar)
run_drishti_lst() { # ivf lst log
    rm -f build/conformance-input.ivf build/conformance-input.lst build/conformance-input.op build/conformance-out-*.yuv
    cp "$1" build/conformance-input.ivf 2>/dev/null || return 1
    cp "$2" build/conformance-input.lst 2>/dev/null || return 1
    ./build/drishti-conformance >"$3" 2>&1
    rm -f build/conformance-input.lst
    return 0
}

# ---- COMMITTED REPRODUCERS (no libaom needed) ----
# tests/repro/*.ivf are tiny libaom-encoded streams with their aomdec reference MD5
# committed alongside, so this half of the gate runs anywhere — including CI without
# libaom. BOTH are hard gates now: e2d-160x160 was always the passing control, and
# e2d-192x160 was the the CDEF-grid heap overflow xfail until av1_clear_cdef was bounded (src/av1_modeinfo.cyr).
# They differ only in width, and both are 128-superblock streams. A MISSING fixture FAILS:
# these files are committed, so their absence is a defect, not an environment.
repro_case() { # name expect(match|xfail)
    local n="$1" expect="$2"
    local ivf="tests/repro/$n.ivf" md5f="tests/repro/$n.md5"
    if [ ! -f "$ivf" ] || [ ! -f "$md5f" ]; then
        echo "  repro $n: FIXTURE MISSING ($ivf / $md5f)"; fail=$((fail+1)); return
    fi
    mkdir -p build
    run_drishti "$ivf" /dev/null || { echo "  repro $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    local got want
    got=$(md5sum build/conformance-out-1.yuv 2>/dev/null | cut -d' ' -f1)
    want=$(cat "$md5f")
    if [ -n "$got" ] && [ "$got" = "$want" ]; then
        echo "  repro $n: keyframe BIT-EXACT vs committed reference"; pass=$((pass+1))
    elif [ "$expect" = "xfail" ]; then
        echo "  repro $n: keyframe differs (known gap)"; xfail=$((xfail+1))
    else
        echo "  repro $n: keyframe REGRESSED"; fail=$((fail+1))
    fi
}

cyrius build programs/conformance.cyr build/drishti-conformance >/dev/null 2>&1 || {
    echo "conformance: harness build FAILED"; exit 1; }
# the header probe proves a delta case's stream really carries deltas before it is scored.
cyrius build programs/vector-probe.cyr build/drishti-vector-probe >/dev/null 2>&1 || {
    echo "conformance: vector-probe build FAILED"; exit 1; }
echo "=== drishti conformance ==="
# A committed MULTI-FRAME reproducer: 6 frames with their per-frame aomdec MD5s, one per
# line. Runs anywhere. hard_n = how many leading frames are HARD gates; the rest are xfail.
# NOTE frames 1-3 of this stream are PIXEL-IDENTICAL (skip-only inter copies of the
# keyframe), so matching them proves only that a zero-MV copy works. FRAME 4 is the one that
# carries distinct content -- it is the real "an inter frame decodes bit-exact" evidence, and
# the reason the hard bound is 4 rather than 2.
repro_seq() { # name hard_n total_n
    local n="$1" hard="$2" tot="$3"
    local ivf="tests/repro/$n.ivf" md5f="tests/repro/$n.md5"
    if [ ! -f "$ivf" ] || [ ! -f "$md5f" ]; then
        echo "  repro $n: FIXTURE MISSING ($ivf / $md5f)"; fail=$((fail+1)); return
    fi
    mkdir -p build
    run_drishti "$ivf" /dev/null || { echo "  repro $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    local line="  repro $n:"
    local k=1
    while [ "$k" -le "$tot" ]; do
        local got want
        got=$(md5sum "build/conformance-out-$k.yuv" 2>/dev/null | cut -d' ' -f1)
        want=$(sed -n "${k}p" "$md5f")
        if [ -n "$got" ] && [ "$got" = "$want" ]; then
            line="$line f$k=OK"; pass=$((pass+1))
        elif [ "$k" -gt "$hard" ]; then
            line="$line f$k=xfail"; xfail=$((xfail+1))
        else
            line="$line f$k=REGRESSED"; fail=$((fail+1))
        fi
        k=$((k+1))
    done
    echo "$line"
}
echo "--- committed reproducers (no libaom required) ---"
repro_case e2d-160x160 match
repro_case e2d-192x160 match   # the CDEF-grid heap overflow: was xfail until av1_clear_cdef was bounded
repro_seq  inter-6frame 6 6   # ALL SIX frames bit-exact vs aomdec (hard)
# SEG_LVL_SKIP + SEG_LVL_ALT_LF (0.8.2): libaom's REALTIME ROI map (AOME_SET_ROI_MAP, speed 8, skip[1] = 1 on
# a middle square) enables SEG_LVL_SKIP plus all four ALT_LF features (data -63) on segment 1 of every inter
# frame. No aomenc flag reaches that encoder path — it is API-only — so these were made once with a scratch
# libaom program and committed with their aomdec MD5s (dav1d agreed on every frame). Geometries 96x64,
# 176x144 and 160x136 (MiRows % 4 == 2), 8 frames each, every frame hard.
repro_seq  roi-skip-96x64 8 8
repro_seq  roi-skip-176x144 8 8
repro_seq  roi-skip-160x136 8 8
# ODD-MI INTER FRAMES (0.8.3): libaom streams whose MI extent is not a multiple of 16 luma samples on ONE axis
# (160x136: MiRows % 4 == 2; 136x96: MiCols % 4 == 2). Their bottom / right-edge inter blocks overhang the MI grid,
# and drishti trimmed their MC to the MI-grid allocation, so 4 chroma rows (or columns) selected the 4-tap filter
# where the nominal block height selects the 8-tap one: 1-LSB chroma differences on frames 3-8 / 4-8. Fixed by
# allocating the decode frame to the SUPERBLOCK grid. libaom 3.15.3 `--cpu-used=8 --end-usage=q --cq-level=40
# (36 for 136x96) --lag-in-frames=0 --enable-palette=0` on a noisy mandelbrot, 8 frames each, every frame hard; dav1d
# agrees with aomdec on every frame.
repro_seq  oddmi-inter-160x136 8 8
repro_seq  oddmi-inter-136x96 8 8
# CHROMA FORMATS (0.8.3): monochrome, 4:4:4 (profile 1) and 4:2:2 (profile 2), so a machine without libaom still
# decodes every format. 72x56 (MiCols and MiRows % 4 == 2), 8 frames each with inter frames and loop restoration
# enabled; libaom 3.15.3 `--cpu-used=6 --end-usage=q --cq-level=40 --lag-in-frames=0`. Their md5s are the
# aomdec --rawvideo layout, which for monochrome is the Y plane alone. dav1d agrees with aomdec on every frame.
# COMPOUND_IDX CONTEXT (0.8.3): libaom 3.15.3 `--cpu-used=0 --lag-in-frames=19 --end-usage=q --cq-level=40`,
# 96x64, 10 frames. Its compound blocks with equidistant references read compound_idx from context row 3+; drishti
# threaded that order-hint term in as a constant 0, read row 0, and desynced at frame 6 (AV1_ERR_BAD_FRAME, the
# SymbolMaxBits exit bound) — the same defect as the published av1-1-b8-05-mv. dav1d agrees with aomdec.
repro_seq  jnt-ctx-96x64 10 10
# OBMC AT THE FRAME EDGE (0.8.3): libaom 3.15.3 `--cpu-used=2 --resize-mode=2 --end-usage=q --cq-level=40`, 96x80,
# 12 frames at six random sizes (51x43 .. 96x80). av1_obmc_overlap trimmed a neighbour's overlap to the VISIBLE
# plane, so an edge OBMC block's overlap cut to <= 4 chroma rows/columns took the 4-tap filter (and the band past
# the picture went unblended); frames 5-12 differed. dav1d agrees with aomdec.
repro_seq  obmc-edge-96x80 12 12
repro_seq  fmt-mono-72x56 8 8
repro_seq  fmt-444-72x56 8 8
repro_seq  fmt-422-72x56 8 8
# HIGH BIT DEPTH (0.8.3): 10-bit 4:2:0 and 12-bit monochrome from libaom 3.15.3 (`--cpu-used=6 --end-usage=q
# --cq-level=40 --lag-in-frames=0`, profile 2 for 12-bit), and 12-bit 4:4:4 from rav1e (`--speed 6 --quantizer 120`:
# libaom's aomenc refuses 12-bit 4:4:4 / 4:2:2). 72x56, 8 frames each; md5s over the aomdec --rawvideo layout, two
# bytes per sample. dav1d agrees with aomdec on every frame.
repro_seq  fmt-b10-420-72x56 8 8
repro_seq  fmt-b12-mono-72x56 8 8
repro_seq  fmt-b12-444-72x56 8 8
# QUANTIZER MATRICES (0.8.4), libaom 3.15.3, 8-bit 4:2:0 (mandelbrot + noise=alls=6:allf=t). qm-iq-128x96 is
# `--cpu-used=6 --tune=iq`, 8 frames at qm levels 9 / 10 with chroma one level above luma on four of them.
# qm-ll-96x64 is `--cpu-used=8 --end-usage=q --cq-level=0 --aq-mode=1 --deltaq-mode=0 --enable-qm=1 --qm-min=0
# --qm-max=4` (lag 0; restoration, palette, intrabc off), 3 frames: a keyframe with lossless AND lossy segments
# (LosslessArray 15) at qm level 0, so its lossless blocks must stay flat (SegQMLevel 15). dav1d agrees with
# aomdec on every frame; both REJECTED on the 0.8.3 decoder.
repro_seq  qm-iq-128x96 8 8
repro_seq  qm-ll-96x64 3 3
# FILM GRAIN (0.8.4), libaom 3.15.3, mandelbrot + noise=alls=6:allf=t, md5s over aomdec's DEFAULT (grained) output.
# fg-reload-96x64: `--cpu-used=6 --film-grain-test=5 --lag-in-frames=0`, 4 frames, three of them update_grain 0 (a
# reference's parameters, this frame's seed). fg-lag-96x64: `--cpu-used=6 --film-grain-test=10`, 10 frames, three
# shown through show_existing_frame with their saved grain. fg-b10-422-72x40: profile 2, 10-bit 4:2:2,
# `--film-grain-test=9 --lag-in-frames=0`, 3 frames. dav1d agrees with aomdec on every frame; the 0.8.4-bite-1 decoder
# (no grain synthesis) matched none of the grained frames.
repro_seq  fg-reload-96x64 4 4
repro_seq  fg-lag-96x64 10 10
repro_seq  fg-b10-422-72x40 3 3
# INTRA BLOCK COPY (0.8.4), libaom 3.15.3 `--tune-content=screen --enable-intrabc=1 --kf-max-dist=0` on testsrc2,
# 2 keyframes each; intrabc MI cells per frame counted with libaom's inspect: ibc-352x288 (`--cpu-used=2`) 1,286 / 320;
# ibc-sb128-352x288 (`--cpu-used=1 --sb-size=128`) 224 / 238; ibc-odd-349x197 (`--cpu-used=1`) 254 / 202;
# ibc-b10-352x288 (10-bit, `--cpu-used=1`) 352 / 280. dav1d agrees with aomdec on every frame; all four were REJECTED
# (allow_intrabc) by the 0.8.4-bite-2 decoder.
repro_seq  ibc-352x288 2 2
repro_seq  ibc-sb128-352x288 2 2
repro_seq  ibc-odd-349x197 2 2
repro_seq  ibc-b10-352x288 2 2
# SUPERRES AT SMALL WIDTHS (0.8.5), libaom 3.15.3 `--superres-mode=1 --superres-denominator=16
# --superres-kf-denominator=16 --lag-in-frames=0`, 8 frames of mandelbrot; md5s from aomdec, dav1d agreeing. In
# srmin-24x24 the bare 5.9.8 formula gives FrameWidth 12, libaom / dav1d / drishti 16 (the Min(16, UpscaledWidth)
# floor); in srmin-16x16 the floor makes FrameWidth = UpscaledWidth = 16, so nothing is upscaled. On the
# 0.8.5-bite-2 decoder the first matched only its keyframe and the second refused its superres frames. dav1d 1.5.4
# decodes nothing of srmin-16x16 ("Cannot allocate memory"), so its md5s are aomdec's alone.
repro_seq  srmin-24x24 8 8
repro_seq  srmin-16x16 8 8
# LARGE SCALE TILE (0.8.4): libaom's lightfield pipeline (examples/lightfield_encoder -> lightfield_bitstream_parsing,
# 8-bit 4:2:0, 64x64 tiles) on mandelbrot views: N anchor temporal units, the camera frame header, then tile list
# OBUs. Each .md5 line is one temporal unit: an anchor (libaom's own anchor output), "-" for the camera header (no
# output), or a tile list in libaom's YUV1D layout (lightfield_tile_list_decoder format 0: the decoded tiles only).
# lst-256x256: 4 anchors, 3 lists of 6 / 7 / 54 tiles; lst-384x256: 4 anchors, 4 lists. Both refused (tile list
# OBUs were skipped, the header-only camera OBU_FRAME failed) by the 0.8.4-bite-3 decoder.
repro_lst() { # name
    local n="$1" ivf="tests/repro/$1.ivf" lst="tests/repro/$1.lst" md5f="tests/repro/$1.md5"
    if [ ! -f "$ivf" ] || [ ! -f "$lst" ] || [ ! -f "$md5f" ]; then
        echo "  repro $n: FIXTURE MISSING ($ivf / $lst / $md5f)"; fail=$((fail+1)); return
    fi
    run_drishti_lst "$ivf" "$lst" /dev/null || { echo "  repro $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    local line="  repro $n:" k=1 want got
    while read -r want; do
        if [ "$want" = "-" ]; then
            if [ -e "build/conformance-out-$k.yuv" ]; then line="$line u$k=REGRESSED(output)"; fail=$((fail+1))
            else line="$line u$k=camera"; fi
        else
            got=$(md5sum "build/conformance-out-$k.yuv" 2>/dev/null | cut -d' ' -f1)
            if [ -n "$got" ] && [ "$got" = "$want" ]; then line="$line u$k=OK"; pass=$((pass+1))
            else line="$line u$k=REGRESSED"; fail=$((fail+1)); fi
        fi
        k=$((k+1))
    done < "$md5f"
    echo "$line"
}
repro_lst lst-256x256
repro_lst lst-384x256
# SCALABILITY reproducers (0.8.4), libaom 3.15.3 examples/svc_encoder_rtc, layering mode 7 (2 spatial x 3 temporal
# layers, six operating points: 0x307 0x303 0x301 0x107 0x103 0x101), 8 frames of mandelbrot, decoded at EVERY
# operating point. The .md5 holds "op unit md5" for each frame aomdec --oppoint op outputs (dav1d --oppoint agreed on
# all of them), unit being the IVF frame it came from; a unit with no line must show nothing (its OBUs all dropped).
# svc-l2t3-128x96 is merged into temporal units (ffmpeg av1_frame_merge, byte for byte): one frame per unit, the
# highest spatial layer in the operating point. svc-l2t3-layers-96x64 is as written, one IVF frame per layer packet:
# one frame per packet. Before 0.8.4 bite 5 drishti had no operating point: it decoded every layer at every one.
repro_svc() { # name
    local n="$1" ivf="tests/repro/$1.ivf" md5f="tests/repro/$1.md5"
    if [ ! -f "$ivf" ] || [ ! -f "$md5f" ]; then
        echo "  repro $n: FIXTURE MISSING ($ivf / $md5f)"; fail=$((fail+1)); return
    fi
    local line="  repro $n:" op ops nu k want got
    mkdir -p "$WORK"
    ops=$(awk '{print $1}' "$md5f" | sort -nu)
    for op in $ops; do
        run_drishti_op "$ivf" "$op" "$WORK/repro-$n-op$op.log" || {
            echo "  repro $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
        nu=$(grep -c '^frame [0-9]' "$WORK/repro-$n-op$op.log")
        line="$line op$op:"
        k=1
        while [ "$k" -le "$nu" ]; do
            want=$(awk -v op="$op" -v u="$k" '$1 == op && $2 == u { print $3 }' "$md5f")
            got=$(md5sum "build/conformance-out-$k.yuv" 2>/dev/null | cut -d' ' -f1)
            if [ -z "$want" ]; then
                if [ -n "$got" ]; then line="$line u$k=REGRESSED(output)"; fail=$((fail+1)); fi
            elif [ -n "$got" ] && [ "$got" = "$want" ]; then line="$line u$k=OK"; pass=$((pass+1))
            else line="$line u$k=REGRESSED"; fail=$((fail+1)); fi
            k=$((k+1))
        done
        if [ "$nu" -lt "$(awk -v op="$op" '$1 == op { if ($2 > m) m = $2 } END { print m + 0 }' "$md5f")" ]; then
            line="$line REGRESSED(only $nu units)"; fail=$((fail+1))
        fi
    done
    echo "$line"
}
repro_svc svc-l2t3-128x96
repro_svc svc-l2t3-layers-96x64

if ! command -v aomenc >/dev/null 2>&1 || ! command -v aomdec >/dev/null 2>&1; then
    echo "--- generated + published corpus ---"
    skip_external "libaom aomenc/aomdec not on PATH"
    finish
fi

mkdir -p "$WORK"

# A continuous-tone source: libaom's screen-content detector flags synthetic test
# patterns and turns on palette/intrabc, which drishti rejects by design. It is cached, so it
# is written to a temporary name and moved into place only when complete: an interrupted
# ffmpeg must not leave a short source behind for every later run to encode from.
SRC_BYTES=$(( FRAME_LIMIT * CORPUS_FRAME ))
if [ "$(stat -c %s "$WORK/src.yuv" 2>/dev/null || echo 0)" -ne "$SRC_BYTES" ]; then
    # This bail must mirror the aomenc/aomdec one above: the committed reproducers already
    # ran and are HARD cases, so their result is kept, and every libaom case is counted as
    # skipped rather than vanishing. It fires on any ffmpeg failure, not just a missing
    # binary — no lavfi mandelbrot source, full disk, and so on.
    rm -f "$WORK/src.yuv" "$WORK/src.yuv.part"
    if ffmpeg -loglevel error -y -f lavfi -i "mandelbrot=size=${CORPUS_W}x${CORPUS_H}:rate=30" \
        -frames:v $FRAME_LIMIT -pix_fmt yuv420p -f rawvideo "$WORK/src.yuv.part" 2>/dev/null; then
        mv -f "$WORK/src.yuv.part" "$WORK/src.yuv"
    else
        rm -f "$WORK/src.yuv.part"
        echo "--- generated + published corpus ---"
        skip_external "ffmpeg could not generate the source"
        finish
    fi
fi

# This generated corpus pins --sb-size=64 deliberately: it is the 64-superblock control
# path, kept green independently of the 128 path that the 128x128-superblock gate un-gated in 0.7.126. The 128
# coverage comes from the published vectors below (all of which use 128 by default).
# The previous run's stream is deleted FIRST: without that, a failed encode left the last
# run's .ivf in place and check() scored it as if this run had produced it.
enc() { # name kf_only extra...
    local name="$1"; shift
    local kfonly="$1"; shift
    local kf=""
    [ "$kfonly" = "1" ] && kf="--kf-max-dist=1 --limit=1"
    [ "$kfonly" = "1" ] || kf="--lag-in-frames=0 --limit=$FRAME_LIMIT"
    rm -f "$WORK/$name.ivf"
    aomenc --codec=av1 -w $CORPUS_W -h $CORPUS_H --i420 --sb-size=64 --cpu-used=8 --end-usage=q \
        --cq-level=40 --aq-mode=0 --deltaq-mode=0 --enable-restoration=0 \
        --tune-content=default --enable-palette=0 --enable-intrabc=0 $kf "$@" \
        --ivf -o "$WORK/$name.ivf" "$WORK/src.yuv" 2>/dev/null
}

# EVERY frame of every corpus entry is a HARD gate as of 0.7.129 — keyframes and inter
# frames alike. The two defects this comment used to describe as permanent xfails (a
# "reconstruction rounding" drift of max |delta| 2..4, and an entropy desync tripping
# SymbolMaxBits) are both FIXED; neither was what its name suggested. The drift was
# warpEstimation's least-squares constants plus per-leaf LoopfilterTxSizes; the desync was
# the temporal-MV scan never running plus CDF counters surviving a frame boundary.
# PER-FRAME DIVERGENCE DETAIL. A differing md5 says only "not equal", which is why the inter
# gap has been carried as a guessed "max |delta| 2..4, ~7% of samples" that no gate could
# reproduce. These numbers say HOW a frame differs: which plane, how many samples, and by how
# much. That distinction is the whole diagnosis — a scattered 1-2 LSB spread across all planes
# is a ROUNDING bug, a large count with a big max is a DESYNC, and a clean Y with dirty chroma
# is a chroma-path bug (which is exactly how the CfL edge-chroma bug was caught).
frame_delta() { # got ref -> "Y=count/max U=count/max V=count/max"
    cmp -l "$1" "$2" 2>/dev/null | awk -v y="$CORPUS_Y" -v c="$CORPUS_C" '
    { o = $1; a = strtonum("0" $2); b = strtonum("0" $3); d = (a > b ? a - b : b - a)
      if (o <= y)         { yn++; if (d > ym) ym = d }
      else if (o <= y + c) { un++; if (d > um) um = d }
      else                { vn++; if (d > vm) vm = d } }
    END { printf "Y=%d/%d U=%d/%d V=%d/%d", yn+0, ym+0, un+0, um+0, vn+0, vm+0 }'
}
# The frames to score come from the REFERENCE decode, never from drishti's own demux count:
# the old loop iterated drishti's "demuxed N" line, so a drishti that read 0 frames (or
# stopped early) scored nothing for those frames and failed nothing. The reference must also
# hold exactly the frames the encode asked for, so a short cached source cannot shrink a case.
gen_seen=""
check() { # name expect(all|keyframe) frames_expected
    local name="$1" expect="$2" want_n="$3"
    gen_seen="$gen_seen $name"
    if [ ! -s "$WORK/$name.ivf" ]; then
        echo "  $name: SETUP FAILED (aomenc produced no stream)"; fail=$((fail+1)); return
    fi
    run_drishti "$WORK/$name.ivf" "$WORK/$name.log" || {
        echo "  $name: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    rm -f "$WORK/$name.ref"
    aomdec --rawvideo -o "$WORK/$name.ref" "$WORK/$name.ivf" 2>/dev/null
    local refsz; refsz=$(stat -c %s "$WORK/$name.ref" 2>/dev/null || echo 0)
    if [ "$refsz" -eq 0 ]; then
        echo "  $name: SETUP FAILED (aomdec produced no reference)"; fail=$((fail+1)); return
    fi
    local n=$(( refsz / CORPUS_FRAME ))
    if [ $(( refsz % CORPUS_FRAME )) -ne 0 ] || [ "$n" -ne "$want_n" ]; then
        echo "  $name: SETUP FAILED (reference holds $refsz bytes, not $want_n frame(s) of $CORPUS_FRAME)"
        fail=$((fail+1)); return
    fi
    local line="  $name:"
    local k=1
    while [ "$k" -le "$n" ]; do
        local off=$(( (k-1) * CORPUS_FRAME ))
        dd if="$WORK/$name.ref" bs=1 skip=$off count=$CORPUS_FRAME of="$WORK/$name.f$k" status=none 2>/dev/null
        local a b st
        a=$(md5sum "build/conformance-out-$k.yuv" 2>/dev/null | cut -d' ' -f1)
        b=$(md5sum "$WORK/$name.f$k" 2>/dev/null | cut -d' ' -f1)
        if [ -z "$a" ]; then st="reject"; else
            if [ "$a" = "$b" ]; then st="OK"; else
                st="differs $(frame_delta "build/conformance-out-$k.yuv" "$WORK/$name.f$k")"
            fi
        fi
        if [ "$st" = "OK" ]; then
            line="$line f$k=OK"; pass=$((pass+1))
        elif [ "$expect" = "keyframe" ] && [ "$k" -gt 1 ]; then
            line="$line f$k=xfail($st)"; xfail=$((xfail+1))
        else
            line="$line f$k=REGRESSED($st)"; fail=$((fail+1))
        fi
        k=$((k+1))
    done
    echo "$line"
}

echo "--- generated corpus (libaom-encoded, libaom reference pixels) ---"
enc kf_only     1
enc seq_filters 0
enc seq_nofilt  0 --enable-cdef=0 --loopfilter-control=0

# KEYFRAME decode is bit-exact and is a HARD gate.
check kf_only all 1
# HARD on every frame, filters included. Reaching this took the temporal-MV scan gate, the
# deblocker's ref/mode deltas, the CDF counter reset, warpEstimation's LS constants and
# per-leaf LoopfilterTxSizes -- see the 0.7.129 CHANGELOG.
check seq_filters all $FRAME_LIMIT
# HARD on every frame: with the loop filters off, all five frames are bit-exact. This is the
# inter-decode path with no filtering in the way, so it pins MC, the warp model, the residual
# and the entropy decode together.
check seq_nofilt  all $FRAME_LIMIT
# GEN_CASES is what the skip path counts; the calls above are what runs. They must agree, or
# a generated case could run here and be missing from the skip count elsewhere.
[ "$gen_seen" = " $GEN_CASES" ] || {
    echo "  harness: GEN_CASES ($GEN_CASES) is out of step with the check calls ($gen_seen)"
    fail=$((fail+1)); }

# ---- PUBLISHED conformance vectors (libaom's own corpus + its own reference MD5s) ----
# These are the real thing: streams drishti never touched, with checksums published by
# the reference implementation. They ALL use 128x128 superblocks (libaom's default), so
# every one of them rejected outright until the 128x128-superblock gate landed. Their .md5
# companion holds ONE LINE PER FRAME, and since 0.8.3 (the streaming harness) EVERY frame is
# scored, not just the keyframe. Since 0.8.5 the list is libaom's whole AV1 corpus, and drishti must output
# exactly as many frames as the .md5 lists: an extra frame past the last md5 line is a regression too.
VDIR="${CONFORMANCE_VECTORS:-build/vectors}"
AOM_BASE="${CONFORMANCE_AOM_BASE:-https://storage.googleapis.com/aom-test-data}"
# Frames that are KNOWN GAPS, as name:frame. A named cause on a gap is a HYPOTHESIS until it
# is fixed: quantizer-00 and mfmv were once filed here as "coded_lossless" and "loop
# restoration", and both turned out to be the CDEF-grid heap overflow (av1_clear_cdef).
# (av1-1-b8-05-mv frames 3-4 were listed here from 0.8.3 bite 1 until bite 5 fixed them: the
# compound_idx context's order-hint term, threaded in as a constant 0 — see tests/repro/jnt-ctx-*.)
# A listed frame that now MATCHES fails the gate, so this list cannot go stale.
PUBLISHED_XFAIL_FRAMES=""

mkdir -p "$VDIR"
# Downloads land under a .part name and are moved into place only when complete, so an
# interrupted transfer cannot leave a truncated vector in the cache for every later run.
fetch_vec() { # name -> 0 if available
    [ -s "$VDIR/$1.ivf" ] && [ -s "$VDIR/$1.ivf.md5" ] && return 0
    rm -f "$VDIR/$1.ivf" "$VDIR/$1.ivf.md5" "$VDIR/$1.ivf.part" "$VDIR/$1.ivf.md5.part"
    curl -sf --max-time 120 -o "$VDIR/$1.ivf.part" "$AOM_BASE/$1.ivf" || {
        rm -f "$VDIR/$1.ivf.part"; return 1; }
    curl -sf --max-time 60 -o "$VDIR/$1.ivf.md5.part" "$AOM_BASE/$1.ivf.md5" || {
        rm -f "$VDIR/$1.ivf.part" "$VDIR/$1.ivf.md5.part"; return 1; }
    mv -f "$VDIR/$1.ivf.part" "$VDIR/$1.ivf" && mv -f "$VDIR/$1.ivf.md5.part" "$VDIR/$1.ivf.md5"
}
# An .mkv-only published vector, put in the cache as the IVF + md5 pair check_published reads: the .mkv and its
# .mkv.md5 are fetched (via .part names, as fetch_vec), the stream is remuxed LOSSLESSLY (ffmpeg -c copy: the
# temporal units are carried byte for byte) and the md5 file is reused as is (one md5 per frame).
fetch_mkv() { # name -> 0 if "$VDIR/name.ivf" and its md5 are available
    [ -s "$VDIR/$1.ivf" ] && [ -s "$VDIR/$1.ivf.md5" ] && return 0
    rm -f "${VDIR:?}/$1.mkv.part" "${VDIR:?}/$1.mkv.md5.part" "${VDIR:?}/$1.ivf.part"
    curl -sf --max-time 120 -o "$VDIR/$1.mkv.part" "$AOM_BASE/$1.mkv" || { rm -f "${VDIR:?}/$1.mkv.part"; return 1; }
    curl -sf --max-time 60 -o "$VDIR/$1.mkv.md5.part" "$AOM_BASE/$1.mkv.md5" || {
        rm -f "${VDIR:?}/$1.mkv.part" "${VDIR:?}/$1.mkv.md5.part"; return 1; }
    ffmpeg -loglevel error -y -i "$VDIR/$1.mkv.part" -c copy -f ivf "$VDIR/$1.ivf.part" 2>/dev/null || {
        rm -f "${VDIR:?}/$1.mkv.part" "${VDIR:?}/$1.mkv.md5.part" "${VDIR:?}/$1.ivf.part"; return 1; }
    mv -f "$VDIR/$1.mkv.md5.part" "$VDIR/$1.ivf.md5" && mv -f "$VDIR/$1.ivf.part" "$VDIR/$1.ivf"
    rm -f "${VDIR:?}/$1.mkv.part"
}
# The md5 of frame k in the PUBLISHED convention. libaom's .md5 files checksum an I420 image even for a
# MONOCHROME stream: the Y plane followed by two 4:2:0 chroma planes of the neutral value 1 << (BitDepth - 1)
# (verified: av1-1-b8-24-monochrome matches on all 10 frames that way, and on none as Y alone). The harness writes
# the aomdec --rawvideo layout (Y alone), so the neutral planes are appended here, from the frame's dims and depth
# in the harness log ("frame k decoded WxH planes=P bitdepth=B").
published_md5() { # k log
    local k="$1" log="$2" geo np bd
    geo=$(sed -n "s/^frame $k decoded \([0-9]*x[0-9]*\) planes=\([0-9]*\) bitdepth=\([0-9]*\).*/\1 \2 \3/p" "$log")
    [ -f "build/conformance-out-$k.yuv" ] || return 0
    read -r geo np bd <<< "$geo"
    if [ "${np:-3}" != "1" ]; then md5sum "build/conformance-out-$k.yuv" | cut -d' ' -f1; return 0; fi
    local w="${geo%x*}" h="${geo#*x}"
    local n=$(( 2 * ((w + 1) / 2) * ((h + 1) / 2) )) mid=$(( 1 << (bd - 1) ))
    { cat "build/conformance-out-$k.yuv"
      LC_ALL=C awk -v n="$n" -v lo=$(( mid & 255 )) -v hi=$(( mid >> 8 )) -v two=$(( bd > 8 )) \
          'BEGIN { for (i = 0; i < n; i++) { if (two) printf "%c%c", lo, hi; else printf "%c", lo } }'
    } | md5sum | cut -d' ' -f1
}
check_published() { # name
    local name="$1"
    if ! fetch_vec "$name"; then skip_case "$name" "vector fetch failed"; return; fi
    local nref; nref=$(grep -cE '^[0-9a-f]{32}' "$VDIR/$name.ivf.md5" || true)
    if [ "$nref" -lt 1 ]; then
        echo "  $name: SETUP FAILED (published md5 file holds no md5)"; fail=$((fail+1)); return
    fi
    run_drishti "$VDIR/$name.ivf" "$WORK/$name.log" || {
        echo "  $name: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    local line="  $name:" k=1
    while [ "$k" -le "$nref" ]; do
        local ref got gap=0
        ref=$(grep -E '^[0-9a-f]{32}' "$VDIR/$name.ivf.md5" | sed -n "${k}p" | cut -d' ' -f1)
        got=$(published_md5 "$k" "$WORK/$name.log")
        case " $PUBLISHED_XFAIL_FRAMES " in *" $name:$k "*) gap=1 ;; esac
        if [ -n "$got" ] && [ "$got" = "$ref" ]; then
            if [ "$gap" = "1" ]; then
                line="$line f$k=MATCHES(remove-from-PUBLISHED_XFAIL_FRAMES)"; fail=$((fail+1))
            else
                line="$line f$k=OK"; pass=$((pass+1))
            fi
        elif [ "$gap" = "1" ]; then
            line="$line f$k=known-gap"; xfail=$((xfail+1))
        else
            line="$line f$k=REGRESSED"; fail=$((fail+1))
        fi
        k=$((k+1))
    done
    local ndec; ndec=$(grep -c '^frame [0-9]* decoded' "$WORK/$name.log")
    if [ "$ndec" -ne "$nref" ]; then
        line="$line REGRESSED(drishti output $ndec frames, the md5 file lists $nref)"; fail=$((fail+1))
    fi
    echo "$line"
}

# ---- THE 128-SB REPRODUCER (the CDEF-grid heap overflow — FIXED, kept as the regression guard) ----
# Same source, same encoder settings, ONLY --sb-size differs. BOTH must match now; 128 was
# the the CDEF-grid heap overflow xfail until av1_clear_cdef was bounded (src/av1_modeinfo.cyr). It stays a hard
# case because it was the minimal local trigger: it needs partial superblock coverage in
# BOTH dimensions (352x288 with 128-SBs leaves a 96-col x 32-row remainder), and it was
# CONTENT-dependent — the published 352x288 vectors cdfupdate/quantizer-32 have the same
# geometry and decoded fine even while the bug was live, because the out-of-bounds -1 only
# sometimes landed on a CDF word that frame actually read.
# Setup failures FAIL, as in oddmi(): libaom and ffmpeg are known present by this point, so a
# stream or reference that does not appear is a broken run, not a missing environment. Both
# used to `return 0` silently, and the old stream was never deleted, so a failed encode scored
# the previous run's file.
sbrepro() { # sbsize expect(match|xfail)
    local sb="$1" expect="$2" n="sbrepro_sb$1"
    rm -f "$WORK/r.yuv" "$WORK/sb$sb.ivf" "$WORK/sb$sb.ref"
    ffmpeg -loglevel error -y -f lavfi -i "mandelbrot=size=352x288:rate=30" -frames:v 1 \
        -pix_fmt yuv420p -f rawvideo "$WORK/r.yuv" 2>/dev/null || {
        echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
    aomenc --codec=av1 -w 352 -h 288 --i420 --cpu-used=8 --end-usage=q --cq-level=40 \
        --sb-size="$sb" --aq-mode=0 --deltaq-mode=0 --enable-restoration=0 \
        --tune-content=default --enable-palette=0 --enable-intrabc=0 --kf-max-dist=1 \
        --limit=1 --ivf -o "$WORK/sb$sb.ivf" "$WORK/r.yuv" 2>/dev/null
    [ -s "$WORK/sb$sb.ivf" ] || { echo "  $n: SETUP FAILED (aomenc produced no stream)"
        fail=$((fail+1)); return; }
    run_drishti "$WORK/sb$sb.ivf" "$WORK/sb$sb.log" || {
        echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    aomdec --rawvideo -o "$WORK/sb$sb.ref" "$WORK/sb$sb.ivf" 2>/dev/null
    [ -s "$WORK/sb$sb.ref" ] || { echo "  $n: SETUP FAILED (aomdec produced no reference)"
        fail=$((fail+1)); return; }
    local a b
    a=$(md5sum build/conformance-out-1.yuv 2>/dev/null | cut -d' ' -f1)
    b=$(md5sum "$WORK/sb$sb.ref" 2>/dev/null | cut -d' ' -f1)
    if [ -n "$a" ] && [ "$a" = "$b" ]; then
        echo "  352x288 sb-size=$sb: keyframe BIT-EXACT"; pass=$((pass+1))
    elif [ "$expect" = "xfail" ]; then
        echo "  352x288 sb-size=$sb: keyframe differs (known gap)"; xfail=$((xfail+1))
    else
        echo "  352x288 sb-size=$sb: keyframe REGRESSED"; fail=$((fail+1))
    fi
}
# ---- ODD-MI GEOMETRY (the CfL edge-chroma bug — the CfL bottom-edge overhang) ----
# EVERY published vector's height is a multiple of 16 and enc()'s source is 64x64, so until
# this case existed the whole gate was blind to a frame whose bottom block OVERHANGS: a
# 4:2:0 keyframe with MiRows % 4 == 2 (luma height/8 odd) drove predict_chroma_from_luma to
# read the last VISIBLE luma row in place of the reconstructed overhang, shifting lumaAvg
# and every sample of the CfL block. Chroma-only, max |delta| 2, and invisible to an
# aligned corpus. 160x136 and 288x152 both reproduce; both superblock sizes are covered
# because the defect is independent of the CDEF-grid heap overflow. Keep at least one MiRows % 4 == 2 case here.
oddmi() { # w h sbsize
    local w="$1" h="$2" sb="$3" n="oddmi_${1}x${2}_sb${3}"
    rm -f "$WORK/$n.ivf" "$WORK/$n.ref"
    ffmpeg -loglevel error -y -f lavfi -i "mandelbrot=size=${w}x${h}:rate=30" -frames:v 1 \
        -pix_fmt yuv420p -f rawvideo "$WORK/$n.yuv" 2>/dev/null || {
        echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
    aomenc --codec=av1 -w "$w" -h "$h" --i420 --sb-size="$sb" --cpu-used=8 --end-usage=q \
        --cq-level=40 --aq-mode=0 --deltaq-mode=0 --enable-restoration=0 \
        --tune-content=default --enable-palette=0 --enable-intrabc=0 --kf-max-dist=1 \
        --limit=1 --ivf -o "$WORK/$n.ivf" "$WORK/$n.yuv" 2>/dev/null
    [ -s "$WORK/$n.ivf" ] || { echo "  $n: SETUP FAILED (aomenc produced no stream)"
        fail=$((fail+1)); return; }
    run_drishti "$WORK/$n.ivf" "$WORK/$n.log" || {
        echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    aomdec --rawvideo -o "$WORK/$n.ref" "$WORK/$n.ivf" 2>/dev/null
    [ -s "$WORK/$n.ref" ] || { echo "  $n: SETUP FAILED (aomdec produced no reference)"
        fail=$((fail+1)); return; }
    local a b
    a=$(md5sum build/conformance-out-1.yuv 2>/dev/null | cut -d' ' -f1)
    b=$(md5sum "$WORK/$n.ref" 2>/dev/null | cut -d' ' -f1)
    if [ -n "$a" ] && [ "$a" = "$b" ]; then
        echo "  ${w}x${h} sb-size=$sb (MiRows%4==2): keyframe BIT-EXACT"; pass=$((pass+1))
    else
        echo "  ${w}x${h} sb-size=$sb (MiRows%4==2): keyframe REGRESSED"; fail=$((fail+1))
    fi
}
echo "--- odd-MI geometry (the CfL edge-chroma bug — CfL bottom-edge overhang) ---"
for c in $ODDMI_CASES; do d="${c%%:*}"; oddmi "${d%%x*}" "${d##*x}" "${c##*:}"; done

echo "--- 128-SB reproducer (same source, only --sb-size differs) ---"
for sb in $SB_CASES; do sbrepro "$sb" match; done   # 128 is the CDEF-grid heap overflow: was xfail until av1_clear_cdef was bounded

# ---- PER-SUPERBLOCK DELTAS (0.8.2): delta_q / delta_lf decode bit-exact, keyframes AND inter frames ----
# libaom emits deltas only from its delta-q modes, and --deltaq-mode=2 needs lookahead (deltaq-mode=1 rides
# on the TPL model and emitted none at all for these sources), hence --lag-in-frames=19 here, unlike the
# generated corpus. libaom always writes delta_lf_multi = 0, so multi = 1 is witnessed only by the unit
# tests. A case is only meaningful if its stream REALLY carries deltas, so each one first PROVES
# delta_q_present (and delta_lf_present for dqlf) through vector-probe — a libaom that stopped emitting
# them would otherwise turn these into ordinary inter streams passing for the wrong reason.
DELTA_FRAMES=5
deltacase() { # name = kind_WxH_sbN
    local n="$1" kind dims sbx
    IFS=_ read -r kind dims sbx <<< "$n"
    local w="${dims%%x*}" h="${dims##*x}" sb="${sbx#sb}"
    local flags="--deltaq-mode=2"
    [ "$kind" = "dqlf" ] && flags="$flags --delta-lf-mode=1"
    rm -f "${WORK:?}/$n.ivf" "${WORK:?}/$n.ref" "${WORK:?}/$n.yuv"
    ffmpeg -loglevel error -y -f lavfi -i "mandelbrot=size=${w}x${h}:rate=30" -frames:v $DELTA_FRAMES \
        -pix_fmt yuv420p -f rawvideo "$WORK/$n.yuv" 2>/dev/null || {
        echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
    aomenc --codec=av1 -w "$w" -h "$h" --i420 --sb-size="$sb" --cpu-used=8 --end-usage=q --cq-level=40 \
        --aq-mode=0 --enable-restoration=0 --tune-content=default --enable-palette=0 --enable-intrabc=0 \
        --limit=$DELTA_FRAMES --lag-in-frames=19 $flags --ivf -o "$WORK/$n.ivf" "$WORK/$n.yuv" 2>/dev/null
    [ -s "$WORK/$n.ivf" ] || { echo "  $n: SETUP FAILED (aomenc produced no stream)"; fail=$((fail+1)); return; }
    rm -f build/conformance-input.ivf
    cp "$WORK/$n.ivf" build/conformance-input.ivf || { echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    local probe; probe=$(./build/drishti-vector-probe 2>&1)
    if ! echo "$probe" | grep -q 'delta_q_present=1'; then
        echo "  $n: SETUP FAILED (the stream carries no delta_q — the case would prove nothing)"
        fail=$((fail+1)); return
    fi
    if [ "$kind" = "dqlf" ] && ! echo "$probe" | grep -q 'delta_lf_present=1'; then
        echo "  $n: SETUP FAILED (the stream carries no delta_lf — the case would prove nothing)"
        fail=$((fail+1)); return
    fi
    run_drishti "$WORK/$n.ivf" "$WORK/$n.log" || { echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    aomdec --rawvideo -o "$WORK/$n.ref" "$WORK/$n.ivf" 2>/dev/null
    local fs=$(( (w * h) + (2 * ((w + 1) / 2) * ((h + 1) / 2)) ))
    local refsz; refsz=$(stat -c %s "$WORK/$n.ref" 2>/dev/null || echo 0)
    if [ "$refsz" -ne $(( fs * DELTA_FRAMES )) ]; then
        echo "  $n: SETUP FAILED (reference holds $refsz bytes, not $DELTA_FRAMES frames of $fs)"
        fail=$((fail+1)); return
    fi
    local line="  $n:" k=1
    while [ "$k" -le "$DELTA_FRAMES" ]; do
        local a b
        a=$(md5sum "build/conformance-out-$k.yuv" 2>/dev/null | cut -d' ' -f1)
        b=$(dd if="$WORK/$n.ref" bs="$fs" skip=$((k-1)) count=1 status=none | md5sum | cut -d' ' -f1)
        if [ -n "$a" ] && [ "$a" = "$b" ]; then line="$line f$k=OK"; pass=$((pass+1))
        else line="$line f$k=REGRESSED"; fail=$((fail+1)); fi
        k=$((k+1))
    done
    echo "$line"
}
echo "--- per-superblock deltas (delta_q / delta_lf; every frame hard) ---"
for c in $DELTA_CASES; do deltacase "$c"; done

# ---- MIXED LOSSLESS SEGMENTS (0.8.2): Lossless = LosslessArray[ segment_id ] per block ----
# libaom's variance AQ at cq-level 0 writes base_q_idx 0 with per-segment ALT_Q, so its keyframe has SOME
# segments lossless and the rest lossy (LosslessArray 7 / 15). drishti used to reject that config outright,
# and would otherwise have decoded every block lossless (the old base_q == 0 shortcut). Each case first
# PROVES its keyframe really is mixed (segmentation on, 0 < mask < 255) through vector-probe. And because
# libaom 3.15.3's encoder writes streams at neighbouring settings (--aq-mode=2) that dav1d AND libaom 3.14
# both reject while its own aomdec accepts, a reference dav1d disagrees with is refused as unjudgeable
# (when dav1d is installed): aomdec alone vouching for a stream is not enough here.
LL_FRAMES=3
llcase() { # name = ll_WxH_sbN
    local n="$1" dims sbx
    IFS=_ read -r _ dims sbx <<< "$n"
    local w="${dims%%x*}" h="${dims##*x}" sb="${sbx#sb}"
    rm -f "${WORK:?}/$n.ivf" "${WORK:?}/$n.ref" "${WORK:?}/$n.yuv" "${WORK:?}/$n.dav1d.yuv"
    ffmpeg -loglevel error -y -f lavfi -i "mandelbrot=size=${w}x${h}:rate=30" -frames:v $LL_FRAMES \
        -pix_fmt yuv420p -f rawvideo "$WORK/$n.yuv" 2>/dev/null || {
        echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
    aomenc --codec=av1 -w "$w" -h "$h" --i420 --sb-size="$sb" --cpu-used=8 --end-usage=q --cq-level=0 \
        --aq-mode=1 --deltaq-mode=0 --enable-restoration=0 --tune-content=default --enable-palette=0 \
        --enable-intrabc=0 --limit=$LL_FRAMES --lag-in-frames=0 --ivf -o "$WORK/$n.ivf" "$WORK/$n.yuv" 2>/dev/null
    [ -s "$WORK/$n.ivf" ] || { echo "  $n: SETUP FAILED (aomenc produced no stream)"; fail=$((fail+1)); return; }
    rm -f build/conformance-input.ivf
    cp "$WORK/$n.ivf" build/conformance-input.ivf || { echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    local probe; probe=$(./build/drishti-vector-probe 2>&1)
    local kmask; kmask=$(echo "$probe" | grep -m1 'lossless_mask=' | tr -dc '0-9')
    if ! echo "$probe" | grep -m1 'segmentation_enabled=' | grep -q '=1' || [ -z "$kmask" ] \
       || [ "$kmask" -le 0 ] || [ "$kmask" -ge 255 ]; then
        echo "  $n: SETUP FAILED (the keyframe is not mixed lossless, mask=${kmask:-none} — the case would prove nothing)"
        fail=$((fail+1)); return
    fi
    run_drishti "$WORK/$n.ivf" "$WORK/$n.log" || { echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    aomdec --rawvideo -o "$WORK/$n.ref" "$WORK/$n.ivf" 2>/dev/null
    if command -v dav1d >/dev/null 2>&1; then
        dav1d -q -i "$WORK/$n.ivf" -o "$WORK/$n.dav1d.yuv" >/dev/null 2>&1
        if ! cmp -s "$WORK/$n.ref" "$WORK/$n.dav1d.yuv"; then
            echo "  $n: SETUP FAILED (dav1d disagrees with aomdec — the reference cannot be trusted)"
            fail=$((fail+1)); return
        fi
    fi
    local fs=$(( (w * h) + (2 * ((w + 1) / 2) * ((h + 1) / 2)) ))
    local refsz; refsz=$(stat -c %s "$WORK/$n.ref" 2>/dev/null || echo 0)
    if [ "$refsz" -ne $(( fs * LL_FRAMES )) ]; then
        echo "  $n: SETUP FAILED (reference holds $refsz bytes, not $LL_FRAMES frames of $fs)"
        fail=$((fail+1)); return
    fi
    local line="  $n (mask $kmask):" k=1
    while [ "$k" -le "$LL_FRAMES" ]; do
        local a b
        a=$(md5sum "build/conformance-out-$k.yuv" 2>/dev/null | cut -d' ' -f1)
        b=$(dd if="$WORK/$n.ref" bs="$fs" skip=$((k-1)) count=1 status=none | md5sum | cut -d' ' -f1)
        if [ -n "$a" ] && [ "$a" = "$b" ]; then line="$line f$k=OK"; pass=$((pass+1))
        else line="$line f$k=REGRESSED"; fail=$((fail+1)); fi
        k=$((k+1))
    done
    echo "$line"
}
echo "--- mixed lossless segments (LosslessArray[ segment_id ]; every frame hard) ---"
for c in $LL_CASES; do llcase "$c"; done

# ---- SEGMENTATION ON INTER FRAMES (0.8.2) — libaom variance AQ (1/2) and cyclic refresh (3) ----
# The generated corpus encodes --aq-mode=0, so until 0.8.2 no external stream had ever exercised
# segmentation on an inter frame. The first one (seg_aq1_cq1_f3) diverged on frame 3 — not in
# segmentation at all, but in the tx_depth context of an INTRA block inside an inter frame, which used
# the keyframe form and ignored an inter neighbour (av1_tx_depth_ctx_inter). Frames 4+ of the variance-AQ
# runs COPY the map from a reference (update_map 0) and inherit its feature data (update_data 0), and the
# realtime cyclic-refresh runs code seg_id_predicted (temporal_update 1); all three rejected until the
# temporal-segmentation bite (load_previous + PrevSegmentIds + 7.20 SavedSegmentIds). Each case proves its
# stream carries the property it exists for, and refuses a reference dav1d disagrees with.
seg_judge() { # n w h fr — decode, reference, dav1d guard, per-frame compare (every frame hard)
    local n="$1" w="$2" h="$3" fr="$4"
    run_drishti "$WORK/$n.ivf" "$WORK/$n.log" || { echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    aomdec --rawvideo -o "$WORK/$n.ref" "$WORK/$n.ivf" 2>/dev/null
    if command -v dav1d >/dev/null 2>&1; then
        dav1d -q -i "$WORK/$n.ivf" -o "$WORK/$n.dav1d.yuv" >/dev/null 2>&1
        if ! cmp -s "$WORK/$n.ref" "$WORK/$n.dav1d.yuv"; then
            echo "  $n: SETUP FAILED (dav1d disagrees with aomdec — the reference cannot be trusted)"
            fail=$((fail+1)); return
        fi
    fi
    local fs=$(( (w * h) + (2 * ((w + 1) / 2) * ((h + 1) / 2)) ))
    local refsz; refsz=$(stat -c %s "$WORK/$n.ref" 2>/dev/null || echo 0)
    if [ "$refsz" -ne $(( fs * fr )) ]; then
        echo "  $n: SETUP FAILED (reference holds $refsz bytes, not $fr frames of $fs)"; fail=$((fail+1)); return
    fi
    local line="  $n:" k=1
    while [ "$k" -le "$fr" ]; do
        local a b
        a=$(md5sum "build/conformance-out-$k.yuv" 2>/dev/null | cut -d' ' -f1)
        b=$(dd if="$WORK/$n.ref" bs="$fs" skip=$((k-1)) count=1 status=none | md5sum | cut -d' ' -f1)
        if [ -n "$a" ] && [ "$a" = "$b" ]; then line="$line f$k=OK"; pass=$((pass+1))
        else line="$line f$k=REGRESSED"; fail=$((fail+1)); fi
        k=$((k+1))
    done
    echo "$line"
}
# the per-frame segmentation flags the probe prints, reduced to: does SOME inter frame (frame_type != 0) with
# segmentation_enabled = 1 match `want` — "seg" (any), "copy" (update_map 0 AND update_data 0), "temporal"
# (temporal_update 1) or "inherit" (update_data 0 with a NON-EMPTY inherited feature set: the probe tracks the
# ref state, so segmentation_active_mask is what load_previous brought in)? The probe prints the flags in that
# order after each frame_type line.
seg_property() { # want
    ./build/drishti-vector-probe 2>&1 | awk -v want="$1" '
        /frame_type=/ { inter = ($0 !~ /frame_type=0/); en = 0; um0 = 0; ud0 = 0 }
        /segmentation_enabled=1/ { en = 1; if (inter && want == "seg") f = 1 }
        /segmentation_update_map=0/ { um0 = 1 }
        /segmentation_temporal_update=1/ { if (inter && en && want == "temporal") f = 1 }
        /segmentation_update_data=0/ { ud0 = 1; if (inter && en && um0 && want == "copy") f = 1 }
        /segmentation_active_mask=/ { if (inter && en && ud0 && $0 !~ /=0$/ && want == "inherit") f = 1 }
        END { exit !f }'
}
segicase() { # name = seg_aqA_cqQ_fF
    local n="$1" aqx cqx frx
    IFS=_ read -r _ aqx cqx frx <<< "$n"
    local aq="${aqx#aq}" cq="${cqx#cq}" fr="${frx#f}" w=352 h=288
    rm -f "${WORK:?}/$n.ivf" "${WORK:?}/$n.ref" "${WORK:?}/$n.yuv" "${WORK:?}/$n.dav1d.yuv"
    ffmpeg -loglevel error -y -f lavfi -i "mandelbrot=size=${w}x${h}:rate=30" -frames:v "$fr" \
        -pix_fmt yuv420p -f rawvideo "$WORK/$n.yuv" 2>/dev/null || {
        echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
    aomenc --codec=av1 -w $w -h $h --i420 --sb-size=64 --cpu-used=8 --end-usage=q --cq-level="$cq" \
        --aq-mode="$aq" --deltaq-mode=0 --enable-restoration=0 --tune-content=default --enable-palette=0 \
        --enable-intrabc=0 --limit="$fr" --lag-in-frames=0 --ivf -o "$WORK/$n.ivf" "$WORK/$n.yuv" 2>/dev/null
    [ -s "$WORK/$n.ivf" ] || { echo "  $n: SETUP FAILED (aomenc produced no stream)"; fail=$((fail+1)); return; }
    rm -f build/conformance-input.ivf
    cp "$WORK/$n.ivf" build/conformance-input.ivf || { echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    if ! seg_property seg; then
        echo "  $n: SETUP FAILED (no inter frame carries segmentation — the case would prove nothing)"
        fail=$((fail+1)); return
    fi
    if ! seg_property copy; then
        echo "  $n: SETUP FAILED (no inter frame copies the map + feature data — the case would prove nothing)"
        fail=$((fail+1)); return
    fi
    seg_judge "$n" "$w" "$h" "$fr"
}
tsegcase() { # name = tseg_WxH_bKBPS_cCPU (9 frames)
    local n="$1" geo bx cx
    IFS=_ read -r _ geo bx cx <<< "$n"
    local w="${geo%x*}" h="${geo#*x}" br="${bx#b}" cpu="${cx#c}" fr=9
    rm -f "${WORK:?}/$n.ivf" "${WORK:?}/$n.ref" "${WORK:?}/$n.yuv" "${WORK:?}/$n.dav1d.yuv"
    ffmpeg -loglevel error -y -f lavfi -i "mandelbrot=size=${w}x${h}:rate=30" -frames:v "$fr" \
        -pix_fmt yuv420p -f rawvideo "$WORK/$n.yuv" 2>/dev/null || {
        echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
    aomenc --codec=av1 -w $w -h $h --i420 --sb-size=64 --rt --cpu-used="$cpu" --aq-mode=3 --end-usage=cbr \
        --target-bitrate="$br" --deltaq-mode=0 --enable-restoration=0 --tune-content=default --enable-palette=0 \
        --enable-intrabc=0 --limit="$fr" --lag-in-frames=0 --ivf -o "$WORK/$n.ivf" "$WORK/$n.yuv" 2>/dev/null
    [ -s "$WORK/$n.ivf" ] || { echo "  $n: SETUP FAILED (aomenc produced no stream)"; fail=$((fail+1)); return; }
    rm -f build/conformance-input.ivf
    cp "$WORK/$n.ivf" build/conformance-input.ivf || { echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    if ! seg_property temporal; then
        echo "  $n: SETUP FAILED (no inter frame codes temporal_update = 1 — the case would prove nothing)"
        fail=$((fail+1)); return
    fi
    seg_judge "$n" "$w" "$h" "$fr"
}
rav1ecase() { # name = rav1e_WxH_sSPEED_qQUANT (9 frames)
    local n="$1" geo sx qx
    IFS=_ read -r _ geo sx qx <<< "$n"
    local w="${geo%x*}" h="${geo#*x}" sp="${sx#s}" qu="${qx#q}" fr=9
    if ! command -v rav1e >/dev/null 2>&1; then skip_case "$n" "rav1e not on PATH"; return; fi
    rm -f "${WORK:?}/$n.ivf" "${WORK:?}/$n.ref" "${WORK:?}/$n.y4m" "${WORK:?}/$n.dav1d.yuv"
    ffmpeg -loglevel error -y -f lavfi -i "mandelbrot=size=${w}x${h}:rate=30" -frames:v "$fr" \
        -pix_fmt yuv420p "$WORK/$n.y4m" 2>/dev/null || { echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
    rav1e "$WORK/$n.y4m" -o "$WORK/$n.ivf" --speed "$sp" --quantizer "$qu" -l "$fr" >/dev/null 2>&1
    [ -s "$WORK/$n.ivf" ] || { echo "  $n: SETUP FAILED (rav1e produced no stream)"; fail=$((fail+1)); return; }
    rm -f build/conformance-input.ivf
    cp "$WORK/$n.ivf" build/conformance-input.ivf || { echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    if ! seg_property inherit; then
        echo "  $n: SETUP FAILED (no inter frame inherits a non-empty feature set — the case would prove nothing)"
        fail=$((fail+1)); return
    fi
    seg_judge "$n" "$w" "$h" "$fr"
}
svtcase() { # name = svt_WxH_pPRESET_crfCRF (9 frames, --aq-mode 1)
    local n="$1" geo px cx
    IFS=_ read -r _ geo px cx <<< "$n"
    local w="${geo%x*}" h="${geo#*x}" pr="${px#p}" crf="${cx#crf}" fr=9
    if ! command -v SvtAv1EncApp >/dev/null 2>&1; then skip_case "$n" "SvtAv1EncApp not on PATH"; return; fi
    rm -f "${WORK:?}/$n.ivf" "${WORK:?}/$n.ref" "${WORK:?}/$n.yuv" "${WORK:?}/$n.dav1d.yuv"
    ffmpeg -loglevel error -y -f lavfi -i "mandelbrot=size=${w}x${h}:rate=30" -frames:v "$fr" \
        -pix_fmt yuv420p -f rawvideo "$WORK/$n.yuv" 2>/dev/null || {
        echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
    SvtAv1EncApp -i "$WORK/$n.yuv" -w "$w" -h "$h" --fps-num 30 --fps-denom 1 -n "$fr" --preset "$pr" \
        --aq-mode 1 --crf "$crf" --keyint 60 -b "$WORK/$n.ivf" >/dev/null 2>&1
    [ -s "$WORK/$n.ivf" ] || { echo "  $n: SETUP FAILED (SVT-AV1 produced no stream)"; fail=$((fail+1)); return; }
    rm -f build/conformance-input.ivf
    cp "$WORK/$n.ivf" build/conformance-input.ivf || { echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    if ! seg_property seg; then
        echo "  $n: SETUP FAILED (no inter frame carries segmentation — the case would prove nothing)"
        fail=$((fail+1)); return
    fi
    seg_judge "$n" "$w" "$h" "$fr"
}
# The probe's per-frame fields reduced to one GOP property — does the stream show what the case exists for?
#   reorder  : >= 8 hidden coded frames, >= 8 show_existing_frame, and the inter frames' refresh_frame_flags
#              together cover all eight slots
#   keys     : >= 4 coded KEY frames          sframe : >= 2 SWITCH frames (frame_type 3)
#   errres   : EVERY coded inter frame has error_resilient_mode = 1 (and there are >= 20)
#   realtime : no hidden frame, >= 40 inter frames, refreshes spread over >= 3 slots
#   noorder  : the sequence header has enable_order_hint = 0
#   nomfmv   : the sequence header has enable_ref_frame_mvs = 0
#   jnt      : the slowest preset's tools: enable_jnt_comp = 1 and >= 4 frames with reference_select (compound)
# Prints the measured counts either way, so a failed guard says what the stream did have.
gop_property() { # want
    ./build/drishti-vector-probe 2>&1 | awk -v want="$1" '
        function judge() {
            if (!seen) return
            if (se) { nse++ }
            else {
                if (ft == 0) nkey++
                if (ft == 3) nsf++
                if (ft != 0) { ninter++; if (er) ner++; ref_or = or(ref_or, rf); if (rs) nrs++ }
                if (!sf) nhid++
            }
        }
        /^ *enable_order_hint=/ { split($0, a, "="); ordh = a[2] + 0 }
        /^ *enable_ref_frame_mvs=/ { split($0, a, "="); mfmv = a[2] + 0 }
        /^ *enable_jnt_comp=/ { split($0, a, "="); jnt = a[2] + 0 }
        /^ *reference_select=/ { split($0, a, "="); rs = a[2] + 0 }
        /^ *frame_type=/ { judge(); seen = 1; split($0, a, "="); ft = a[2] + 0; se = 0; sf = 0; er = 0; rf = 0; rs = 0 }
        /^ *show_existing_frame=/ { split($0, a, "="); se = a[2] + 0 }
        /^ *show_frame=/ { split($0, a, "="); sf = a[2] + 0 }
        /^ *error_resilient_mode=/ { split($0, a, "="); er = a[2] + 0 }
        /^ *refresh_frame_flags=/ { split($0, a, "="); rf = a[2] + 0 }
        END {
            judge()
            nslot = 0; for (i = 0; i < 8; i++) if (and(ref_or, lshift(1, i))) nslot++
            ok = 0
            if (want == "reorder")  ok = (nhid >= 8 && nse >= 8 && ref_or == 255)
            if (want == "keys")     ok = (nkey >= 4)
            if (want == "sframe")   ok = (nsf >= 2)
            if (want == "errres")   ok = (ninter >= 20 && ner == ninter)
            if (want == "realtime") ok = (nhid == 0 && ninter >= 40 && nslot >= 3)
            if (want == "noorder")  ok = (ordh == 0)
            if (want == "nomfmv")   ok = (mfmv == 0)
            if (want == "jnt")      ok = (jnt == 1 && nrs >= 4)
            printf "hidden=%d show_existing=%d keys=%d switch=%d inter=%d err_res=%d slots=%d compound=%d", \
                nhid, nse, nkey, nsf, ninter, ner, nslot, nrs
            exit !ok
        }'
}
gopcase() { # name = KIND_WxH
    local n="$1" kind geo
    IFS=_ read -r kind geo <<< "$n"
    local w="${geo%x*}" h="${geo#*x}" fr=40 want="reorder" args="--cpu-used=6"
    case "$kind" in
        gopdef)    fr=90 ;;
        goplag35)  fr=90; args="--cpu-used=8 --lag-in-frames=35" ;;
        gop2pass)  fr=60; args="--cpu-used=6 --passes=2 --end-usage=vbr --target-bitrate=200" ;;
        gopkf)     fr=45; args="--cpu-used=6 --kf-max-dist=10"; want="keys" ;;
        goprt)     fr=60; args="--rt --cpu-used=9 --end-usage=cbr --target-bitrate=200"; want="realtime" ;;
        goperr)    args="--cpu-used=6 --error-resilient=1"; want="errres" ;;
        gopsf)     args="--cpu-used=6 --sframe-dist=8 --sframe-mode=1"; want="sframe" ;;
        gopnoord)  args="--cpu-used=6 --enable-order-hint=0"; want="noorder" ;;
        gopnomfmv) args="--cpu-used=6 --enable-ref-frame-mvs=0"; want="nomfmv" ;;
        gopc0)     fr=24; args="--cpu-used=0 --lag-in-frames=19"; want="jnt" ;;   # the bite-5 compound_idx desync
        *)         echo "  $n: SETUP FAILED (unknown case kind)"; fail=$((fail+1)); return ;;
    esac
    rm -f "${WORK:?}/$n.ivf" "${WORK:?}/$n.ref" "${WORK:?}/$n.yuv" "${WORK:?}/$n.dav1d.yuv"
    # a little temporal noise keeps the content natural (no screen-content tools) and the residual busy.
    ffmpeg -loglevel error -y -f lavfi -i "mandelbrot=size=${w}x${h}:rate=30,noise=alls=6:allf=t" -frames:v "$fr" \
        -pix_fmt yuv420p -f rawvideo "$WORK/$n.yuv" 2>/dev/null || {
        echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
    # shellcheck disable=SC2086
    aomenc --codec=av1 -w "$w" -h "$h" --i420 --limit="$fr" $args --ivf -o "$WORK/$n.ivf" "$WORK/$n.yuv" \
        >/dev/null 2>&1
    [ -s "$WORK/$n.ivf" ] || { echo "  $n: SETUP FAILED (aomenc produced no stream)"; fail=$((fail+1)); return; }
    rm -f build/conformance-input.ivf
    cp "$WORK/$n.ivf" build/conformance-input.ivf || { echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    local prop
    if ! prop=$(gop_property "$want"); then
        echo "  $n: SETUP FAILED (no '$want' GOP: $prop — the case would prove nothing)"; fail=$((fail+1)); return
    fi
    echo "  $n ($prop)"
    seg_judge "$n" "$w" "$h" "$fr"
}
# VARIABLE-SIZE judge (0.8.3): a stream whose frame size changes (reference scaling) cannot be sliced at a fixed
# frame size, so aomdec writes ONE FILE PER FRAME (its `%6` output pattern), each at its own size, and drishti's
# harness does the same. dav1d's guard compares the concatenation. The frame count comes from the reference and
# must equal the frames encoded.
# A third argument "nodav1d" drops the dav1d guard, for streams dav1d cannot decode at all (each caller says why).
vs_judge() { # n fr [nodav1d] — decode, per-frame reference, dav1d guard, per-frame compare (every frame hard)
    local n="$1" fr="$2" guard=1
    [ "${3:-}" = "nodav1d" ] && guard=0
    run_drishti "$WORK/$n.ivf" "$WORK/$n.log" || { echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    rm -f "${WORK:?}/$n.ref-"* "${WORK:?}/$n.ref" "${WORK:?}/$n.dav1d.yuv"
    aomdec --rawvideo -o "$WORK/$n.ref-%6.yuv" "$WORK/$n.ivf" 2>/dev/null
    local nref; nref=$(find "$WORK" -maxdepth 1 -name "$n.ref-*.yuv" | wc -l)
    if [ "$nref" -ne "$fr" ]; then
        echo "  $n: SETUP FAILED (aomdec wrote $nref frame(s), not $fr)"; fail=$((fail+1)); return
    fi
    if [ "$guard" = "1" ] && command -v dav1d >/dev/null 2>&1; then
        dav1d -q -i "$WORK/$n.ivf" -o "$WORK/$n.dav1d.yuv" >/dev/null 2>&1
        local k=1
        while [ "$k" -le "$fr" ]; do cat "$WORK/$n.ref-$(printf %06d "$k").yuv"; k=$((k+1)); done > "$WORK/$n.ref"
        if ! cmp -s "$WORK/$n.ref" "$WORK/$n.dav1d.yuv"; then
            echo "  $n: SETUP FAILED (dav1d disagrees with aomdec — the reference cannot be trusted)"
            fail=$((fail+1)); return
        fi
    fi
    local line="  $n:" k=1
    while [ "$k" -le "$fr" ]; do
        local a b
        a=$(md5sum "build/conformance-out-$k.yuv" 2>/dev/null | cut -d' ' -f1)
        b=$(md5sum "$WORK/$n.ref-$(printf %06d "$k").yuv" 2>/dev/null | cut -d' ' -f1)
        if [ -n "$a" ] && [ "$a" = "$b" ]; then line="$line f$k=OK"; pass=$((pass+1))
        else line="$line f$k=REGRESSED"; fail=$((fail+1)); fi
        k=$((k+1))
    done
    echo "$line"
    rm -f "${WORK:?}/$n.ref-"*
}
# superres property: >= 4 coded frames with use_superres = 1 and a downscaled frame_width that is not a multiple
# of 8 (overhang columns exist); "lr" also needs one of them to use loop restoration, "resize" >= 2 distinct
# upscaled sizes (the frame size really changes). Prints the counts either way.
sr_property() { # want
    ./build/drishti-vector-probe 2>&1 | awk -v want="$1" '
        function judge() {
            if (!seen || se) return
            if (sr && (fw % 8) != 0) { nsr++; if (lr) nlr++ }
            sizes[uw "x" fh] = 1
        }
        /^ *frame_type=/ { judge(); seen = 1; se = 0; sr = 0; lr = 0 }
        /^ *show_existing_frame=/ { split($0, a, "="); se = a[2] + 0 }
        /^ *frame_width=/ { split($0, a, "="); fw = a[2] + 0 }
        /^ *frame_height=/ { split($0, a, "="); fh = a[2] + 0 }
        /^ *upscaled_width=/ { split($0, a, "="); uw = a[2] + 0 }
        /^ *use_superres=/ { split($0, a, "="); sr = a[2] + 0 }
        /^ *uses_lr=/ { split($0, a, "="); lr = a[2] + 0 }
        END {
            judge(); ns = 0; for (s in sizes) ns++
            ok = (nsr >= 4)
            if (want == "lr") ok = ok && (nlr >= 1)
            if (want == "resize") ok = ok && (ns >= 2)
            printf "superres_overhang_frames=%d with_lr=%d sizes=%d", nsr, nlr, ns
            exit !ok
        }'
}
srcase() { # name = KIND_WxH
    local n="$1" kind geo
    IFS=_ read -r kind geo <<< "$n"
    local w="${geo%x*}" h="${geo#*x}" fr=12 want="sr" args
    # fixed superres: denominator for inter frames, then for keyframes
    srfixed() { echo "--superres-mode=1 --superres-denominator=$1 --superres-kf-denominator=$2"; }
    case "$kind" in
        srfix)    args="--cpu-used=6 $(srfixed 12 10)" ;;
        srrand)   fr=16; args="--cpu-used=6 --superres-mode=2" ;;
        srsb128)  args="--cpu-used=6 --sb-size=128 $(srfixed 9 14)" ;;
        srodd)    args="--cpu-used=6 $(srfixed 13 11)" ;;
        srtiles)  args="--cpu-used=6 --tile-columns=2 $(srfixed 11 13)" ;;
        srrt)     fr=20; args="--rt --cpu-used=8 $(srfixed 12 12)" ;;
        srlr)     fr=8; want="lr"; args="--cpu-used=4 --enable-restoration=1 $(srfixed 13 13)" ;;
        srresize) fr=20; want="resize"; args="--cpu-used=6 --resize-mode=2 --superres-mode=2" ;;
        *)        echo "  $n: SETUP FAILED (unknown case kind)"; fail=$((fail+1)); return ;;
    esac
    rm -f "${WORK:?}/$n.ivf" "${WORK:?}/$n.yuv"
    ffmpeg -loglevel error -y -f lavfi -i "mandelbrot=size=${w}x${h}:rate=30,noise=alls=6:allf=t" -frames:v "$fr" \
        -pix_fmt yuv420p -f rawvideo "$WORK/$n.yuv" 2>/dev/null || {
        echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
    # shellcheck disable=SC2086
    aomenc --codec=av1 -w "$w" -h "$h" --i420 --limit="$fr" $args --ivf -o "$WORK/$n.ivf" "$WORK/$n.yuv" \
        >/dev/null 2>&1
    [ -s "$WORK/$n.ivf" ] || { echo "  $n: SETUP FAILED (aomenc produced no stream)"; fail=$((fail+1)); return; }
    rm -f build/conformance-input.ivf
    cp "$WORK/$n.ivf" build/conformance-input.ivf || { echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    local prop
    if ! prop=$(sr_property "$want"); then
        echo "  $n: SETUP FAILED (no '$want' superres stream: $prop — the case would prove nothing)"
        fail=$((fail+1)); return
    fi
    echo "  $n ($prop)"
    vs_judge "$n" "$fr"
}
# chroma-format property: the sequence header must carry the format the case claims (mono: num_planes 1; 444:
# subsampling 0/0; 422: 1/0), and extra "lr" needs a frame restoring a CHROMA plane (luma for mono), "sct" a frame
# with allow_screen_content_tools (chroma palettes are only possible there).
fmt_property() { # format extra
    ./build/drishti-vector-probe 2>&1 | awk -v fmt="$1" -v extra="$2" '
        /^ *num_planes=/ { split($0, a, "="); np = a[2] + 0 }
        /^ *subsampling_x=/ { split($0, a, "="); sx = a[2] + 0 }
        /^ *subsampling_y=/ { split($0, a, "="); sy = a[2] + 0 }
        /^ *frame_type=/ { nf++ }
        /^ *allow_screen_content_tools=1/ { nsct++ }
        /^ *lr_type_y=[1-3]/ { nly++ }
        /^ *lr_type_[uv]=[1-3]/ { nlc++ }
        END {
            ok = 0
            if (fmt == "mono") ok = (np == 1)
            if (fmt == "444") ok = (np == 3 && sx == 0 && sy == 0)
            if (fmt == "422") ok = (np == 3 && sx == 1 && sy == 0)
            if (extra == "lr") ok = ok && ((fmt == "mono") ? (nly >= 1) : (nlc >= 1))
            if (extra == "sct") ok = ok && (nsct >= 1)
            printf "planes=%d subsampling=%d/%d frames=%d sct_frames=%d lr_luma=%d lr_chroma=%d", \
                np, sx, sy, nf, nsct, nly, nlc
            exit !ok
        }'
}
fmtcase() { # name = KIND_WxH
    local n="$1" kind geo
    IFS=_ read -r kind geo <<< "$n"
    local w="${geo%x*}" h="${geo#*x}" fr=20 fmt extra="" pf args src="mandelbrot"
    case "$kind" in
        fmtmono*) fmt="mono"; pf="yuv420p"; args="--i420 --monochrome" ;;
        fmt444*)  fmt="444"; pf="yuv444p"; args="--i444 --profile=1" ;;
        fmt422*)  fmt="422"; pf="yuv422p"; args="--i422 --profile=2" ;;
        *)        echo "  $n: SETUP FAILED (unknown case kind)"; fail=$((fail+1)); return ;;
    esac
    local srfix="--superres-mode=1 --superres-denominator=13 --superres-kf-denominator=11"
    case "${kind#fmt}" in
        mono|444|422)       args="$args --cpu-used=6" ;;
        monort|444rt|422rt) fr=30; args="$args --rt --cpu-used=8" ;;
        444scr|422scr)      fr=8; extra="sct"; src="testsrc2"
                            args="$args --cpu-used=6 --tune-content=screen --enable-intrabc=0" ;;
        monosr|444sr|422sr) fr=10; extra="lr"; args="$args --cpu-used=6 $srfix" ;;
        444sb128)           fr=10; args="$args --cpu-used=4 --sb-size=128 --end-usage=q --cq-level=20" ;;
        422oddmi)           fr=12; args="$args --cpu-used=6 --sb-size=64 --lag-in-frames=19" ;;
        *)                  echo "  $n: SETUP FAILED (unknown case kind)"; fail=$((fail+1)); return ;;
    esac
    local sfilt=",noise=alls=6:allf=t"
    [ "$src" = "testsrc2" ] && sfilt=""
    rm -f "${WORK:?}/$n.ivf" "${WORK:?}/$n.yuv"
    ffmpeg -loglevel error -y -f lavfi -i "${src}=size=${w}x${h}:rate=30${sfilt}" -frames:v "$fr" \
        -pix_fmt "$pf" -f rawvideo "$WORK/$n.yuv" 2>/dev/null || {
        echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
    # shellcheck disable=SC2086
    aomenc --codec=av1 -w "$w" -h "$h" --limit="$fr" $args --ivf -o "$WORK/$n.ivf" "$WORK/$n.yuv" >/dev/null 2>&1
    [ -s "$WORK/$n.ivf" ] || { echo "  $n: SETUP FAILED (aomenc produced no stream)"; fail=$((fail+1)); return; }
    rm -f build/conformance-input.ivf
    cp "$WORK/$n.ivf" build/conformance-input.ivf || { echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    local prop
    if ! prop=$(fmt_property "$fmt" "$extra"); then
        echo "  $n: SETUP FAILED (not a '$fmt${extra:+ + $extra}' stream: $prop — the case would prove nothing)"
        fail=$((fail+1)); return
    fi
    echo "  $n ($prop)"
    vs_judge "$n" "$fr"
}
# dimension property: "exact WxH" = every coded frame is exactly W x H (the geometry the case names, not one the
# encoder rounded); "resize" = >= 2 distinct coded sizes. Prints the distinct sizes either way.
dim_property() { # want w h
    ./build/drishti-vector-probe 2>&1 | awk -v want="$1" -v W="$2" -v H="$3" '
        /^ *show_existing_frame=/ { split($0, a, "="); se = a[2] + 0 }
        /^ *frame_width=/ { split($0, a, "="); fw = a[2] + 0 }
        /^ *frame_height=/ {
            split($0, a, "="); fh = a[2] + 0
            if (!se) { sz[fw "x" fh] = 1; nf++; if (fw != W || fh != H) off++ }
        }
        END {
            ns = 0; list = ""; for (s in sz) { ns++; list = list " " s }
            ok = (nf > 0)
            if (want == "exact") ok = ok && (off == 0)
            if (want == "resize") ok = ok && (ns >= 2)
            printf "sizes:%s", list
            exit !ok
        }'
}
dimcase() { # name = dim_WxH_sbS (8 frames)
    local n="$1" geo sbx
    IFS=_ read -r _ geo sbx <<< "$n"
    local w="${geo%x*}" h="${geo#*x}" sb="${sbx#sb}" fr=8 lag=19
    [ "$sb" = "128" ] && lag=0
    rm -f "${WORK:?}/$n.ivf" "${WORK:?}/$n.yuv"
    ffmpeg -loglevel error -y -f lavfi -i "mandelbrot=size=${w}x${h}:rate=30,noise=alls=6:allf=t" -frames:v "$fr" \
        -pix_fmt yuv420p -f rawvideo "$WORK/$n.yuv" 2>/dev/null || {
        echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
    aomenc --codec=av1 -w "$w" -h "$h" --i420 --limit="$fr" --cpu-used=6 --sb-size="$sb" --lag-in-frames="$lag" \
        --ivf -o "$WORK/$n.ivf" "$WORK/$n.yuv" >/dev/null 2>&1
    [ -s "$WORK/$n.ivf" ] || { echo "  $n: SETUP FAILED (aomenc produced no stream)"; fail=$((fail+1)); return; }
    rm -f build/conformance-input.ivf
    cp "$WORK/$n.ivf" build/conformance-input.ivf || { echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    local prop
    if ! prop=$(dim_property exact "$w" "$h"); then
        echo "  $n: SETUP FAILED (not every frame is ${w}x${h}: $prop — the case would prove nothing)"
        fail=$((fail+1)); return
    fi
    vs_judge "$n" "$fr"
}
rscase() { # name = KIND_WxH
    local n="$1" kind geo
    IFS=_ read -r kind geo <<< "$n"
    local w="${geo%x*}" h="${geo#*x}" fr=10 args
    rsfixed() { echo "--resize-mode=1 --resize-denominator=$1 --resize-kf-denominator=$2"; }
    case "$kind" in
        rsfix9)      args="--cpu-used=6 $(rsfixed 9 16)" ;;
        rsfix12)     args="--cpu-used=6 $(rsfixed 12 13)" ;;
        rsfix16)     args="--cpu-used=6 $(rsfixed 16 9)" ;;
        rsup2x)      args="--cpu-used=6 $(rsfixed 8 16)" ;;        # half-size keyframe, full-size inter frames
        rsdown2x)    args="--cpu-used=6 $(rsfixed 16 8)" ;;        # the 2x-larger reference limit
        rsrand128)   fr=20; args="--cpu-used=6 --sb-size=128 --resize-mode=2" ;;
        rsrandtiles) fr=12; args="--cpu-used=6 --tile-columns=1 --tile-rows=1 --resize-mode=2" ;;
        rsrandc2)    fr=20; args="--cpu-used=2 --resize-mode=2" ;;   # the edge-OBMC witness (bite 6)
        rsrandlag)   fr=40; args="--cpu-used=6 --lag-in-frames=35 --resize-mode=2" ;;
        rsrandrt)    fr=30; args="--rt --cpu-used=8 --resize-mode=2" ;;
        *)           echo "  $n: SETUP FAILED (unknown case kind)"; fail=$((fail+1)); return ;;
    esac
    rm -f "${WORK:?}/$n.ivf" "${WORK:?}/$n.yuv"
    ffmpeg -loglevel error -y -f lavfi -i "mandelbrot=size=${w}x${h}:rate=30,noise=alls=6:allf=t" -frames:v "$fr" \
        -pix_fmt yuv420p -f rawvideo "$WORK/$n.yuv" 2>/dev/null || {
        echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
    # shellcheck disable=SC2086
    aomenc --codec=av1 -w "$w" -h "$h" --i420 --limit="$fr" $args --ivf -o "$WORK/$n.ivf" "$WORK/$n.yuv" \
        >/dev/null 2>&1
    [ -s "$WORK/$n.ivf" ] || { echo "  $n: SETUP FAILED (aomenc produced no stream)"; fail=$((fail+1)); return; }
    rm -f build/conformance-input.ivf
    cp "$WORK/$n.ivf" build/conformance-input.ivf || { echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    local prop
    if ! prop=$(dim_property resize "$w" "$h"); then
        echo "  $n: SETUP FAILED (the frame size never changes: $prop — the case would prove nothing)"
        fail=$((fail+1)); return
    fi
    echo "  $n ($prop)"
    vs_judge "$n" "$fr"
}
# bit-depth property: the sequence header carries bit depth `bd` and the claimed format (420 / 444 / 422 / mono),
# and `extra` is present: "lr" (a CHROMA plane restored; luma for mono), "sct" (screen-content tools), "lossless"
# (a coded-lossless frame), "resize" (>= 2 coded sizes).
bd_property() { # bd format extra
    ./build/drishti-vector-probe 2>&1 | awk -v bd="$1" -v fmt="$2" -v extra="$3" '
        /^ *bit_depth=/ { split($0, a, "="); b = a[2] + 0 }
        /^ *num_planes=/ { split($0, a, "="); np = a[2] + 0 }
        /^ *subsampling_x=/ { split($0, a, "="); sx = a[2] + 0 }
        /^ *subsampling_y=/ { split($0, a, "="); sy = a[2] + 0 }
        /^ *show_existing_frame=/ { split($0, a, "="); se = a[2] + 0 }
        /^ *frame_width=/ { split($0, a, "="); fw = a[2] + 0 }
        /^ *frame_height=/ { split($0, a, "="); if (!se) sz[fw "x" (a[2] + 0)] = 1 }
        /^ *coded_lossless=1/ { nll++ }
        /^ *allow_screen_content_tools=1/ { nsct++ }
        /^ *lr_type_y=[1-3]/ { nly++ }
        /^ *lr_type_[uv]=[1-3]/ { nlc++ }
        END {
            ns = 0; for (s in sz) ns++
            ok = (b == bd)
            if (fmt == "420") ok = ok && (np == 3 && sx == 1 && sy == 1)
            if (fmt == "444") ok = ok && (np == 3 && sx == 0 && sy == 0)
            if (fmt == "422") ok = ok && (np == 3 && sx == 1 && sy == 0)
            if (fmt == "mono") ok = ok && (np == 1)
            if (extra == "lr") ok = ok && ((fmt == "mono") ? (nly >= 1) : (nlc >= 1))
            if (extra == "sct") ok = ok && (nsct >= 1)
            if (extra == "lossless") ok = ok && (nll >= 1)
            if (extra == "resize") ok = ok && (ns >= 2)
            printf "bit_depth=%d planes=%d subsampling=%d/%d lossless_frames=%d sct_frames=%d lr_chroma=%d sizes=%d", \
                b, np, sx, sy, nll, nsct, nlc, ns
            exit !ok
        }'
}
bdcase() { # name = KIND_WxH
    local n="$1" kind geo
    IFS=_ read -r kind geo <<< "$n"
    local w="${geo%x*}" h="${geo#*x}" fr=12 bd fmt="420" extra="" enc="aomenc" src="mandelbrot" args=""
    local srfix="--superres-mode=1 --superres-denominator=13 --superres-kf-denominator=11"
    case "$kind" in
        b10*) bd=10 ;;
        b12*) bd=12; args="--profile=2" ;;
        r12*) bd=12; enc="rav1e" ;;
        *)    echo "  $n: SETUP FAILED (unknown case kind)"; fail=$((fail+1)); return ;;
    esac
    case "$kind" in
        b10|b12)       args="$args --cpu-used=6"; fr=20 ;;
        b10444)        fmt="444"; args="--profile=1 --cpu-used=6" ;;
        b10422)        fmt="422"; args="--profile=2 --cpu-used=6" ;;
        b10mono|b12mono) fmt="mono"; args="$args --monochrome --cpu-used=6" ;;
        b10sr|b12sr)   fr=10; extra="lr"; args="$args --cpu-used=6 $srfix" ;;
        b10rs)         fr=16; extra="resize"; args="--cpu-used=2 --resize-mode=2" ;;
        b10c0|b12c0)   args="$args --cpu-used=0" ;;
        b10scr)        fr=8; extra="sct"; src="testsrc2"
                       args="--cpu-used=6 --tune-content=screen --enable-intrabc=0" ;;
        b10sb128)      fr=10; args="--cpu-used=4 --sb-size=128 --end-usage=q --cq-level=20" ;;
        b10rt)         fr=30; args="--rt --cpu-used=8" ;;
        b10ll|b12ll)   fr=4; extra="lossless"; args="$args --cpu-used=6 --lossless=1" ;;
        b10hiq)        fr=10; args="--cpu-used=4 --end-usage=q --cq-level=5" ;;
        r12444)        fmt="444"; fr=10 ;;
        r12422)        fmt="422"; fr=10 ;;
        *)             echo "  $n: SETUP FAILED (unknown case kind)"; fail=$((fail+1)); return ;;
    esac
    local pf="yuv${fmt}p${bd}le" iflag="--i${fmt}" sfilt=",noise=alls=6:allf=t"
    [ "$fmt" = "mono" ] && { pf="yuv420p${bd}le"; iflag="--i420"; }
    [ "$src" = "testsrc2" ] && sfilt=""
    rm -f "${WORK:?}/$n.ivf" "${WORK:?}/$n.yuv" "${WORK:?}/$n.y4m"
    if [ "$enc" = "rav1e" ]; then
        if ! command -v rav1e >/dev/null 2>&1; then skip_case "$n" "rav1e not on PATH"; return; fi
        ffmpeg -loglevel error -y -f lavfi -i "${src}=size=${w}x${h}:rate=30${sfilt}" -frames:v "$fr" -pix_fmt "$pf" \
            -strict -1 "$WORK/$n.y4m" 2>/dev/null || { echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
        rav1e "$WORK/$n.y4m" -o "$WORK/$n.ivf" --speed 6 --quantizer 100 -l "$fr" >/dev/null 2>&1
    else
        ffmpeg -loglevel error -y -f lavfi -i "${src}=size=${w}x${h}:rate=30${sfilt}" -frames:v "$fr" -pix_fmt "$pf" \
            -f rawvideo "$WORK/$n.yuv" 2>/dev/null || { echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
        # shellcheck disable=SC2086
        aomenc --codec=av1 -w "$w" -h "$h" $iflag --input-bit-depth="$bd" --bit-depth="$bd" --limit="$fr" $args \
            --ivf -o "$WORK/$n.ivf" "$WORK/$n.yuv" >/dev/null 2>&1
    fi
    [ -s "$WORK/$n.ivf" ] || { echo "  $n: SETUP FAILED ($enc produced no stream)"; fail=$((fail+1)); return; }
    rm -f build/conformance-input.ivf
    cp "$WORK/$n.ivf" build/conformance-input.ivf || { echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    local prop
    if ! prop=$(bd_property "$bd" "$fmt" "$extra"); then
        echo "  $n: SETUP FAILED (not a $bd-bit $fmt${extra:+ + $extra} stream: $prop — the case would prove nothing)"
        fail=$((fail+1)); return
    fi
    echo "  $n ($prop)"
    vs_judge "$n" "$fr"
}
# odd-MI INTER frames (0.8.3). The probe must show an INTER frame whose MI extent leaves a bottom or right
# superblock-row remainder that is not a multiple of 16 luma samples (mi_rows % 4 == 2 or mi_cols % 4 == 2): that
# is where an edge block's chroma is cut to 4 rows or columns by an MI-grid-sized allocation (see oddmi-inter-*).
oddmiicase() { # name = oddmii_WxH_sbS_lagL_cC
    local n="$1" geo sbx lagx cx
    IFS=_ read -r _ geo sbx lagx cx <<< "$n"
    local w="${geo%x*}" h="${geo#*x}" sb="${sbx#sb}" lag="${lagx#lag}" cpu="${cx#c}" fr=12
    rm -f "${WORK:?}/$n.ivf" "${WORK:?}/$n.ref" "${WORK:?}/$n.yuv" "${WORK:?}/$n.dav1d.yuv"
    ffmpeg -loglevel error -y -f lavfi -i "mandelbrot=size=${w}x${h}:rate=30,noise=alls=6:allf=t" -frames:v "$fr" \
        -pix_fmt yuv420p -f rawvideo "$WORK/$n.yuv" 2>/dev/null || {
        echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
    aomenc --codec=av1 -w "$w" -h "$h" --i420 --limit="$fr" --cpu-used="$cpu" --sb-size="$sb" \
        --lag-in-frames="$lag" --ivf -o "$WORK/$n.ivf" "$WORK/$n.yuv" >/dev/null 2>&1
    [ -s "$WORK/$n.ivf" ] || { echo "  $n: SETUP FAILED (aomenc produced no stream)"; fail=$((fail+1)); return; }
    rm -f build/conformance-input.ivf
    cp "$WORK/$n.ivf" build/conformance-input.ivf || { echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    if ! ./build/drishti-vector-probe 2>&1 | awk '
        /^ *frame_type=/ { split($0, a, "="); inter = (a[2] + 0 != 0) }
        /^ *mi_cols=/ { split($0, a, "="); mc = a[2] + 0 }
        /^ *mi_rows=/ { split($0, a, "="); if (inter && ((mc % 4) == 2 || ((a[2] + 0) % 4) == 2)) f = 1 }
        END { exit !f }'; then
        echo "  $n: SETUP FAILED (no inter frame with mi_rows or mi_cols % 4 == 2 — the case would prove nothing)"
        fail=$((fail+1)); return
    fi
    seg_judge "$n" "$w" "$h" "$fr"
}
echo "--- segmentation on inter frames (libaom AQ; copied map + inherited data; every frame hard) ---"
for c in $SEGI_CASES; do segicase "$c"; done
echo "--- temporal segmentation (libaom realtime cyclic refresh; seg_id_predicted; every frame hard) ---"
for c in $TSEG_CASES; do tsegcase "$c"; done
# Does the probe show what a QM case exists for? want: flat (matrices signalled, none can apply), applies (some
# frame applies one), level0 (every applying frame at level 0), levels3 (applying frames at >= 3 distinct luma
# levels), mixedll (a frame that applies a matrix AND has lossless and lossy segments: 0 < LosslessArray < 255),
# uvlevel (a frame applying a matrix whose chroma level differs from luma), sct (screen-content tools on). Every
# want except flat also requires an applying frame; bd / fmt are checked as bd_property does.
qm_property() { # want bd fmt
    ./build/drishti-vector-probe 2>&1 | awk -v want="$1" -v bd="$2" -v fmt="$3" '
        /^ *bit_depth=/ { split($0, a, "="); b = a[2] + 0 }
        /^ *num_planes=/ { split($0, a, "="); np = a[2] + 0 }
        /^ *subsampling_x=/ { split($0, a, "="); sx = a[2] + 0 }
        /^ *subsampling_y=/ { split($0, a, "="); sy = a[2] + 0 }
        /^ *frame_type=/ { f++ }
        /^ *using_qmatrix=1/ { nuq++ }
        /^ *qm_y=/ { split($0, a, "="); y[f] = a[2] + 0 }
        /^ *qm_u=/ { split($0, a, "="); u[f] = a[2] + 0 }
        /^ *qm_v=/ { split($0, a, "="); v[f] = a[2] + 0 }
        /^ *qmatrix_applies=1/ { ap[f] = 1 }
        /^ *lossless_mask=/ { split($0, a, "="); m[f] = a[2] + 0 }
        /^ *allow_screen_content_tools=1/ { nsct++ }
        END {
            nap = 0; nlv = 0; nnz = 0; nmix = 0; nuv = 0
            for (k = 1; k <= f; k++) {
                if (!ap[k]) continue
                nap++
                if (!(y[k] in lv)) { lv[y[k]] = 1; nlv++ }
                if (y[k] != 0) nnz++
                if (m[k] > 0 && m[k] < 255) nmix++
                if (np > 1 && (u[k] != y[k] || v[k] != y[k])) nuv++
            }
            ok = (b == bd) && (nuq >= 1)
            if (fmt == "420") ok = ok && (np == 3 && sx == 1 && sy == 1)
            if (fmt == "444") ok = ok && (np == 3 && sx == 0 && sy == 0)
            if (fmt == "mono") ok = ok && (np == 1)
            if (want == "flat") ok = ok && (nap == 0)
            if (want != "flat") ok = ok && (nap >= 1)
            if (want == "level0") ok = ok && (nnz == 0)
            if (want == "levels3") ok = ok && (nlv >= 3)
            if (want == "mixedll") ok = ok && (nmix >= 1)
            if (want == "uvlevel") ok = ok && (nuv >= 1)
            if (want == "sct") ok = ok && (nsct >= 1)
            printf "bit_depth=%d planes=%d using_qmatrix_frames=%d applying_frames=%d luma_levels=%d mixed_lossless=%d", \
                b, np, nuq, nap, nlv, nmix
            printf " chroma_level_differs=%d sct_frames=%d", nuv, nsct
            exit !ok
        }'
}
qmcase() { # name = KIND_WxH (every frame hard)
    local n="$1" kind geo
    IFS=_ read -r kind geo <<< "$n"
    local w="${geo%x*}" h="${geo#*x}" fr=8 bd=8 fmt="420" enc="aomenc" src="mandelbrot" want="applies" args=""
    local lag0="--lag-in-frames=0 --enable-restoration=0 --enable-palette=0 --enable-intrabc=0"
    case "$kind" in
        qm15)   fr=4; want="flat"
                args="--cpu-used=8 --end-usage=q --cq-level=30 $lag0 --enable-qm=1 --qm-min=15 --qm-max=15" ;;
        qmon)   fr=4; args="--cpu-used=8 --end-usage=q --cq-level=30 $lag0 --enable-qm=1" ;;
        qm0)    want="level0"; args="--cpu-used=6 --enable-qm=1 --qm-min=0 --qm-max=0" ;;
        qmall)  fr=20; want="levels3"; args="--cpu-used=4 --sb-size=128 --enable-qm=1 --qm-min=0 --qm-max=14" ;;
        qmll)   fr=3; want="mixedll"
                args="--cpu-used=8 --end-usage=q --cq-level=0 --aq-mode=1 --deltaq-mode=0 --tune-content=default"
                args="$args $lag0 --enable-qm=1 --qm-min=0 --qm-max=4" ;;
        qmiq)   fr=6; want="uvlevel"; args="--cpu-used=6 --tune=iq" ;;
        qm444)  fmt="444"; want="uvlevel"; args="--profile=1 --cpu-used=6 --tune=iq" ;;
        qmb10)  bd=10; args="--cpu-used=6 --enable-qm=1 --qm-min=1 --qm-max=7" ;;
        qmb12)  bd=12; fr=6; args="--profile=2 --cpu-used=6 --enable-qm=1 --qm-min=0 --qm-max=9" ;;
        qmmono) fmt="mono"; args="--monochrome --cpu-used=6 --enable-qm=1 --qm-min=0 --qm-max=5" ;;
        qmscr)  src="testsrc2"; want="sct"
                args="--cpu-used=6 --tune-content=screen --enable-intrabc=0 --enable-qm=1 --qm-min=0 --qm-max=8" ;;
        qmrt)   fr=30; args="--rt --cpu-used=8 --enable-qm=1 --qm-min=0 --qm-max=10" ;;
        qmai)   fr=6; args="--allintra --cpu-used=6 --enable-qm=1" ;;
        svtqm)  fr=16; enc="svt"; want="uvlevel"
                args="--preset 8 --enable-qm 1 --qm-min 0 --qm-max 6 --chroma-qm-min 9 --chroma-qm-max 14 --keyint 32" ;;
        *)      echo "  $n: SETUP FAILED (unknown case kind)"; fail=$((fail+1)); return ;;
    esac
    local pf="yuv${fmt}p" iflag="--i${fmt}" sfilt=",noise=alls=6:allf=t"
    [ "$fmt" = "mono" ] && { pf="yuv420p"; iflag="--i420"; }
    [ "$bd" != 8 ] && pf="${pf}${bd}le"
    [ "$src" = "testsrc2" ] && sfilt=""
    rm -f "${WORK:?}/$n.ivf" "${WORK:?}/$n.yuv" "${WORK:?}/$n.y4m"
    if [ "$enc" = "svt" ]; then
        if ! command -v SvtAv1EncApp >/dev/null 2>&1; then skip_case "$n" "SvtAv1EncApp not on PATH"; return; fi
        ffmpeg -loglevel error -y -f lavfi -i "${src}=size=${w}x${h}:rate=30${sfilt}" -frames:v "$fr" -pix_fmt "$pf" \
            "$WORK/$n.y4m" 2>/dev/null || { echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
        # shellcheck disable=SC2086
        SvtAv1EncApp -i "$WORK/$n.y4m" -b "$WORK/$n.ivf" $args >/dev/null 2>&1
    else
        ffmpeg -loglevel error -y -f lavfi -i "${src}=size=${w}x${h}:rate=30${sfilt}" -frames:v "$fr" -pix_fmt "$pf" \
            -f rawvideo "$WORK/$n.yuv" 2>/dev/null || { echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
        # shellcheck disable=SC2086
        aomenc --codec=av1 -w "$w" -h "$h" $iflag --input-bit-depth="$bd" --bit-depth="$bd" --limit="$fr" $args \
            --ivf -o "$WORK/$n.ivf" "$WORK/$n.yuv" >/dev/null 2>&1
    fi
    [ -s "$WORK/$n.ivf" ] || { echo "  $n: SETUP FAILED ($enc produced no stream)"; fail=$((fail+1)); return; }
    rm -f build/conformance-input.ivf
    cp "$WORK/$n.ivf" build/conformance-input.ivf || { echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    local prop
    if ! prop=$(qm_property "$want" "$bd" "$fmt"); then
        echo "  $n: SETUP FAILED (not a $bd-bit $fmt '$want' quantizer-matrix stream: $prop — the case would prove nothing)"
        fail=$((fail+1)); return
    fi
    echo "  $n ($prop)"
    vs_judge "$n" "$fr"
}
echo "--- quantizer matrices (7.12.3 step 1b; every frame hard) ---"
for c in $QM_CASES; do qmcase "$c"; done
# Does the probe show what a FILM GRAIN case exists for? Per OUTPUT frame (show_frame or show_existing_frame) it reads
# the grain the output process applies (after load_grain_params). want: applies (some output frame applies grain),
# lagged (a show_existing_frame applies its saved grain), reload (a grain frame re-used a reference's parameters:
# update_grain 0), superres (a grain frame is superres-upscaled), resize (>= 2 coded sizes), clipid / clipbt (a grain
# frame clips to the restricted range, with matrix_coefficients MC_IDENTITY / not). bd / fmt as bd_property.
grain_property() { # want bd fmt
    ./build/drishti-vector-probe 2>&1 | awk -v want="$1" -v bd="$2" -v fmt="$3" '
        /^ *bit_depth=/ { split($0, a, "="); b = a[2] + 0 }
        /^ *num_planes=/ { split($0, a, "="); np = a[2] + 0 }
        /^ *subsampling_x=/ { split($0, a, "="); sx = a[2] + 0 }
        /^ *subsampling_y=/ { split($0, a, "="); sy = a[2] + 0 }
        /^ *frame_type=/ { f++ }
        /^ *show_existing_frame=/ { split($0, a, "="); se[f] = a[2] + 0 }
        /^ *show_frame=/ { split($0, a, "="); sh[f] = a[2] + 0 }
        /^ *use_superres=/ { split($0, a, "="); sr[f] = a[2] + 0 }
        /^ *frame_width=/ { split($0, a, "="); fw = a[2] + 0 }
        /^ *frame_height=/ { split($0, a, "="); if (!se[f]) sz[fw "x" (a[2] + 0)] = 1 }
        /^ *fg_apply_grain=/ { split($0, a, "="); ap[f] = a[2] + 0 }
        /^ *fg_update_grain=/ { split($0, a, "="); up[f] = a[2] + 0 }
        /^ *fg_clip_to_restricted_range=/ { split($0, a, "="); cl[f] = a[2] + 0 }
        /^ *matrix_coefficients=/ { split($0, a, "="); mc = a[2] + 0 }
        END {
            nap = 0; nse = 0; nre = 0; nsr = 0; ns = 0; ncl = 0
            for (s in sz) ns++
            for (k = 1; k <= f; k++) {
                if (!(sh[k] || se[k]) || !ap[k]) continue
                nap++
                if (se[k]) nse++
                if (!se[k] && !up[k]) nre++
                if (sr[k]) nsr++
                if (cl[k]) ncl++
            }
            ok = (b == bd) && (nap >= 1)
            if (fmt == "420") ok = ok && (np == 3 && sx == 1 && sy == 1)
            if (fmt == "444") ok = ok && (np == 3 && sx == 0 && sy == 0)
            if (fmt == "422") ok = ok && (np == 3 && sx == 1 && sy == 0)
            if (fmt == "mono") ok = ok && (np == 1)
            if (want == "lagged") ok = ok && (nse >= 1)
            if (want == "reload") ok = ok && (nre >= 1)
            if (want == "superres") ok = ok && (nsr >= 1)
            if (want == "resize") ok = ok && (ns >= 2)
            if (want == "clipid") ok = ok && (ncl >= 1) && (mc == 0)
            if (want == "clipbt") ok = ok && (ncl >= 1) && (mc != 0)
            printf "bit_depth=%d planes=%d grain_outputs=%d via_show_existing=%d reloads=%d superres=%d sizes=%d", \
                b, np, nap, nse, nre, nsr, ns
            printf " clipped=%d matrix_coefficients=%d", ncl, mc
            exit !ok
        }'
}
fgcase() { # name = KIND_WxH (every frame hard)
    local n="$1" kind geo
    IFS=_ read -r kind geo <<< "$n"
    local w="${geo%x*}" h="${geo#*x}" fr=10 bd=8 fmt="420" enc="aomenc" want="lagged" args=""
    local src="mandelbrot" sfilt=",noise=alls=6:allf=t"
    local cicp="--color-primaries=bt709 --transfer-characteristics=bt709"
    case "$kind" in
        fgt5|fgt9|fgt11) fr=6; want="reload"; args="--cpu-used=6 --lag-in-frames=0 --film-grain-test=${kind#fgt}" ;;
        fgt[0-9]*) args="--cpu-used=6 --film-grain-test=${kind#fgt}" ;;
        fgb10)  bd=10; args="--cpu-used=6 --film-grain-test=3" ;;
        fgb12)  bd=12; args="--profile=2 --cpu-used=6 --film-grain-test=7" ;;
        fg444)  fmt="444"; args="--profile=1 --cpu-used=6 --film-grain-test=5" ;;
        fg422)  fmt="422"; bd=10; args="--profile=2 --cpu-used=6 --film-grain-test=9" ;;
        fgmono) fmt="mono"; args="--monochrome --cpu-used=6 --film-grain-test=2" ;;
        fgsr)   fr=8; want="superres"
                args="--cpu-used=6 --film-grain-test=4 --superres-mode=1 --superres-denominator=13 --superres-kf-denominator=11" ;;
        fgrs)   fr=16; want="resize"; args="--cpu-used=6 --resize-mode=2 --film-grain-test=6" ;;   # 2 = random
        fgsvt)  enc="svt"; args="--preset 8 --film-grain 10 --keyint 32" ;;
        fgrav)  enc="rav1e"; args="--speed 6 --photon-noise 8" ;;
        fgid)   fr=6; fmt="444"; src="testsrc2"; sfilt=""; want="clipid"
                args="--profile=1 --cpu-used=6 --film-grain-test=1 $cicp --matrix-coefficients=identity" ;;
        fgbt)   fr=6; fmt="444"; src="testsrc2"; sfilt=""; want="clipbt"
                args="--profile=1 --cpu-used=6 --film-grain-test=1 $cicp --matrix-coefficients=bt709" ;;
        *)      echo "  $n: SETUP FAILED (unknown case kind)"; fail=$((fail+1)); return ;;
    esac
    local pf="yuv${fmt}p" iflag="--i${fmt}"
    [ "$fmt" = "mono" ] && { pf="yuv420p"; iflag="--i420"; }
    [ "$bd" != 8 ] && pf="${pf}${bd}le"
    rm -f "${WORK:?}/$n.ivf" "${WORK:?}/$n.yuv" "${WORK:?}/$n.y4m"
    if [ "$enc" = "svt" ] || [ "$enc" = "rav1e" ]; then
        local tool="SvtAv1EncApp"; [ "$enc" = "rav1e" ] && tool="rav1e"
        if ! command -v "$tool" >/dev/null 2>&1; then skip_case "$n" "$tool not on PATH"; return; fi
        ffmpeg -loglevel error -y -f lavfi -i "${src}=size=${w}x${h}:rate=30${sfilt}" -frames:v "$fr" \
            -pix_fmt "$pf" "$WORK/$n.y4m" 2>/dev/null || { echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
        # shellcheck disable=SC2086
        if [ "$enc" = "svt" ]; then SvtAv1EncApp -i "$WORK/$n.y4m" -b "$WORK/$n.ivf" $args >/dev/null 2>&1
        else rav1e "$WORK/$n.y4m" -o "$WORK/$n.ivf" -l "$fr" $args >/dev/null 2>&1; fi
    else
        ffmpeg -loglevel error -y -f lavfi -i "${src}=size=${w}x${h}:rate=30${sfilt}" -frames:v "$fr" \
            -pix_fmt "$pf" -f rawvideo "$WORK/$n.yuv" 2>/dev/null || { echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
        # shellcheck disable=SC2086
        aomenc --codec=av1 -w "$w" -h "$h" $iflag --input-bit-depth="$bd" --bit-depth="$bd" --limit="$fr" $args \
            --ivf -o "$WORK/$n.ivf" "$WORK/$n.yuv" >/dev/null 2>&1
    fi
    [ -s "$WORK/$n.ivf" ] || { echo "  $n: SETUP FAILED ($enc produced no stream)"; fail=$((fail+1)); return; }
    rm -f build/conformance-input.ivf
    cp "$WORK/$n.ivf" build/conformance-input.ivf || { echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    local prop
    if ! prop=$(grain_property "$want" "$bd" "$fmt"); then
        echo "  $n: SETUP FAILED (not a $bd-bit $fmt '$want' film-grain stream: $prop — the case would prove nothing)"
        fail=$((fail+1)); return
    fi
    echo "  $n ($prop)"
    vs_judge "$n" "$fr"
}
echo "--- film grain (7.18.3, the output process; every frame hard) ---"
for c in $FG_CASES; do fgcase "$c"; done
# Does the probe show what an INTRA BLOCK COPY case exists for? want: base (some frame allows intrabc), lossless (an
# allow_intrabc frame is coded lossless), aq (... has segmentation on), tiles (... has >= 2 tiles), sb128 (128x128
# superblocks), gop (>= 2 allow_intrabc frames AND >= 1 inter frame). bd / fmt as bd_property.
ibc_property() { # want bd fmt
    ./build/drishti-vector-probe 2>&1 | awk -v want="$1" -v bd="$2" -v fmt="$3" '
        /^ *bit_depth=/ { split($0, a, "="); b = a[2] + 0 }
        /^ *num_planes=/ { split($0, a, "="); np = a[2] + 0 }
        /^ *subsampling_x=/ { split($0, a, "="); sx = a[2] + 0 }
        /^ *subsampling_y=/ { split($0, a, "="); sy = a[2] + 0 }
        /^ *use_128x128_superblock=/ { split($0, a, "="); s128 = a[2] + 0 }
        /^ *frame_type=/ { f++; split($0, a, "="); ft[f] = a[2] + 0 }
        /^ *coded_lossless=/ { split($0, a, "="); ll[f] = a[2] + 0 }
        /^ *tile_cols=/ { split($0, a, "="); tc[f] = a[2] + 0 }
        /^ *tile_rows=/ { split($0, a, "="); tr[f] = a[2] + 0 }
        /^ *allow_intrabc=/ { split($0, a, "="); ib[f] = a[2] + 0 }
        /^ *segmentation_enabled=/ { split($0, a, "="); sg[f] = a[2] + 0 }
        END {
            nib = 0; nll = 0; nsg = 0; nti = 0; ninter = 0
            for (k = 1; k <= f; k++) {
                if (ft[k] == 1) ninter++
                if (!ib[k]) continue
                nib++
                if (ll[k]) nll++
                if (sg[k]) nsg++
                if (tc[k] * tr[k] >= 2) nti++
            }
            ok = (b == bd) && (nib >= 1)
            if (fmt == "420") ok = ok && (np == 3 && sx == 1 && sy == 1)
            if (fmt == "444") ok = ok && (np == 3 && sx == 0 && sy == 0)
            if (fmt == "422") ok = ok && (np == 3 && sx == 1 && sy == 0)
            if (fmt == "mono") ok = ok && (np == 1)
            if (want == "lossless") ok = ok && (nll >= 1)
            if (want == "aq") ok = ok && (nsg >= 1)
            if (want == "tiles") ok = ok && (nti >= 1)
            if (want == "sb128") ok = ok && (s128 == 1)
            if (want == "gop") ok = ok && (nib >= 2) && (ninter >= 1)
            printf "bit_depth=%d planes=%d intrabc_frames=%d lossless=%d segmented=%d tiled=%d sb128=%d inter_frames=%d", \
                b, np, nib, nll, nsg, nti, s128, ninter
            exit !ok
        }'
}
ibccase() { # name = KIND_WxH (every frame hard)
    local n="$1" kind geo
    IFS=_ read -r kind geo <<< "$n"
    local w="${geo%x*}" h="${geo#*x}" fr=2 bd=8 fmt="420" want="base" args="" kf="--kf-max-dist=0"
    case "$kind" in
        ibc)     args="--cpu-used=2" ;;
        ibc0)    args="--cpu-used=0" ;;
        ibcodd)  args="--cpu-used=1" ;;
        ibc444)  fmt="444"; args="--profile=1 --cpu-used=1" ;;
        ibc422)  fmt="422"; bd=10; args="--profile=2 --cpu-used=1" ;;
        ibcb10)  bd=10; args="--cpu-used=1" ;;
        ibcb12)  bd=12; args="--profile=2 --cpu-used=1" ;;
        ibcmono) fmt="mono"; args="--monochrome --cpu-used=1" ;;
        ibcll)   want="lossless"; args="--cpu-used=1 --lossless=1" ;;
        ibc128)  want="sb128"; args="--cpu-used=1 --sb-size=128" ;;
        ibctile) want="tiles"; args="--cpu-used=2 --tile-columns=1 --tile-rows=1" ;;
        ibcaq)   want="aq"; args="--cpu-used=1 --aq-mode=1" ;;
        ibcgop)  fr=10; want="gop"; kf="--kf-max-dist=4"; args="--cpu-used=2" ;;
        *)       echo "  $n: SETUP FAILED (unknown case kind)"; fail=$((fail+1)); return ;;
    esac
    local pf="yuv${fmt}p" iflag="--i${fmt}"
    [ "$fmt" = "mono" ] && { pf="yuv420p"; iflag="--i420"; }
    [ "$bd" != 8 ] && pf="${pf}${bd}le"
    rm -f "${WORK:?}/$n.ivf" "${WORK:?}/$n.yuv"
    ffmpeg -loglevel error -y -f lavfi -i "testsrc2=size=${w}x${h}:rate=30" -frames:v "$fr" -pix_fmt "$pf" \
        -f rawvideo "$WORK/$n.yuv" 2>/dev/null || { echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
    # shellcheck disable=SC2086
    aomenc --codec=av1 -w "$w" -h "$h" $iflag --input-bit-depth="$bd" --bit-depth="$bd" --limit="$fr" $args $kf \
        --tune-content=screen --enable-intrabc=1 --ivf -o "$WORK/$n.ivf" "$WORK/$n.yuv" >/dev/null 2>&1
    [ -s "$WORK/$n.ivf" ] || { echo "  $n: SETUP FAILED (aomenc produced no stream)"; fail=$((fail+1)); return; }
    rm -f build/conformance-input.ivf
    cp "$WORK/$n.ivf" build/conformance-input.ivf || { echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    local prop
    if ! prop=$(ibc_property "$want" "$bd" "$fmt"); then
        echo "  $n: SETUP FAILED (not a $bd-bit $fmt '$want' intrabc stream: $prop — the case would prove nothing)"
        fail=$((fail+1)); return
    fi
    # aomdec writes one frame per shown frame; an odd-size encode may code fewer frames than requested
    local nref; nref=$(aomdec --rawvideo -o /dev/null --summary "$WORK/$n.ivf" 2>&1 | grep -oE '[0-9]+ showed' \
        | grep -oE '[0-9]+' | head -1 || true)
    echo "  $n ($prop)"
    vs_judge "$n" "${nref:-$fr}"
}
echo "--- intra block copy (5.11.7 use_intrabc, 7.11.3 from the current frame; every frame hard) ---"
for c in $IBC_CASES; do ibccase "$c"; done
LST_TOOLS="ref/aom-build/examples"
lstcase() { # name = lst_WxH_LFWxLFH_bsB ; seed = position in LST_CASES
    local n="$1" seed="$2" geo lfx bsx
    IFS=_ read -r _ geo lfx bsx <<< "$n"
    local w="${geo%x*}" h="${geo#*x}" lfw="${lfx%x*}" lfh="${lfx#*x}" bs="${bsx#bs}" nl=4
    [ "$bs" = "$bsx" ] && bs="$bsx"
    local t
    for t in lightfield_encoder lightfield_bitstream_parsing lightfield_tile_list_decoder; do
        if [ ! -x "$LST_TOOLS/$t" ]; then skip_case "$n" "$LST_TOOLS/$t not built"; return; fi
    done
    local d="$WORK/$n.d" tools; tools="$(pwd)/$LST_TOOLS"
    rm -rf "${d:?}"; mkdir -p "$d"
    local nv=$((lfw * lfh)) nanch=$(( ((lfw + bs - 1) / bs) * ((lfh + bs - 1) / bs) ))
    ffmpeg -loglevel error -y -f lavfi -i "mandelbrot=size=${w}x${h}:rate=25:start_scale=3:end_scale=0.3" \
        -frames:v "$nv" -pix_fmt yuv420p -f rawvideo "$d/lf.yuv" 2>/dev/null || {
        echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
    (cd "$d" && "$tools/lightfield_encoder" "$w" "$h" lf.yuv lf.ivf "$lfw" "$lfh" "$bs" >/dev/null 2>&1) || {
        echo "  $n: SETUP FAILED (lightfield_encoder)"; fail=$((fail+1)); return; }
    # four tile lists of 1..64 entries (the 512x512 output holds 8 x 8 tiles of 64): image, anchor, column, row
    awk -v nl="$nl" -v seed="$seed" -v nv="$nv" -v na="$nanch" -v tc=$((w / 64)) -v tr=$((h / 64)) '
        function r(m) { x = (x * 75 + 74) % 65537; return x % m }
        BEGIN { x = seed * 7919 + 1
                for (L = 0; L < nl; L++) { print "Frame " L; k = 1 + r(64)
                    for (i = 0; i < k; i++) print r(nv), r(na), r(tc), r(tr) } }' > "$d/tiles.txt"
    (cd "$d" && "$tools/lightfield_bitstream_parsing" lf.ivf tl.ivf "$nanch" tiles.txt >/dev/null 2>&1) || {
        echo "  $n: SETUP FAILED (lightfield_bitstream_parsing)"; fail=$((fail+1)); return; }
    (cd "$d" && "$tools/lightfield_tile_list_decoder" tl.ivf ref1d.yuv "$nanch" "$nl" 0 >/dev/null 2>&1) || {
        echo "  $n: SETUP FAILED (lightfield_tile_list_decoder)"; fail=$((fail+1)); return; }
    printf '%d\n' "$nanch" > "$d/tl.lst"
    run_drishti_lst "$d/tl.ivf" "$d/tl.lst" "$d/drishti.log" || {
        echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    local line="  $n ($nanch anchors, $nl tile lists):" k=1 a b
    while [ "$k" -le "$nanch" ]; do
        a=$(md5sum "build/conformance-out-$k.yuv" 2>/dev/null | cut -d' ' -f1)
        b=$(md5sum "$d/ref_$((k - 1)).yuv" 2>/dev/null | cut -d' ' -f1)
        if [ -n "$a" ] && [ "$a" = "$b" ]; then line="$line a$k=OK"; pass=$((pass+1))
        else line="$line a$k=REGRESSED"; fail=$((fail+1)); fi
        k=$((k+1))
    done
    local off=0 L=1 cnt
    for cnt in $(awk '/^Frame/ { if (n) print n; n = 0; next } { n++ } END { if (n) print n }' "$d/tiles.txt"); do
        k=$((nanch + 1 + L))
        a=$(md5sum "build/conformance-out-$k.yuv" 2>/dev/null | cut -d' ' -f1)
        b=$(dd if="$d/ref1d.yuv" bs=6144 skip="$off" count="$cnt" status=none | md5sum | cut -d' ' -f1)
        if [ -n "$a" ] && [ "$a" = "$b" ]; then line="$line l$L=OK($cnt)"; pass=$((pass+1))
        else line="$line l$L=REGRESSED($cnt)"; fail=$((fail+1)); fi
        off=$((off + cnt)); L=$((L + 1))
    done
    echo "$line"
}
echo "--- large scale tile (7.3: anchors, the camera header, tile list OBUs; every anchor and list hard) ---"
lst_seed=1
for c in $LST_CASES; do lstcase "$c" "$lst_seed"; lst_seed=$((lst_seed + 1)); done
SVC_ENC="ref/aom-build/examples/svc_encoder_rtc"
# drishti at operating point op vs aomdec --oppoint (one file per output frame, named by the unit it came from), dav1d
# --oppoint --alllayers all agreeing with aomdec. Appends "opN:" and one oK=OK per frame to svc_line.
svc_judge() { # ivf op all tag
    local ivf="$1" op="$2" all="$3" tag="$4" r k u a b
    if ! run_drishti_op "$ivf" "$op" "$WORK/$tag.log"; then
        svc_line="$svc_line op$op=SETUP-FAILED(copy)"; fail=$((fail+1)); return
    fi
    rm -f "${WORK:?}/$tag.ref-"*.yuv "${WORK:?}/$tag.ref" "${WORK:?}/$tag.dav1d.yuv"
    aomdec --rawvideo --oppoint="$op" -o "$WORK/$tag.ref-%6.yuv" "$ivf" 2>/dev/null
    local refs=() ; mapfile -t refs < <(find "$WORK" -maxdepth 1 -name "$tag.ref-*.yuv" | sort)
    if [ "${#refs[@]}" -lt 1 ]; then
        svc_line="$svc_line op$op=SETUP-FAILED(no aomdec output)"; fail=$((fail+1)); return
    fi
    cat "${refs[@]}" > "$WORK/$tag.ref"
    if command -v dav1d >/dev/null 2>&1; then
        dav1d -q --oppoint "$op" --alllayers "$all" -i "$ivf" -o "$WORK/$tag.dav1d.yuv" >/dev/null 2>&1
        if ! cmp -s "$WORK/$tag.ref" "$WORK/$tag.dav1d.yuv"; then
            svc_line="$svc_line op$op=SETUP-FAILED(dav1d disagrees with aomdec)"; fail=$((fail+1)); return
        fi
    fi
    svc_line="$svc_line op$op:"
    local nu; nu=$(grep -c '^frame [0-9]' "$WORK/$tag.log")
    declare -A want=()
    for r in "${refs[@]}"; do u="${r##*.ref-}"; u=$((10#${u%.yuv})); want[$u]="$r"; done
    k=1
    while [ "$k" -le "$nu" ]; do
        a=$(md5sum "build/conformance-out-$k.yuv" 2>/dev/null | cut -d' ' -f1)
        if [ -z "${want[$k]:-}" ]; then
            if [ -n "$a" ]; then svc_line="$svc_line u$k=REGRESSED(output)"; fail=$((fail+1)); fi
        else
            b=$(md5sum "${want[$k]}" | cut -d' ' -f1)
            if [ -n "$a" ] && [ "$a" = "$b" ]; then svc_line="$svc_line u$k=OK"; pass=$((pass+1))
            else svc_line="$svc_line u$k=REGRESSED"; fail=$((fail+1)); fi
        fi
        k=$((k+1))
    done
    for u in "${!want[@]}"; do
        if [ "$u" -gt "$nu" ]; then svc_line="$svc_line u$u=REGRESSED(missing)"; fail=$((fail+1)); fi
    done
    rm -f "${WORK:?}/$tag.ref-"*.yuv
}
# the operating_point_idc list, and "ok" when every frame OBU of the stream carries an extension header (want_ext
# 1), its layers are exactly sl spatial x tl temporal (0 = do not check), and every operating point but the first
# leaves a present layer out; else the reason
svc_property() { # want_ext sl tl
    ./build/drishti-vector-probe 2>&1 | awk -v want_ext="$1" -v sl="$2" -v tl="$3" '
        /operating_point_idc=/ { split($0, a, "="); n = split(a[2], idc, ","); list = a[2] }
        / OBU type=(3|4|6) / {
            split($0, f, " "); for (i in f) { split(f[i], kv, "="); v[kv[1]] = kv[2] + 0 }
            if (v["ext"] == 1) {
                L[v["tid"] "," v["sid"]] = 1
                if (v["tid"] > mt) mt = v["tid"]
                if (v["sid"] > ms) ms = v["sid"]
            } else noext++
        }
        END {
            why = ""
            if (n < 2) why = why " operating_points_cnt_minus_1=" (n - 1)
            if (want_ext && noext) why = why " " noext "-frame-OBUs-without-extension"
            if (sl && (ms + 1 != sl || mt + 1 != tl)) why = why " layers=" (ms + 1) "x" (mt + 1)
            for (i = 2; i <= n; i++) {
                d = 0   # bit k of x is int(x / 2^k) % 2 (no gawk-only and() / rshift())
                for (l in L) {
                    split(l, ts, ",")
                    if (int(idc[i] / 2 ^ ts[1]) % 2 == 0 || int(idc[i] / 2 ^ (ts[2] + 8)) % 2 == 0) d = 1
                }
                if (!d) why = why " op" (i - 1) "-drops-nothing"
            }
            print "operating_point_idc=" list " " (why == "" ? "ok" : "BAD" why)
        }'
}
# the payload bytes of build/conformance-input.ivf, summed over its IVF frames (the probe's per-unit sizes)
svc_payload_bytes() {
    ./build/drishti-vector-probe 2>&1 | sed -n 's/^=== temporal unit [0-9]* (\([0-9]*\) bytes) ===$/\1/p' |
        awk '{ s += $1 } END { print s + 0 }'
}
svccase() { # name = svcLM[bD]_WxH
    local n="$1" lmx geo
    IFS=_ read -r lmx geo <<< "$n"
    local w="${geo%x*}" h="${geo#*x}" lm="${lmx#svc}" bd=8 sl tl pix=yuv420p
    case "$lm" in *b*) bd="${lm#*b}"; lm="${lm%b*}" ;; esac
    case "$lm" in 1) sl=1 tl=2 ;; 2) sl=1 tl=3 ;; 5) sl=2 tl=1 ;; 6) sl=3 tl=1 ;; 7) sl=2 tl=3 ;; 8) sl=3 tl=3 ;;
        *) echo "  $n: SETUP FAILED (layering mode $lm unknown)"; fail=$((fail+1)); return ;; esac
    [ "$bd" = "10" ] && pix=yuv420p10le
    if [ ! -x "$SVC_ENC" ]; then skip_case "$n" "$SVC_ENC not built"; return; fi
    # spatial layer s takes (s + 1) shares of 800 kbps (the last absorbs the rounding), its temporal layers cumulative
    # fractions of that: svc_encoder_rtc requires the spatial layers' top temporal rates to sum to the target
    local br; br=$(awk -v sl="$sl" -v tl="$tl" 'BEGIN { used = 0; out = ""
        for (s = 0; s < sl; s++) {
            top = (s == sl - 1) ? 800 - used : int(800 * (s + 1) / (sl * (sl + 1) / 2)); used += top
            for (t = 0; t < tl; t++) out = out (out == "" ? "" : ",") ((t == tl - 1) ? top : int(top * (t + 1) / tl))
        }
        print out }')
    ffmpeg -loglevel error -y -f lavfi -i "mandelbrot=size=${w}x${h}:rate=30:start_scale=3:end_scale=0.3" \
        -frames:v 12 -pix_fmt "$pix" -strict -1 "$WORK/$n.y4m" 2>/dev/null || {
        echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
    "$SVC_ENC" -k 10000 --width="$w" --height="$h" -lm "$lm" --speed=7 --target-bitrate=800 --bitrates="$br" \
        --spatial-layers="$sl" --temporal-layers="$tl" --timebase=1/30 -d "$bd" "$WORK/$n.y4m" -o "$WORK/$n.ivf" \
        >/dev/null 2>&1
    if [ ! -s "$WORK/$n.ivf" ]; then echo "  $n: SETUP FAILED (svc_encoder_rtc)"; fail=$((fail+1)); return; fi
    ffmpeg -loglevel error -y -i "$WORK/$n.ivf" -c copy -bsf:v av1_frame_merge -f ivf "$WORK/$n.tu.ivf" 2>/dev/null || {
        echo "  $n: SETUP FAILED (av1_frame_merge)"; fail=$((fail+1)); return; }
    # the merge must only regroup: as many units as temporal delimiters, and the payload bytes unchanged
    local pw pm um tdm
    cp "$WORK/$n.ivf" build/conformance-input.ivf
    pw=$(svc_payload_bytes)
    cp "$WORK/$n.tu.ivf" build/conformance-input.ivf
    local prop; prop=$(svc_property 1 "$sl" "$tl")
    pm=$(svc_payload_bytes)
    um=$(./build/drishti-vector-probe 2>&1 | grep -c '^=== temporal unit')
    tdm=$(./build/drishti-vector-probe 2>&1 | grep -c ' OBU type=2 ')
    if [ "$pw" != "$pm" ] || [ "$um" != "$tdm" ] || [ "$um" != "12" ]; then
        echo "  $n: SETUP FAILED (the merge changed the stream: payload $pw -> $pm bytes, $um units, $tdm delimiters)"
        fail=$((fail+1)); return
    fi
    case "$prop" in
        *" ok") ;;
        *) echo "  $n: SETUP FAILED (property: $prop — the case would prove nothing)"; fail=$((fail+1)); return ;;
    esac
    local nops op; nops=$(sed -n 's/^operating_point_idc=\([0-9,]*\) .*/\1/p' <<< "$prop" | tr ',' '\n' | grep -c .)
    svc_line="  $n ($prop) merged:"
    op=0; while [ "$op" -lt "$nops" ]; do svc_judge "$WORK/$n.tu.ivf" "$op" 0 "$n.tu"; op=$((op+1)); done
    svc_line="$svc_line | as-written:"
    op=0; while [ "$op" -lt "$nops" ]; do svc_judge "$WORK/$n.ivf" "$op" 1 "$n.lp"; op=$((op+1)); done
    echo "$svc_line"
}
echo "--- scalability (5.3.1 drop_obu at every operating point; merged units and layer packets; every frame hard) ---"
for c in $SVC_CASES; do svccase "$c"; done
for c in $SVC_PUBLISHED_OPS; do
    v="${c%%:*}" last="${c##*:}"
    if ! fetch_vec "$v"; then skip_case "$v-ops" "vector fetch failed"; continue; fi
    cp "$VDIR/$v.ivf" build/conformance-input.ivf
    prop=$(svc_property 0 0 0)
    case "$prop" in *" ok") ;; *) echo "  $v-ops: SETUP FAILED (property: $prop)"; fail=$((fail+1)); continue ;; esac
    svc_line="  $v-ops ($prop):"
    op=1; while [ "$op" -le "$last" ]; do svc_judge "$VDIR/$v.ivf" "$op" 0 "$v.ops"; op=$((op+1)); done
    echo "$svc_line"
done
# does the probe show `want` — "ctxtile" (an adapting frame saving a tile other than 0) or "fp" (an adapting frame
# with disable_frame_end_update_cdf 1) — AND a later frame inheriting CDFs (primary_ref_frame != 7)?
cdf_property() { # want
    ./build/drishti-vector-probe 2>&1 | awk -v want="$1" '
        function judge() {
            if (seen && !se) {
                if (want == "ctxtile" && dcu == 0 && dfe == 0 && cut != 0) { got = 1 }
                if (want == "fp" && dcu == 0 && dfe == 1) { got = 1 }
                if (got && pr != 7 && ft != 0 && saw_inherit_after) { inh = 1 }
                if (got) { saw_inherit_after = 1 }
            }
        }
        /^ *frame_type=/ { judge(); seen = 1; split($0, a, "="); ft = a[2] + 0; se = 0; pr = 7; dcu = 1; dfe = 1; cut = 0 }
        /^ *show_existing_frame=/ { split($0, a, "="); se = a[2] + 0 }
        /^ *primary_ref_frame=/ { split($0, a, "="); pr = a[2] + 0 }
        /^ *disable_cdf_update=/ { split($0, a, "="); dcu = a[2] + 0 }
        /^ *disable_frame_end_update_cdf=/ { split($0, a, "="); dfe = a[2] + 0 }
        /^ *context_update_tile_id=/ { split($0, a, "="); cut = a[2] + 0 }
        END { judge(); exit !(got && inh) }'
}
cdfcase() { # name = KIND_WxH
    local n="$1" kind geo
    IFS=_ read -r kind geo <<< "$n"
    local w="${geo%x*}" h="${geo#*x}" fr=9 want="ctxtile" srcf="" args=""
    case "$kind" in
        mt2c)      args="--tile-columns=1" ;;
        mt2x2)     args="--tile-columns=1 --tile-rows=1"; srcf=",noise=alls=12:allf=t" ;;
        mt2csb128) args="--tile-columns=1 --sb-size=128"; srcf=",noise=alls=12:allf=t" ;;
        mt4crt)    args="--tile-columns=2 --rt --cpu-used=9 --end-usage=cbr --target-bitrate=500"
                   srcf=",noise=alls=12:allf=t" ;;
        fp)        args="--frame-parallel=1"; want="fp" ;;
        fp2c)      args="--frame-parallel=1 --tile-columns=1"; want="fp" ;;
        *)         echo "  $n: SETUP FAILED (unknown case kind)"; fail=$((fail+1)); return ;;
    esac
    rm -f "${WORK:?}/$n.ivf" "${WORK:?}/$n.ref" "${WORK:?}/$n.yuv" "${WORK:?}/$n.dav1d.yuv"
    # 640x360 mandelbrot trips libaom's screen-content detector (palette / intrabc, rejected by design); a
    # little temporal noise keeps it natural content.
    ffmpeg -loglevel error -y -f lavfi -i "mandelbrot=size=${w}x${h}:rate=30${srcf}" -frames:v "$fr" \
        -pix_fmt yuv420p -f rawvideo "$WORK/$n.yuv" 2>/dev/null || {
        echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
    # shellcheck disable=SC2086
    aomenc --codec=av1 -w $w -h $h --i420 --cpu-used=8 --end-usage=q --cq-level=30 --limit="$fr" \
        --lag-in-frames=0 --enable-restoration=0 --enable-palette=0 --enable-intrabc=0 $args \
        --ivf -o "$WORK/$n.ivf" "$WORK/$n.yuv" 2>/dev/null
    [ -s "$WORK/$n.ivf" ] || { echo "  $n: SETUP FAILED (aomenc produced no stream)"; fail=$((fail+1)); return; }
    rm -f build/conformance-input.ivf
    cp "$WORK/$n.ivf" build/conformance-input.ivf || { echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    if ! cdf_property "$want"; then
        echo "  $n: SETUP FAILED (no '$want' CDF save followed by an inheriting frame — the case would prove nothing)"
        fail=$((fail+1)); return
    fi
    seg_judge "$n" "$w" "$h" "$fr"
}
echo "--- cross-frame CDF save: the context tile, and the initial context (frame-parallel); every frame hard ---"
for c in $CDF_CASES; do cdfcase "$c"; done
palcase() { # name = KIND_WxH (6 frames)
    local n="$1" kind geo
    IFS=_ read -r kind geo <<< "$n"
    local w="${geo%x*}" h="${geo#*x}" fr=6 src="mandelbrot" args=""
    case "$kind" in
        palstock)  ;;   # NOTHING added: the encode a user gets by default
        palscreen) src="testsrc2"; args="--tune-content=screen --enable-intrabc=0" ;;
        palbars)   src="smptehdbars"; args="--tune-content=screen --enable-intrabc=0" ;;
        *)         echo "  $n: SETUP FAILED (unknown case kind)"; fail=$((fail+1)); return ;;
    esac
    rm -f "${WORK:?}/$n.ivf" "${WORK:?}/$n.ref" "${WORK:?}/$n.yuv" "${WORK:?}/$n.dav1d.yuv"
    ffmpeg -loglevel error -y -f lavfi -i "${src}=size=${w}x${h}:rate=30" -frames:v "$fr" \
        -pix_fmt yuv420p -f rawvideo "$WORK/$n.yuv" 2>/dev/null || {
        echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
    # shellcheck disable=SC2086
    aomenc --codec=av1 -w $w -h $h --i420 --cpu-used=8 --end-usage=q --cq-level=30 --limit="$fr" $args \
        --ivf -o "$WORK/$n.ivf" "$WORK/$n.yuv" 2>/dev/null
    [ -s "$WORK/$n.ivf" ] || { echo "  $n: SETUP FAILED (aomenc produced no stream)"; fail=$((fail+1)); return; }
    rm -f build/conformance-input.ivf
    cp "$WORK/$n.ivf" build/conformance-input.ivf || { echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    local probe; probe=$(./build/drishti-vector-probe 2>&1)
    if ! echo "$probe" | grep -q 'allow_screen_content_tools=1'; then
        echo "  $n: SETUP FAILED (no frame allows screen-content tools — the case would prove nothing)"
        fail=$((fail+1)); return
    fi
    if echo "$probe" | grep -q 'allow_intrabc=1'; then
        echo "  $n: SETUP FAILED (a frame uses intrabc — roadmap 0.8.4, not this case)"; fail=$((fail+1)); return
    fi
    seg_judge "$n" "$w" "$h" "$fr"
}
echo "--- palette (allow_screen_content_tools; the stock default encode first); every frame hard ---"
for c in $PAL_CASES; do palcase "$c"; done
echo "--- other encoders: rav1e (inherited features) and SVT-AV1 (variance AQ); every frame hard ---"
for c in $RAV1E_CASES; do rav1ecase "$c"; done
for c in $SVT_CASES; do svtcase "$c"; done
# open GOP: the stream must code >= 2 INTRA_ONLY frames and show >= 1 of them through show_existing_frame.
svtopencase() { # name = svtopen_WxH (60 frames, keyint 16)
    local n="$1" geo
    IFS=_ read -r _ geo <<< "$n"
    local w="${geo%x*}" h="${geo#*x}" fr=60
    if ! command -v SvtAv1EncApp >/dev/null 2>&1; then skip_case "$n" "SvtAv1EncApp not on PATH"; return; fi
    rm -f "${WORK:?}/$n.ivf" "${WORK:?}/$n.yuv"
    ffmpeg -loglevel error -y -f lavfi -i "mandelbrot=size=${w}x${h}:rate=30,noise=alls=6:allf=t" -frames:v "$fr" \
        -pix_fmt yuv420p -f rawvideo "$WORK/$n.yuv" 2>/dev/null || {
        echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
    SvtAv1EncApp -i "$WORK/$n.yuv" -w "$w" -h "$h" --fps-num 30 --fps-denom 1 -n "$fr" --preset 8 \
        --irefresh-type 1 --keyint 16 --crf 35 -b "$WORK/$n.ivf" >/dev/null 2>&1
    [ -s "$WORK/$n.ivf" ] || { echo "  $n: SETUP FAILED (SVT-AV1 produced no stream)"; fail=$((fail+1)); return; }
    rm -f build/conformance-input.ivf
    cp "$WORK/$n.ivf" build/conformance-input.ivf || { echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    local prop
    if ! prop=$(./build/drishti-vector-probe 2>&1 | awk '
        /^ *frame_type=/ { split($0, a, "="); ft = a[2] + 0 }
        /^ *show_existing_frame=/ { split($0, a, "="); if (ft == 2) { if (a[2] + 0) nse++; else nio++ } }
        END { printf "intra_only=%d shown_existing=%d", nio, nse; exit !(nio >= 2 && nse >= 1) }'); then
        echo "  $n: SETUP FAILED (no shown intra-only frames: $prop — the case would prove nothing)"
        fail=$((fail+1)); return
    fi
    echo "  $n ($prop)"
    vs_judge "$n" "$fr"
}
for c in $SVTOPEN_CASES; do svtopencase "$c"; done

echo "--- odd-MI inter frames (edge blocks past the MI grid; superblock-grid allocation); every frame hard ---"
for c in $ODDMII_CASES; do oddmiicase "$c"; done

echo "--- superres (7.16 upscaling with overhang columns; tiles, 128-SB, LR, resize); every frame hard ---"
for c in $SR_CASES; do srcase "$c"; done
# superres frames whose width the floor decides: "floored=N" counts superres frames whose FrameWidth exceeds the bare
# 5.9.8 formula, "equal=N" those whose FrameWidth equals UpscaledWidth. Prints both; fails (exit 1) unless floored
# reaches min_floored and, with want "eq", equal reaches 2 — or, without it, no frame is equal (they are scaled).
srmin_property() { # want min_floored
    ./build/drishti-vector-probe 2>&1 | awk -v want="$1" -v minf="$2" '
        /^  frame_width=/ { split($0, a, "="); fw = a[2] + 0 }
        /^  upscaled_width=/ { split($0, a, "="); uw = a[2] + 0 }
        /^  superres_denom=/ { split($0, a, "="); d = a[2] + 0
            if (d > 8) { if (fw == uw) eq++; if (fw > int((uw * 8 + int(d / 2)) / d)) fl++ } }
        END {
            printf "floored=%d equal=%d", fl, eq
            if (fl < minf) exit 1
            if (want == "eq" && eq < 2) exit 1
            if (want != "eq" && eq > 0) exit 1
        }'
}
srmincase() { # name = srmin_WxH[_dD][_b10][_eq|_rand]
    local n="$1" geo rest
    geo="${n#srmin_}"; geo="${geo%%_*}"; rest="${n#srmin_"$geo"}"
    local w="${geo%x*}" h="${geo#*x}" d=16 bd=8 want="floor" mode=1 minf=2 pix=yuv420p fr=8 t
    for t in ${rest//_/ }; do
        case "$t" in
            d[0-9]*) d="${t#d}" ;;
            b10) bd=10; pix=yuv420p10le ;;
            eq) want="eq" ;;
            rand) mode=2; minf=1 ;;
            *) echo "  $n: SETUP FAILED (unknown case token $t)"; fail=$((fail+1)); return ;;
        esac
    done
    local den=(--superres-denominator="$d" --superres-kf-denominator="$d")
    [ "$mode" = "2" ] && den=()
    rm -f "${WORK:?}/$n.ivf" "${WORK:?}/$n.y4m"
    ffmpeg -loglevel error -y -f lavfi -i "mandelbrot=size=${w}x${h}:rate=25" -frames:v "$fr" -pix_fmt "$pix" \
        -strict -1 "$WORK/$n.y4m" 2>/dev/null || { echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
    aomenc --quiet --limit="$fr" --bit-depth="$bd" --superres-mode="$mode" "${den[@]}" --lag-in-frames=0 \
        -o "$WORK/$n.ivf" "$WORK/$n.y4m" >/dev/null 2>&1
    [ -s "$WORK/$n.ivf" ] || { echo "  $n: SETUP FAILED (aomenc produced no stream)"; fail=$((fail+1)); return; }
    rm -f build/conformance-input.ivf
    cp "$WORK/$n.ivf" build/conformance-input.ivf || { echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    local prop
    if ! prop=$(srmin_property "$want" "$minf"); then
        echo "  $n: SETUP FAILED (property: $prop — the case would prove nothing)"; fail=$((fail+1)); return
    fi
    echo "  $n ($prop)"
    # dav1d 1.5.4 decodes NOTHING of an _eq stream ("Cannot allocate memory", the keyframe included), although its
    # src/obu.c applies the same floor and its src/decode.c the same width test; aomdec is the only reference there.
    if [ "$want" = "eq" ]; then vs_judge "$n" "$fr" nodav1d; else vs_judge "$n" "$fr"; fi
}
echo "--- superres at small widths (5.9.8 + Annex A: FrameWidth >= Min(16, UpscaledWidth); every frame hard) ---"
for c in $SRMIN_CASES; do srmincase "$c"; done

echo "--- chroma formats: monochrome, 4:4:4, 4:2:2 (palettes, LR, superres, 128-SB, odd MI); every frame hard ---"
for c in $FMT_CASES; do fmtcase "$c"; done

echo "--- dimension sweep: 1x1 .. 257x31, both superblock sizes; every frame hard ---"
for c in $DIM_CASES; do dimcase "$c"; done
echo "--- scaled references (resize): every denominator class, 2x both ways, random sizes; every frame hard ---"
for c in $RS_CASES; do rscase "$c"; done

echo "--- high bit depth: 10-bit and 12-bit, every format and the format-sensitive tools; every frame hard ---"
for c in $BD_CASES; do bdcase "$c"; done

echo "--- long GOPs: hidden frames, show_existing, every refresh slot, switch frames; every frame hard ---"
for c in $GOP_CASES; do gopcase "$c"; done

echo "--- published libaom vectors: the full test_vectors.cc corpus (every frame, and no frame more) ---"
npub=$(printf '%s\n' $PUBLISHED | grep -c .)
if [ "$npub" -ne "$PUBLISHED_COUNT" ]; then
    echo "  harness: PUBLISHED lists $npub vectors, not $PUBLISHED_COUNT"; fail=$((fail+1))
fi
for v in $PUBLISHED; do check_published "$v"; done
for v in $PUBLISHED_MKV; do
    if fetch_mkv "$v"; then check_published "$v"; else skip_case "$v" "vector fetch/remux failed"; fi
done

# A libaom test-data file into $VDIR/invalid (via a .part name, as fetch_vec) -> 0 if available.
fetch_invalid() { # file
    local d="$VDIR/invalid"
    mkdir -p "$d"
    [ -s "$d/$1" ] && return 0
    if curl -sf --max-time 60 -o "${d:?}/${1:?}.part" "$AOM_BASE/$1"; then mv -f "${d:?}/${1:?}.part" "${d:?}/${1:?}"
    else rm -f "${d:?}/${1:?}.part"; return 1; fi
}
# One invalid stream. libaom's test reads it through IVFVideoSource, which ignores EVERY IVF header field; the real
# aomdec and dav1d applications (and drishti's IVF reader) refuse most of these files at the container, on a fuzzed
# fourcc, version or header size. To fuzz the DECODER the way libaom's test does, the stream runs from a copy with
# version 0, header size 32 and fourcc AV01. Checked, per input unit:
#  - drishti-conformance exits by itself within 60 s: no crash, no hang, no runaway allocation;
#  - drishti shows exactly what aomdec --keep-going shows for that unit (libaom's test also decodes on past an
#    error): the same frame, or nothing. A refused unit and a unit that shows no frame are the same here: drishti
#    latches its first error, libaom recovers, and no unit in the corpus has libaom SHOW a frame after its error;
#  - aomdec itself agrees with libaom's published .res: a unit .res says fails must show nothing (else the reference
#    is not libaom's and the case is a setup failure).
invcase() { # name[:res-suffix]
    local n="${1%%:*}" rs="res" d="$VDIR/invalid"
    case "$1" in *:*) rs="${1##*:}" ;; esac
    if ! fetch_invalid "$n.ivf" || ! fetch_invalid "$n.ivf.$rs"; then skip_case "$n" "fetch failed"; return; fi
    local w="$WORK/$n.d" rc nu k u r a b want
    rm -rf "${w:?}"; mkdir -p "$w"
    cp "$d/$n.ivf" "$w/in.ivf"
    printf '\000\000\040\000AV01' | dd of="$w/in.ivf" bs=1 seek=4 conv=notrunc status=none
    rm -f build/conformance-input.ivf build/conformance-input.lst build/conformance-input.op build/conformance-out-*.yuv
    cp "$w/in.ivf" build/conformance-input.ivf
    timeout 60 ./build/drishti-conformance > "$w/drishti.log" 2>&1
    rc=$?
    if [ "$rc" -gt 1 ]; then
        echo "  $n: REGRESSED (drishti-conformance exit $rc: a crash, signal or timeout)"; fail=$((fail+1)); return
    fi
    timeout 60 aomdec --rawvideo --keep-going -o "$w/ref-%6.yuv" "$w/in.ivf" > /dev/null 2>&1
    local res=(); mapfile -t res < <(tr -s ' \n' '\n' < "$d/$n.ivf.$rs" | grep .)
    nu=$(grep -c '^frame [0-9]' "$w/drishti.log")
    if [ "$nu" -ne "${#res[@]}" ]; then
        echo "  $n: REGRESSED (drishti walked $nu units; libaom's .$rs lists ${#res[@]})"; fail=$((fail+1)); return
    fi
    local line="  $n:" ref_dav1d=0
    case " $INVALID_DAV1D_REF " in *" $n "*) ref_dav1d=1 ;; esac
    if [ "$ref_dav1d" = "1" ]; then
        if ! command -v dav1d >/dev/null 2>&1; then
            skip_case "$n" "dav1d is its reference and is not on PATH"; return
        fi
        dav1d -q -i "$w/in.ivf" -o "$w/dav1d.yuv" > /dev/null 2>&1
        cat build/conformance-out-*.yuv > "$w/drishti.yuv" 2>/dev/null
        if [ -s "$w/dav1d.yuv" ] && cmp -s "$w/drishti.yuv" "$w/dav1d.yuv"; then
            echo "$line every unit = dav1d (libaom refuses this stream; see INVALID_DAV1D_REF)"; pass=$((pass+nu))
        else
            echo "$line REGRESSED (not dav1d's output)"; fail=$((fail+1))
        fi
        return
    fi
    k=1
    while [ "$k" -le "$nu" ]; do
        u=$(printf '%06d' "$k") r="${res[$((k-1))]}"
        a=-; [ -f "$w/ref-$u.yuv" ] && a=$(md5sum < "$w/ref-$u.yuv" | cut -d' ' -f1)
        b=-; [ -f "build/conformance-out-$k.yuv" ] && b=$(md5sum < "build/conformance-out-$k.yuv" | cut -d' ' -f1)
        if [ "$r" != "0" ] && [ "$r" != "-1" ] && [ "$a" != "-" ]; then
            echo "  $n: SETUP FAILED (aomdec shows a frame for unit $k, which libaom's .$rs says fails with $r)"
            fail=$((fail+1)); return
        fi
        want=ok; [ "$a" != "$b" ] && want=diff
        case " $INVALID_XFAIL_UNITS " in
            *" $n:$k "*)
                if [ "$want" = "ok" ]; then line="$line u$k=MATCHES(remove-from-INVALID_XFAIL_UNITS)"; fail=$((fail+1))
                else line="$line u$k=known-gap"; xfail=$((xfail+1)); fi ;;
            *)
                if [ "$want" = "ok" ]; then line="$line u$k=OK"; pass=$((pass+1))
                else line="$line u$k=REGRESSED"; fail=$((fail+1)); fi ;;
        esac
        k=$((k+1))
    done
    echo "$line"
}
echo "--- invalid streams: libaom's fuzz/crash corpus, decoded as its test does (no crash; per unit = libaom) ---"
for c in $INVALID_CASES; do invcase "$c"; done

finish
