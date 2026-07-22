# Makefile for drishti
#
# Most commands delegate to the `cyrius` CLI, which reads cyrius.cyml.
# drishti is a pure-Cyrius CPU library — no C, no FFI, no libav* — so
# every target is host-runnable.
#
# Quick reference:
#   make test           — CPU-only tests (globs ALL tests/*.tcyr suites)
#   make build          — link-check the library (programs/smoke.cyr)
#   make bench          — run tests/*.bcyr benchmarks
#   make fuzz           — run tests/*.fcyr mutation harnesses
#   make dist           — regenerate dist/drishti.cyr via `cyrius distlib`
#   make lint / fmt-check / vet  — quality gates
#   make version-check  — VERSION / cyrius.cyml / CHANGELOG / drishti_version() agree
#   make test-all       — version-check + dist regen + CPU tests + fuzz
#   make clean          — scrub build/
#
# Adapted from chitra's Makefile (the codec-lib convention repo).

CYRIUS ?= cyrius

# ---------------------------------------------------------------------------
# Lib-wiring guard — refuses to build if lib/ is a symlink to a cyrius
# checkout (causes cross-repo writes when an agent edits lib/*.cyr).
# lib/ must be a real directory populated by `cyrius deps`.
# ---------------------------------------------------------------------------
.PHONY: check-lib-wiring
check-lib-wiring:
	@if [ -L lib ]; then \
		echo "ERROR: lib/ is a symlink ($$(readlink lib))."; \
		echo "       drishti's lib/ must be a real directory populated by"; \
		echo "       'cyrius deps'. Fix: rm lib && mkdir lib && cyrius deps"; \
		exit 1; \
	fi

# ---------------------------------------------------------------------------
# Library gates
# ---------------------------------------------------------------------------

.PHONY: build
build: check-lib-wiring
	@mkdir -p build
	$(CYRIUS) build programs/smoke.cyr build/drishti-smoke
	@echo "smoke: $$(wc -c < build/drishti-smoke) bytes"
	@# RUN it — building alone never executed a single assertion, so the smoke
	@# program's stale version check rotted undetected from 0.7.1 to 0.7.125.
	@./build/drishti-smoke || { echo "smoke: FAILED"; exit 1; }
	@echo "smoke: OK"

.PHONY: test
# Globs ALL tests/*.tcyr so codec-family suites (av1.tcyr, h264.tcyr, …)
# are picked up automatically as they land; each is a standalone suite
# with its own main(). Per-file loop because the aggregate `cyrius test`
# exit code is 0 even when a suite fails (verified at pin 6.4.43).
test: check-lib-wiring
	@for f in tests/*.tcyr; do $(CYRIUS) test "$$f" || exit 1; done

.PHONY: bench
bench: check-lib-wiring
	@for f in tests/*.bcyr; do $(CYRIUS) bench "$$f" || exit 1; done

.PHONY: fuzz
# .fcyr harnesses are plain exit-0 programs — run them through
# `cyrius test` (project-local convention; `cyrius fuzz` looks in fuzz/).
fuzz: check-lib-wiring
	@for f in tests/*.fcyr; do $(CYRIUS) test "$$f" || exit 1; done

# Decode streams drishti did NOT produce and compare pixels against libaom's own
# decoder — the only gate here whose reference drishti cannot have colluded with.
# Skips cleanly when libaom/ffmpeg are absent (CONFORMANCE_STRICT=1 to fail).
.PHONY: conformance
conformance:
	@scripts/conformance.sh

.PHONY: lint
lint:
	@fail=0; \
	for f in src/*.cyr programs/*.cyr tests/*.tcyr; do \
		out=$$($(CYRIUS) lint $$f 2>&1); echo "$$out"; \
		echo "$$out" | grep -qE '^\s*warn ' && fail=1; \
		echo "$$out" | grep -qE '^[1-9][0-9]* untracked deferrals' && fail=1; \
	done; \
	[ $$fail -eq 0 ] || { echo "lint: warnings present"; exit 1; }

.PHONY: fmt-check
fmt-check:
	@# cyrius 6.x's `fmt <file> --check` reports formatting via the EXIT
	@# CODE only (0 = clean, non-zero = needs fmt). The file goes BEFORE
	@# the --check flag.
	@fail=0; \
	for f in src/*.cyr programs/*.cyr tests/*.tcyr; do \
		if ! $(CYRIUS) fmt $$f --check > /dev/null 2>&1; then \
			echo "needs fmt: $$f"; fail=1; \
		fi; \
	done; \
	[ $$fail -eq 0 ] || { echo "fmt: drift detected"; exit 1; }

.PHONY: vet
vet:
	$(CYRIUS) vet programs/smoke.cyr

.PHONY: dist
dist:
	$(CYRIUS) distlib

.PHONY: version-check
version-check:
	@./scripts/version-check.sh

.PHONY: test-all
test-all: version-check dist test fuzz

.PHONY: clean
clean:
	rm -rf build/
