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
# The committed tests/repro/*.ivf cases (with their reference MD5s) run ANYWHERE. The
# generated + published corpus additionally needs aomenc/aomdec/ffmpeg on PATH and is
# skipped cleanly when absent; set CONFORMANCE_STRICT=1 to fail instead.
#
# Usage: scripts/conformance.sh            (generate corpus + run)
#        CONFORMANCE_KEEP=1 scripts/...    (keep the generated corpus for inspection)

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

pass=0; fail=0; xfail=0

# ---- COMMITTED REPRODUCERS (no libaom needed) ----
# tests/repro/*.ivf are tiny libaom-encoded streams with their aomdec reference MD5
# committed alongside, so this half of the gate runs anywhere — including CI without
# libaom. BOTH are hard gates now: e2d-160x160 was always the passing control, and
# e2d-192x160 was the the CDEF-grid heap overflow xfail until av1_clear_cdef was bounded (src/av1_modeinfo.cyr).
# They differ only in width, and both are 128-superblock streams.
repro_case() { # name expect(match|xfail)
    local n="$1" expect="$2"
    local ivf="tests/repro/$n.ivf" md5f="tests/repro/$n.md5"
    [ -f "$ivf" ] && [ -f "$md5f" ] || return 0
    mkdir -p build
    cp "$ivf" build/conformance-input.ivf
    rm -f build/conformance-out-*.i420
    ./build/drishti-conformance >/dev/null 2>&1
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
    cp "$ivf" build/conformance-input.ivf
    rm -f build/conformance-out-*.i420
    ./build/drishti-conformance >/dev/null 2>&1
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
    echo "  libaom (aomenc/aomdec) not found — skipping the generated + published corpus"
    echo "=== matched=$pass  known-gap=$xfail  REGRESSED=$fail ==="
    [ "$fail" -gt 0 ] && exit 1
    [ "${CONFORMANCE_STRICT:-0}" = "1" ] && exit 1
    exit 0
fi

mkdir -p "$WORK"

# A continuous-tone source: libaom's screen-content detector flags synthetic test
# patterns and turns on palette/intrabc, which drishti rejects by design.
if [ ! -f "$WORK/src.yuv" ]; then
    # This bail must mirror the aomenc/aomdec one above: the committed reproducers already
    # ran and are HARD cases, so exiting straight to 0 here would DISCARD a real regression
    # (and ignore CONFORMANCE_STRICT). It fires on any ffmpeg failure, not just a missing
    # binary — no lavfi mandelbrot source, full disk, and so on.
    ffmpeg -loglevel error -y -f lavfi -i "mandelbrot=size=${CORPUS_W}x${CORPUS_H}:rate=30" \
        -frames:v $FRAME_LIMIT -pix_fmt yuv420p -f rawvideo "$WORK/src.yuv" 2>/dev/null || {
        echo "  ffmpeg unavailable — skipping the generated + published corpus"
        echo "=== matched=$pass  known-gap=$xfail  REGRESSED=$fail ==="
        [ "$fail" -gt 0 ] && exit 1
        [ "${CONFORMANCE_STRICT:-0}" = "1" ] && exit 1
        exit 0; }
fi

# This generated corpus pins --sb-size=64 deliberately: it is the 64-superblock control
# path, kept green independently of the 128 path that the 128x128-superblock gate un-gated in 0.7.126. The 128
# coverage comes from the published vectors below (all of which use 128 by default).
enc() { # name kf_only extra...
    local name="$1"; shift
    local kfonly="$1"; shift
    local kf=""
    [ "$kfonly" = "1" ] && kf="--kf-max-dist=1 --limit=1"
    [ "$kfonly" = "1" ] || kf="--lag-in-frames=0 --limit=$FRAME_LIMIT"
    aomenc --codec=av1 -w $CORPUS_W -h $CORPUS_H --i420 --sb-size=64 --cpu-used=8 --end-usage=q \
        --cq-level=40 --aq-mode=0 --deltaq-mode=0 --enable-restoration=0 \
        --tune-content=default --enable-palette=0 --enable-intrabc=0 $kf "$@" \
        --ivf -o "$WORK/$name.ivf" "$WORK/src.yuv" 2>/dev/null
}

# The KEYFRAME (frame 1) of every corpus entry is a HARD gate: it is bit-exact today
# and must stay so. Inter frames are known gaps (roadmap.md E2) recorded as xfail —
# two distinct defects, both surfaced by this harness and neither reachable from
# drishti's own round-trip tests:
#   (a) reconstruction rounding — frames carrying real coded content decode but land
#       within max |delta| 2..4 of the reference; reproduces with CDEF *and*
#       deblocking disabled, so it is not the loop filters.
#   (b) entropy desync — busier inter frames trip the spec's SymbolMaxBits >= -14
#       bound at av1_sym_dec_exit (AV1_ERR_BAD_FRAME), i.e. drishti consumed symbols
#       the encoder never wrote. Caught cleanly; no crash, no OOB.
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
check() { # name expect(all|keyframe)
    local name="$1" expect="$2"
    cp "$WORK/$name.ivf" build/conformance-input.ivf
    rm -f build/conformance-out-*.i420
    ./build/drishti-conformance >"$WORK/$name.log" 2>&1
    aomdec --rawvideo -o "$WORK/$name.ref" "$WORK/$name.ivf" 2>/dev/null
    # iterate over DEMUXED units, not decoded ones, so a rejected frame is visible.
    local n; n=$(sed -n 's/^demuxed \([0-9]*\) .*/\1/p' "$WORK/$name.log")
    [ -n "$n" ] || n=0
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
check kf_only all
# Inter frames: frames carrying real coded content diverge by a small rounding delta
# (max |d| = 2..4) in inter reconstruction — NOT the loop filters (it reproduces with
# CDEF and deblocking both disabled). Tracked as roadmap.md E2; xfail so the gate
# still guards the keyframe path and the all-skip inter path from regressing.
check seq_filters keyframe
# HARD on every frame: with the loop filters off, all five frames are bit-exact. This is the
# inter-decode path with no filtering in the way, so it pins MC, the warp model, the residual
# and the entropy decode together.
check seq_nofilt  all

# ---- PUBLISHED conformance vectors (libaom's own corpus + its own reference MD5s) ----
# These are the real thing: streams drishti never touched, with checksums published by
# the reference implementation. They ALL use 128x128 superblocks (libaom's default), so
# every one of them rejected outright until the 128x128-superblock gate landed. The KEYFRAME (frame 1) is the
# gate; later frames hit the inter gaps (INTER-FRAME PIXEL DRIFT/INTER-FRAME SYMBOL DESYNC) and are not scored here.
VDIR="${CONFORMANCE_VECTORS:-build/vectors}"
AOM_BASE=https://storage.googleapis.com/aom-test-data
PUBLISHED="av1-1-b8-01-size-16x16 av1-1-b8-01-size-32x32 av1-1-b8-01-size-64x64 \
av1-1-b8-00-quantizer-32 av1-1-b8-04-cdfupdate av1-1-b8-05-mv \
av1-1-b8-00-quantizer-00 av1-1-b8-06-mfmv"
# NO published keyframe gaps remain. quantizer-00 and mfmv were the last two, and both
# were filed here with a WRONG named cause — "coded_lossless = 1 (the WHT lossless path)"
# and "uses_lr = 1 (loop restoration)" respectively. A controlled sweep refuted both
# attributions (0.7.126), and the real cause turned out to be neither feature: a single
# unbounded store in av1_clear_cdef overwriting the CDF blob (the CDEF-grid heap overflow). The lesson is worth
# keeping: a named cause on an xfail is a HYPOTHESIS, not a diagnosis — label it as one.
PUBLISHED_XFAIL=""

mkdir -p "$VDIR"
fetch_vec() { # name -> 0 if available
    [ -f "$VDIR/$1.ivf" ] && [ -f "$VDIR/$1.ivf.md5" ] && return 0
    curl -sf --max-time 120 -o "$VDIR/$1.ivf" "$AOM_BASE/$1.ivf" || return 1
    curl -sf --max-time 60 -o "$VDIR/$1.ivf.md5" "$AOM_BASE/$1.ivf.md5" || return 1
    return 0
}
check_published() { # name expect(match|xfail)
    local name="$1" expect="$2"
    if ! fetch_vec "$name"; then echo "  $name: (unavailable — skipped)"; return 0; fi
    cp "$VDIR/$name.ivf" build/conformance-input.ivf
    rm -f build/conformance-out-*.i420
    ./build/drishti-conformance >"$WORK/$name.log" 2>&1
    local ref got
    ref=$(head -1 "$VDIR/$name.ivf.md5" | cut -d' ' -f1)
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
sbrepro() { # sbsize expect(match|xfail)
    local sb="$1" expect="$2"
    ffmpeg -loglevel error -y -f lavfi -i "mandelbrot=size=352x288:rate=30" -frames:v 1 \
        -pix_fmt yuv420p -f rawvideo "$WORK/r.yuv" 2>/dev/null || return 0
    aomenc --codec=av1 -w 352 -h 288 --i420 --cpu-used=8 --end-usage=q --cq-level=40 \
        --sb-size="$sb" --aq-mode=0 --deltaq-mode=0 --enable-restoration=0 \
        --tune-content=default --enable-palette=0 --enable-intrabc=0 --kf-max-dist=1 \
        --limit=1 --ivf -o "$WORK/sb$sb.ivf" "$WORK/r.yuv" 2>/dev/null
    [ -f "$WORK/sb$sb.ivf" ] || return 0
    cp "$WORK/sb$sb.ivf" build/conformance-input.ivf
    rm -f build/conformance-out-*.i420
    ./build/drishti-conformance >"$WORK/sb$sb.log" 2>&1
    aomdec --rawvideo -o "$WORK/sb$sb.ref" "$WORK/sb$sb.ivf" 2>/dev/null
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
    ffmpeg -loglevel error -y -f lavfi -i "mandelbrot=size=${w}x${h}:rate=30" -frames:v 1 \
        -pix_fmt yuv420p -f rawvideo "$WORK/$n.yuv" 2>/dev/null || {
        echo "  $n: SETUP FAILED (ffmpeg)"; fail=$((fail+1)); return; }
    rm -f "$WORK/$n.ivf"
    aomenc --codec=av1 -w "$w" -h "$h" --i420 --sb-size="$sb" --cpu-used=8 --end-usage=q \
        --cq-level=40 --aq-mode=0 --deltaq-mode=0 --enable-restoration=0 \
        --tune-content=default --enable-palette=0 --enable-intrabc=0 --kf-max-dist=1 \
        --limit=1 --ivf -o "$WORK/$n.ivf" "$WORK/$n.yuv" 2>/dev/null
    [ -f "$WORK/$n.ivf" ] || { echo "  $n: SETUP FAILED (aomenc produced no stream)"
        fail=$((fail+1)); return; }
    cp "$WORK/$n.ivf" build/conformance-input.ivf
    rm -f build/conformance-out-*.i420
    ./build/drishti-conformance >"$WORK/$n.log" 2>&1
    aomdec --rawvideo -o "$WORK/$n.ref" "$WORK/$n.ivf" 2>/dev/null
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
oddmi 160 136 64
oddmi 160 136 128
oddmi 288 152 64
oddmi 288 152 128

echo "--- 128-SB reproducer (same source, only --sb-size differs) ---"
sbrepro 64 match
sbrepro 128 match   # the CDEF-grid heap overflow: was xfail until av1_clear_cdef was bounded

echo "--- published libaom vectors (128x128 superblocks) ---"
for v in $PUBLISHED; do check_published "$v" match; done
for v in $PUBLISHED_XFAIL; do check_published "$v" xfail; done

echo "=== matched=$pass  known-gap=$xfail  REGRESSED=$fail ==="
[ "${CONFORMANCE_KEEP:-0}" = "1" ] || rm -f "$WORK"/*.f[0-9] "$WORK"/*.ref
if [ "$fail" -gt 0 ]; then
    echo "conformance: FAIL — a frame that used to match no longer does"
    exit 1
fi
echo "conformance: OK"
exit 0
