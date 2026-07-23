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
# Requires: aomenc + aomdec (libaom) on PATH. Skips cleanly (exit 0) when absent so
# CI without libaom is not blocked; set CONFORMANCE_STRICT=1 to fail instead.
#
# Usage: scripts/conformance.sh            (generate corpus + run)
#        CONFORMANCE_KEEP=1 scripts/...    (keep the generated corpus for inspection)

set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
WORK="${CONFORMANCE_WORK:-build/conformance}"
FRAME_LIMIT=5

if ! command -v aomenc >/dev/null 2>&1 || ! command -v aomdec >/dev/null 2>&1; then
    echo "conformance: libaom (aomenc/aomdec) not found — SKIPPED"
    [ "${CONFORMANCE_STRICT:-0}" = "1" ] && exit 1
    exit 0
fi

mkdir -p "$WORK"
cyrius build programs/conformance.cyr build/drishti-conformance >/dev/null 2>&1 || {
    echo "conformance: harness build FAILED"; exit 1; }

# A continuous-tone source: libaom's screen-content detector flags synthetic test
# patterns and turns on palette/intrabc, which drishti rejects by design.
if [ ! -f "$WORK/src.yuv" ]; then
    ffmpeg -loglevel error -y -f lavfi -i "mandelbrot=size=64x64:rate=30" \
        -frames:v $FRAME_LIMIT -pix_fmt yuv420p -f rawvideo "$WORK/src.yuv" 2>/dev/null || {
        echo "conformance: ffmpeg not found — SKIPPED"; exit 0; }
fi

# --sb-size=64 is REQUIRED: libaom defaults to 128x128 superblocks and drishti's SB
# loop is 64x64-only, so every stock libaom stream (and every published AV1 test
# vector we surveyed) rejects up front. 128x128 support is the single gate blocking
# the standard vector corpus (roadmap.md E2).
enc() { # name kf_only extra...
    local name="$1"; shift
    local kfonly="$1"; shift
    local kf=""
    [ "$kfonly" = "1" ] && kf="--kf-max-dist=1 --limit=1"
    [ "$kfonly" = "1" ] || kf="--lag-in-frames=0 --limit=$FRAME_LIMIT"
    aomenc --codec=av1 -w 64 -h 64 --i420 --sb-size=64 --cpu-used=8 --end-usage=q \
        --cq-level=40 --aq-mode=0 --deltaq-mode=0 --enable-restoration=0 \
        --tune-content=default --enable-palette=0 --enable-intrabc=0 $kf "$@" \
        --ivf -o "$WORK/$name.ivf" "$WORK/src.yuv" 2>/dev/null
}

pass=0; fail=0; xfail=0
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
        local off=$(( (k-1) * 6144 ))
        dd if="$WORK/$name.ref" bs=1 skip=$off count=6144 of="$WORK/$name.f$k" status=none 2>/dev/null
        local a b st
        a=$(md5sum "build/conformance-out-$k.i420" 2>/dev/null | cut -d' ' -f1)
        b=$(md5sum "$WORK/$name.f$k" 2>/dev/null | cut -d' ' -f1)
        if [ -z "$a" ]; then st="reject"; else
            if [ "$a" = "$b" ]; then st="OK"; else st="differs"; fi
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

echo "=== drishti conformance (libaom-encoded streams, libaom reference pixels) ==="
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
check seq_nofilt  keyframe

# ---- PUBLISHED conformance vectors (libaom's own corpus + its own reference MD5s) ----
# These are the real thing: streams drishti never touched, with checksums published by
# the reference implementation. They ALL use 128x128 superblocks (libaom's default), so
# every one of them rejected outright until E2a landed. The KEYFRAME (frame 1) is the
# gate; later frames hit the inter gaps (E2b/E2c) and are not scored here.
VDIR="${CONFORMANCE_VECTORS:-build/vectors}"
AOM_BASE=https://storage.googleapis.com/aom-test-data
PUBLISHED="av1-1-b8-01-size-16x16 av1-1-b8-01-size-32x32 av1-1-b8-01-size-64x64 \
av1-1-b8-00-quantizer-32 av1-1-b8-04-cdfupdate av1-1-b8-05-mv"
# Known keyframe gaps, each with a named cause (roadmap.md E2d/E2e):
#   quantizer-00 -> coded_lossless = 1 (the WHT lossless path)
#   mfmv         -> uses_lr = 1 (loop restoration active on the keyframe)
PUBLISHED_XFAIL="av1-1-b8-00-quantizer-00 av1-1-b8-06-mfmv"

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

# ---- THE 128-SB REPRODUCER (E2d) ----
# Same source, same encoder settings, ONLY --sb-size differs. 64 must match; 128 is the
# known defect. This is the minimal local handle on it: it needs partial superblock
# coverage in BOTH dimensions (352x288 with 128-SBs leaves a 96-col x 32-row remainder),
# and it is CONTENT-dependent — the published 352x288 vectors cdfupdate/quantizer-32 have
# the same geometry and decode fine. NOT a lossless bug: lossless at 128 SB matches at
# 256x256, 128x128 and 256x224.
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
        echo "  352x288 sb-size=$sb: keyframe differs (known 128-SB defect)"; xfail=$((xfail+1))
    else
        echo "  352x288 sb-size=$sb: keyframe REGRESSED"; fail=$((fail+1))
    fi
}
echo "--- 128-SB reproducer (same source, only --sb-size differs) ---"
sbrepro 64 match
sbrepro 128 xfail

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
