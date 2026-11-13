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
SB_CASES="64 128"
# kind_WxH_sbN: dqlf = delta_q + delta_lf, dqonly = delta_q alone (0.8.2).
DELTA_CASES="dqlf_352x288_sb64 dqlf_352x288_sb128 dqonly_352x288_sb64"
PUBLISHED="av1-1-b8-01-size-16x16 av1-1-b8-01-size-32x32 av1-1-b8-01-size-64x64 \
av1-1-b8-00-quantizer-32 av1-1-b8-04-cdfupdate av1-1-b8-05-mv \
av1-1-b8-00-quantizer-00 av1-1-b8-06-mfmv"

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
    for c in $SB_CASES; do skip_case "sbrepro_sb$c" "$1"; done
    for c in $DELTA_CASES; do skip_case "$c" "$1"; done
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
    rm -f build/conformance-input.ivf build/conformance-out-*.i420
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
    got=$(md5sum build/conformance-out-1.i420 2>/dev/null | cut -d' ' -f1)
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
        got=$(md5sum "build/conformance-out-$k.i420" 2>/dev/null | cut -d' ' -f1)
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
        a=$(md5sum "build/conformance-out-$k.i420" 2>/dev/null | cut -d' ' -f1)
        b=$(md5sum "$WORK/$name.f$k" 2>/dev/null | cut -d' ' -f1)
        if [ -z "$a" ]; then st="reject"; else
            if [ "$a" = "$b" ]; then st="OK"; else
                st="differs $(frame_delta "build/conformance-out-$k.i420" "$WORK/$name.f$k")"
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
# every one of them rejected outright until the 128x128-superblock gate landed. Only the
# KEYFRAME (frame 1) is scored here; scoring every frame of the full corpus is roadmap.md 0.8.5.
VDIR="${CONFORMANCE_VECTORS:-build/vectors}"
AOM_BASE="${CONFORMANCE_AOM_BASE:-https://storage.googleapis.com/aom-test-data}"
# NO published keyframe gaps remain. quantizer-00 and mfmv were the last two, and both
# were filed here with a WRONG named cause — "coded_lossless = 1 (the WHT lossless path)"
# and "uses_lr = 1 (loop restoration)" respectively. A controlled sweep refuted both
# attributions (0.7.126), and the real cause turned out to be neither feature: a single
# unbounded store in av1_clear_cdef overwriting the CDF blob (the CDEF-grid heap overflow). The lesson is worth
# keeping: a named cause on an xfail is a HYPOTHESIS, not a diagnosis — label it as one.
PUBLISHED_XFAIL=""

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
check_published() { # name expect(match|xfail)
    local name="$1" expect="$2"
    if ! fetch_vec "$name"; then skip_case "$name" "vector fetch failed"; return; fi
    local ref got
    ref=$(head -1 "$VDIR/$name.ivf.md5" | cut -d' ' -f1)
    if ! echo "$ref" | grep -qE '^[0-9a-f]{32}$'; then
        echo "  $name: SETUP FAILED (published md5 file holds no md5)"; fail=$((fail+1)); return
    fi
    run_drishti "$VDIR/$name.ivf" "$WORK/$name.log" || {
        echo "  $name: SETUP FAILED (copy)"; fail=$((fail+1)); return; }
    got=$(md5sum build/conformance-out-1.i420 2>/dev/null | cut -d' ' -f1)
    if [ -n "$got" ] && [ "$got" = "$ref" ]; then
        echo "  $name: keyframe BIT-EXACT vs published md5"; pass=$((pass+1))
    elif [ "$expect" = "xfail" ]; then
        echo "  $name: keyframe differs (known gap)"; xfail=$((xfail+1))
    else
        echo "  $name: keyframe REGRESSED (ref=$ref got=${got:-none})"; fail=$((fail+1))
    fi
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
    a=$(md5sum build/conformance-out-1.i420 2>/dev/null | cut -d' ' -f1)
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
    a=$(md5sum build/conformance-out-1.i420 2>/dev/null | cut -d' ' -f1)
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
        a=$(md5sum "build/conformance-out-$k.i420" 2>/dev/null | cut -d' ' -f1)
        b=$(dd if="$WORK/$n.ref" bs="$fs" skip=$((k-1)) count=1 status=none | md5sum | cut -d' ' -f1)
        if [ -n "$a" ] && [ "$a" = "$b" ]; then line="$line f$k=OK"; pass=$((pass+1))
        else line="$line f$k=REGRESSED"; fail=$((fail+1)); fi
        k=$((k+1))
    done
    echo "$line"
}
echo "--- per-superblock deltas (delta_q / delta_lf; every frame hard) ---"
for c in $DELTA_CASES; do deltacase "$c"; done

echo "--- published libaom vectors (128x128 superblocks) ---"
for v in $PUBLISHED; do check_published "$v" match; done
for v in $PUBLISHED_XFAIL; do check_published "$v" xfail; done

finish
