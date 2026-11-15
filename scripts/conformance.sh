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
# QUANTIZER MATRICES (0.8.2): qm15 signals matrices at the flat level 15 (must decode bit-exact: no matrix
# applies); qmon uses libaom's default levels, which drishti does not implement — it must REJECT, never
# mis-decode (each rejected frame is a known gap until roadmap 0.8.4).
QM_CASES="qm15_176x144 qmon_176x144"
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
PUBLISHED="av1-1-b8-01-size-16x16 av1-1-b8-01-size-32x32 av1-1-b8-01-size-64x64 \
av1-1-b8-00-quantizer-32 av1-1-b8-04-cdfupdate av1-1-b8-05-mv \
av1-1-b8-00-quantizer-00 av1-1-b8-06-mfmv av1-1-b8-24-monochrome av1-1-b8-02-allintra"
# CHROMA FORMATS (0.8.3), kind_WxH, every frame hard: monochrome, 4:4:4 (profile 1) and 4:2:2 (profile 2), over
# GOPs, realtime, screen content (chroma palettes), superres + loop restoration, 128-SB and an odd-MI geometry. Each
# stream PROVES its format through vector-probe (num_planes / subsampling), and the restoration cases prove a
# CHROMA plane was restored (lr_type_u/v), not just luma. 4:2:0 is covered by every other section.
FMT_CASES="fmtmono_176x144 fmt444_176x144 fmt422_176x144 fmtmonort_176x144 fmt444rt_176x144 fmt422rt_176x144 \
fmt444scr_320x240 fmt422scr_320x240 fmtmonosr_352x288 fmt444sr_352x288 fmt422sr_352x288 fmt444sb128_352x288 \
fmt422oddmi_136x136"

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
    for c in $CDF_CASES; do skip_case "$c" "$1"; done
    for c in $PAL_CASES; do skip_case "$c" "$1"; done
    for c in $RAV1E_CASES; do skip_case "$c" "$1"; done
    for c in $SVT_CASES; do skip_case "$c" "$1"; done
    for c in $GOP_CASES; do skip_case "$c" "$1"; done
    for c in $SR_CASES; do skip_case "$c" "$1"; done
    for c in $FMT_CASES; do skip_case "$c" "$1"; done
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
    rm -f build/conformance-input.ivf build/conformance-out-*.yuv
    cp "$1" build/conformance-input.ivf 2>/dev/null || return 1
    ./build/drishti-conformance >"$2" 2>&1
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
repro_seq  fmt-mono-72x56 8 8
repro_seq  fmt-444-72x56 8 8
repro_seq  fmt-422-72x56 8 8

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
# scored, not just the keyframe; the full published corpus is roadmap.md 0.8.5.
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
vs_judge() { # n fr — decode, per-frame reference, dav1d guard, per-frame compare (every frame hard)
    local n="$1" fr="$2"
    run_drishti "$WORK/$n.ivf" "$WORK/$n.log" || { echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    rm -f "${WORK:?}/$n.ref-"* "${WORK:?}/$n.ref" "${WORK:?}/$n.dav1d.yuv"
    aomdec --rawvideo -o "$WORK/$n.ref-%6.yuv" "$WORK/$n.ivf" 2>/dev/null
    local nref; nref=$(find "$WORK" -maxdepth 1 -name "$n.ref-*.yuv" | wc -l)
    if [ "$nref" -ne "$fr" ]; then
        echo "  $n: SETUP FAILED (aomdec wrote $nref frame(s), not $fr)"; fail=$((fail+1)); return
    fi
    if command -v dav1d >/dev/null 2>&1; then
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
qmcase() { # name = qm15_WxH (hard) | qmon_WxH (must reject); 4 frames
    local n="$1" kind geo
    IFS=_ read -r kind geo <<< "$n"
    local w="${geo%x*}" h="${geo#*x}" fr=4 qmargs="--enable-qm=1"
    [ "$kind" = "qm15" ] && qmargs="--enable-qm=1 --qm-min=15 --qm-max=15"
    rm -f "${WORK:?}/$n.ivf" "${WORK:?}/$n.ref" "${WORK:?}/$n.yuv" "${WORK:?}/$n.dav1d.yuv"
    ffmpeg -loglevel error -y -f lavfi -i "mandelbrot=size=${w}x${h}:rate=30" -frames:v "$fr" \
        -pix_fmt yuv420p -f rawvideo "$WORK/$n.yuv" 2>/dev/null || {
        echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
    # shellcheck disable=SC2086
    aomenc --codec=av1 -w $w -h $h --i420 --cpu-used=8 --end-usage=q --cq-level=30 --limit="$fr" \
        --lag-in-frames=0 --enable-restoration=0 --enable-palette=0 --enable-intrabc=0 $qmargs \
        --ivf -o "$WORK/$n.ivf" "$WORK/$n.yuv" 2>/dev/null
    [ -s "$WORK/$n.ivf" ] || { echo "  $n: SETUP FAILED (aomenc produced no stream)"; fail=$((fail+1)); return; }
    rm -f build/conformance-input.ivf
    cp "$WORK/$n.ivf" build/conformance-input.ivf || { echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    local probe; probe=$(./build/drishti-vector-probe 2>&1)
    if ! echo "$probe" | grep -q 'using_qmatrix=1'; then
        echo "  $n: SETUP FAILED (no frame signals using_qmatrix — the case would prove nothing)"; fail=$((fail+1)); return
    fi
    if [ "$kind" = "qm15" ] && echo "$probe" | grep -q 'qmatrix_applies=1'; then
        echo "  $n: SETUP FAILED (a frame applies a matrix — not the flat-level case)"; fail=$((fail+1)); return
    fi
    if [ "$kind" = "qmon" ] && ! echo "$probe" | grep -q 'qmatrix_applies=1'; then
        echo "  $n: SETUP FAILED (no frame applies a matrix — the reject would prove nothing)"; fail=$((fail+1)); return
    fi
    if [ "$kind" = "qm15" ]; then seg_judge "$n" "$w" "$h" "$fr"; return; fi
    run_drishti "$WORK/$n.ivf" "$WORK/$n.log" || { echo "  $n: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    aomdec --rawvideo -o "$WORK/$n.ref" "$WORK/$n.ivf" 2>/dev/null
    local fs=$(( (w * h) + (2 * ((w + 1) / 2) * ((h + 1) / 2)) ))
    local line="  $n:" k=1
    while [ "$k" -le "$fr" ]; do
        local a b
        a=$(md5sum "build/conformance-out-$k.yuv" 2>/dev/null | cut -d' ' -f1)
        b=$(dd if="$WORK/$n.ref" bs="$fs" skip=$((k-1)) count=1 status=none | md5sum | cut -d' ' -f1)
        if [ -z "$a" ] && grep -q "frame $k DECODE-FAILED err=7" "$WORK/$n.log"; then
            line="$line f$k=rejected(known-gap)"; xfail=$((xfail+1))
        elif [ -n "$a" ] && [ "$a" = "$b" ]; then
            line="$line f$k=DECODES(promote-to-hard)"; fail=$((fail+1))
        else
            line="$line f$k=REGRESSED(mis-decode)"; fail=$((fail+1))
        fi
        k=$((k+1))
    done
    echo "$line"
}
echo "--- quantizer matrices: the flat level decodes, a real matrix is REJECTED (never mis-decoded) ---"
for c in $QM_CASES; do qmcase "$c"; done
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

echo "--- odd-MI inter frames (edge blocks past the MI grid; superblock-grid allocation); every frame hard ---"
for c in $ODDMII_CASES; do oddmiicase "$c"; done

echo "--- superres (7.16 upscaling with overhang columns; tiles, 128-SB, LR, resize); every frame hard ---"
for c in $SR_CASES; do srcase "$c"; done

echo "--- chroma formats: monochrome, 4:4:4, 4:2:2 (palettes, LR, superres, 128-SB, odd MI); every frame hard ---"
for c in $FMT_CASES; do fmtcase "$c"; done

echo "--- long GOPs: hidden frames, show_existing, every refresh slot, switch frames; every frame hard ---"
for c in $GOP_CASES; do gopcase "$c"; done

echo "--- published libaom vectors (128x128 superblocks; every frame) ---"
for v in $PUBLISHED; do check_published "$v"; done

finish
