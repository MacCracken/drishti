#!/usr/bin/env bash
# scripts/oom-sweep.sh — OOM fault injection over one stream (0.8.5), for make conformance's oom section.
#
# Every allocation in src/ goes through dr_alloc, and build/conformance-input.oom = k makes drishti-conformance's
# k-th one fail (once; the decoder carries on). A run whose k-th allocation failed must stop with DR_ERR_OOM, and
# nothing else: a crash or hang is CRASH, a decoded unit that differs from the fault-free decode is CORRUPT, another
# error code is ERR<codes> (a mislabelled OOM), and a run with no error at all is TOLERATED (the failure was
# swallowed — nothing in drishti allocates what it does not need, so a swallowed failure is a decode that went on
# without it).
#
#   scripts/oom-sweep.sh sites                     build the SITE-TAGGED harness: a copy of the tree in which every
#                                                  dr_alloc / dr_alloc_keep call is dr_alloc_at(site, keep, ...),
#                                                  served exactly as before, so a trace run lists the
#                                                  site of every allocation in order (build/oom/sites.txt maps them)
#   scripts/oom-sweep.sh sweep NAME IVF MODE [LST] [MD5]
#       MODE full   fail every k = 1..N
#       MODE sites  trace the fault-free decode with the site-tagged harness, then fail each allocation SITE at its
#                   first and last occurrence and three evenly spaced between (every occurrence when it has at most 5)
#       LST         the large-scale tile anchor count sidecar, if the stream is one
#       MD5         the stream's committed reference md5s (one line per unit, "-" for a unit with no output): the
#                   fault-free baseline must match them, so "matches the baseline" means "matches the reference"
#     Prints one "RESULT ..." line: NAME N=<allocations> sites=<n> runs=<n> then OOM=<n> and every other verdict
#     count; for a broken k, a "BAD k verdict site" line (site via the site-tagged harness). Exit 0 iff every run was
#     OOM (and the baseline matched).
#
# Run from the repo root after drishti-conformance is built (make conformance does both).
set -u
OUT=build/oom
BIN=$(realpath build/drishti-conformance)
JOBS=$(nproc 2>/dev/null || echo 4)

build_sites() {
    mkdir -p "$OUT"
    local d
    d=$(mktemp -d "$OUT/tree.XXXXXX") || return 1
    cp -r src programs lib cyrius.cyml "$d/" || return 1
    [ -f cyrius.lock ] && cp cyrius.lock "$d/"
    python3 -I - "$d" "$OUT/sites.txt" <<'PY' || return 1
import re, glob, sys, os
d, table = sys.argv[1], sys.argv[2]
pat = re.compile(r'(?<![A-Za-z0-9_])dr_alloc(_keep)?\(')
sites = []
for f in sorted(glob.glob(d + '/src/*.cyr')):
    lines = open(f).read().split('\n')
    for i, l in enumerate(lines):
        if l.lstrip().startswith('fn dr_alloc'):
            continue
        h = l.find('#')
        code, com = (l, '') if h < 0 else (l[:h], l[h:])
        def tag(m):
            sites.append('%s:%d' % (os.path.basename(f), i + 1))
            return 'dr_alloc_at(%d, %d, ' % (len(sites) - 1, 1 if m.group(1) else 0)
        nc = pat.sub(tag, code)
        if nc != code:
            lines[i] = nc + com
    open(f, 'w').write('\n'.join(lines))
p = d + '/src/drishti.cyr'
s = open(p).read()
anchor = 'fn dr_alloc_fail_at(n): i64 {'
if s.count(anchor) != 1:
    sys.exit('oom-sweep: dr_alloc_fail_at not found once in src/drishti.cyr')
s = s.replace(anchor, '''var Dr_Alloc_Trace = 0;
fn dr_alloc_at(site, keep, size): i64 {
    if (Dr_Alloc_Trace != 0) { print("T ", 2); print_num(site); print("\\n", 1); }
    if (dr_alloc_inject() != 0) { print("OOMSITE ", 8); print_num(site); print("\\n", 1); return 0; }
    return dr_alloc_serve(size, keep);
}
fn dr_alloc_fail_at(n): i64 {
    if (n == 999999999) { Dr_Alloc_Trace = 1; n = 0; }''', 1)
open(p, 'w').write(s)
open(table, 'w').write(''.join('%d %s\n' % (i, x) for i, x in enumerate(sites)))
print('%d allocation sites tagged' % len(sites))
PY
    (cd "$d" && cyrius build programs/conformance.cyr conformance-sites > build.log 2>&1) || {
        echo "oom-sweep: the site-tagged harness did not build (see $d/build.log)"; return 1; }
    mv "$d/conformance-sites" "$OUT/conformance-sites"
    rm -rf "${d:?}"
    return 0
}

# one harness run in its own directory: run_in DIR BINARY K IVF LST
run_in() {
    mkdir -p "$1/build"
    cp "$4" "$1/build/conformance-input.ivf"
    echo "$3" > "$1/build/conformance-input.oom"
    if [ -n "$5" ]; then cp "$5" "$1/build/conformance-input.lst"; fi
    (cd "$1" && timeout 60 "$2" > log 2>&1)
}

# the verdict of one k (run from xargs): prints "k verdict"
one_k() {
    local k=$1 d="$W/k$1" rc verdict=OOM codes u m f
    run_in "$d" "$BIN" "$k" "$IVF" "$LST"; rc=$?
    if [ "$rc" -gt 1 ]; then echo "$k CRASH"; rm -rf "${d:?}"; return; fi
    while read -r u m; do
        f="$d/build/conformance-out-$u.yuv"
        if [ -f "$f" ] && [ "$(md5sum < "$f" | cut -c1-32)" != "$m" ]; then verdict=CORRUPT; fi
    done < "$W/base.md5"
    if [ "$verdict" = OOM ]; then
        codes=$(grep -o 'err=[0-9-]*' "$d/log" | sed 's/err=//' | sort -u | tr '\n' ',' || true)
        if [ -z "$codes" ]; then verdict=TOLERATED
        elif [ "$codes" != "9," ]; then verdict="ERR${codes%,}"; fi
    fi
    echo "$k $verdict"
    rm -rf "${d:?}"
}

sweep() {
    local name=$1 mode=$3
    IVF=$(realpath "$2"); LST=""; [ -n "${4:-}" ] && LST=$(realpath "$4")
    local md5=${5:-}
    mkdir -p "$OUT"
    W=$(mktemp -d "$OUT/$name.XXXXXX"); W=$(realpath "$W")
    export W IVF LST BIN
    export -f run_in one_k
    # the fault-free baseline: N, and every unit's md5
    run_in "$W/base" "$BIN" 0 "$IVF" "$LST"
    local n
    n=$(sed -n 's/^oom: fail-at 0 allocations \([0-9]*\)$/\1/p' "$W/base/log")
    if [ -z "$n" ]; then echo "RESULT $name BASELINE-FAILED (no allocation count)"; return 1; fi
    : > "$W/base.md5"
    local f k
    for f in "$W"/base/build/conformance-out-*.yuv; do
        [ -e "$f" ] || continue
        k=$(basename "$f" .yuv); k=${k#conformance-out-}
        echo "$k $(md5sum < "$f" | cut -c1-32)" >> "$W/base.md5"
    done
    sort -n -o "$W/base.md5" "$W/base.md5"
    if [ -n "$md5" ]; then
        # unit u's reference is line u of the md5 file; "-" = no output for that unit
        local u=1 want got bad=0
        while read -r want; do
            got=$(awk -v u="$u" '$1 == u { print $2 }' "$W/base.md5")
            if [ "$want" = "-" ]; then [ -z "$got" ] || bad=1
            elif [ "$got" != "$want" ]; then bad=1; fi
            u=$((u + 1))
        done < "$md5"
        if [ "$bad" != 0 ]; then echo "RESULT $name BASELINE-MISMATCH (the fault-free decode is not the reference)"
            rm -rf "${W:?}"; return 1; fi
    fi
    # the k list
    local sites=0
    if [ "$mode" = full ]; then
        seq 1 "$n" > "$W/klist"
    else
        run_in "$W/trace" "$(realpath "$OUT/conformance-sites")" 999999999 "$IVF" "$LST"
        grep '^T ' "$W/trace/log" | awk '{ print NR, $2 }' > "$W/trace.ks"
        if [ "$(wc -l < "$W/trace.ks")" != "$n" ]; then
            echo "RESULT $name TRACE-MISMATCH (the site-tagged harness made $(wc -l < "$W/trace.ks")" \
              "allocations, not $n)"
            rm -rf "${W:?}"; return 1
        fi
        sites=$(awk '{ print $2 }' "$W/trace.ks" | sort -u | wc -l)
        if [ -n "${OOM_SITES_ACC:-}" ]; then awk '{ print $2 }' "$W/trace.ks" | sort -u >> "$OOM_SITES_ACC"; fi
        awk '{ n[$2]++; occ[$2, n[$2]] = $1 }
          END { for (s in n) { c = n[s]
                  if (c <= 5) { for (i = 1; i <= c; i++) print occ[s, i] }
                  else { for (i = 0; i < 5; i++) print occ[s, 1 + int(i * (c - 1) / 4)] } } }' "$W/trace.ks" \
          | sort -nu > "$W/klist"
    fi
    xargs -P "$JOBS" -I{} bash -c 'one_k {}' < "$W/klist" > "$W/verdicts"
    local runs summary
    runs=$(wc -l < "$W/klist")
    summary=$(awk '{ c[$2]++ } END { for (v in c) printf " %s=%d", v, c[v] }' "$W/verdicts")
    if [ "$mode" = full ]; then echo "RESULT $name N=$n runs=$runs$summary"
    else echo "RESULT $name N=$n sites=$sites runs=$runs$summary"; fi
    local ok=0
    if [ "$(grep -c ' OOM$' "$W/verdicts")" = "$runs" ]; then ok=1; fi
    if [ "$ok" = 0 ] && [ -x "$OUT/conformance-sites" ]; then
        # name the site of (up to 8 of) the broken k's
        local line kk vv sid
        grep -v ' OOM$' "$W/verdicts" | sort -n | head -8 | while read -r kk vv; do
            run_in "$W/attr$kk" "$(realpath "$OUT/conformance-sites")" "$kk" "$IVF" "$LST"
            sid=$(sed -n 's/^OOMSITE \([0-9]*\)$/\1/p' "$W/attr$kk/log" | head -1)
            echo "BAD $kk $vv $(awk -v i="$sid" '$1 == i { print $2 }' "$OUT/sites.txt")"
        done
    fi
    rm -rf "${W:?}"
    [ "$ok" = 1 ]
}

case "${1:-}" in
    sites) build_sites ;;
    sweep) shift; sweep "$@" ;;
    *) echo "usage: scripts/oom-sweep.sh sites | sweep NAME IVF full|sites [LST] [MD5]"; exit 2 ;;
esac
