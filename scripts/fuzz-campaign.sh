#!/usr/bin/env bash
# scripts/fuzz-campaign.sh WORKERS ITERATIONS [FIRST_SEED] — a long corpus-guided fuzzing campaign (0.8.5).
#
# Builds tests/av1_corpus.fcyr once and runs WORKERS copies in parallel, each in its own directory under
# build/fuzz/ with a fuzz.cfg of "seed iterations 1": worker i fuzzes from seed FIRST_SEED + i. In save mode every
# mutant is written to the worker's fuzz-cur.ivf before it is decoded, and one that fails an oracle to fuzz-bad.ivf,
# so whatever kills a worker (a crash, a SIGALRM hang) or trips an oracle is on disk. A worker that does not end
# cleanly keeps its directory and has its input copied to build/fuzz/found-<seed>.ivf. Exit 0 iff every worker ended
# cleanly. `make fuzz` runs the same harness for a short fixed campaign; this is the long one.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
W=${1:-4} N=${2:-1000} S0=${3:-1}
mkdir -p build/fuzz
cyrius build tests/av1_corpus.fcyr build/fuzz/corpus-fuzz > build/fuzz/build.log 2>&1 || {
    echo "fuzz-campaign: the harness did not build (build/fuzz/build.log)"; exit 2; }
work() {
    local s=$1 n=$2 d="build/fuzz/w$1" rc
    rm -rf "${d:?}"; mkdir -p "$d"
    ln -s "$ROOT/tests" "$d/tests"
    echo "$s $n 1" > "$d/fuzz.cfg"
    (cd "$d" && ../corpus-fuzz > log 2>&1); rc=$?
    if [ "$rc" -eq 0 ] && ! grep -q FZBAD "$d/log"; then
        echo "worker seed=$s: ok ($(grep -o 'corpus fuzz: .*' "$d/log"))"; rm -rf "${d:?}"
    else
        local what="rc=$rc"; [ "$rc" -eq 142 ] && what="HANG (SIGALRM)"; [ "$rc" -eq 139 ] && what="CRASH (SIGSEGV)"
        if [ -f "$d/fuzz-bad.ivf" ]; then cp "$d/fuzz-bad.ivf" "build/fuzz/found-$s.ivf"
        else cp "$d/fuzz-cur.ivf" "build/fuzz/found-$s.ivf" 2>/dev/null; fi
        echo "worker seed=$s: FOUND $what $(grep -m3 FZBAD "$d/log" | tr '\n' ' ') -> build/fuzz/found-$s.ivf"
    fi
}
export -f work; export ROOT
seq "$S0" $((S0 + W - 1)) | xargs -P "$W" -I{} bash -c "work {} $N" | tee build/fuzz/campaign.log
! grep -q FOUND build/fuzz/campaign.log
