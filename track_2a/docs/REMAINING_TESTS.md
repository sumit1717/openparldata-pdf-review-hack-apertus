# Exact remaining execution checks

The retained historical assembly receipt and dispatcher component mock-test manifest/logs are in `validation/`. They record their original source-only scopes and original file identities; edited documentation is identified separately in the current root manifest. Use the [canonical run guide](../README.md) for commands and [release gates](RELEASE_GATES.md) for the short evidence checklist. All actual Docker, native/PDF, provider, manually checked reference and full-product checks below remain unexecuted for this assembled candidate. No silence, source inspection, previous snapshot pass or authored output is a substitute.

## A. Static assembly review (safe source-only scope)

- Parse every Python file without importing or executing project code; parse JSON and check strict schemas as data.
- Recalculate copied-file Git blob SHA1 and SHA256 against `SOURCE_PINS.json`; pin all new wrapper/docs files in a candidate manifest.
- Inspect the Make → shell → Docker → CLI paths, COPY closure, pinned locks, default non-root/no-network/no-secret controls, input/output mount separation and fresh-output behavior.
- Verify only `track_2a` exists; official required paths are present; data below 100 MB; no private real source/capture or counterfeit gold is included, and the confirmed scoped project licenses are documented.
- Review the adapter overlay separately. Source-only parsing/tests establish only that contract, not a real run.

## B. Fresh Docker build and offline functionality

1. Fresh Linux amd64 non-root checkout: `make build`; retain exact candidate digest, Docker version, base digest, wheel hashes and dependency-check output. Verify no unpinned fallback install.
2. `make run`: verify the authored three-page source, zero provider calls, one valid-unadjudicated authored capture, malformed-original retention, unresolved page, review HTML/JSON and complete source/result hashes. Inspect output pixels/pages as a separate visual check if needed. Do not call it model accuracy.
3. Repeat with the same output name: fail without changing any bytes. Repeat with a fresh name: succeed with new invocation identity while deterministic preparation bytes stay equal.
4. `make test`: run the unchanged converter suite and owned-converter worksheet scope; record exact pass/fail/skip counts and reasons. The wrapper explicitly skips `test_real_frozen_ledger_dates_baselines_uninspected_annexes` and `test_unknown_family_and_tampered_ledger_failclosed` because source-bearing historical ledger data is excluded. Their upstream source remains unchanged. Run those two tests only in the complete authorized private checkout. This is not a full historical comparison-suite pass. Do not hide the separate known converter filesystem-only skips or turn synthetic checks into a security claim.
5. `make comparison-demo`: inspect the owned recommendation/agenda worksheet; all cases remain answer-ineligible, baselines unknown and manual review not started.
6. Prepare/import/review via separate absolute read-only input mounts and dedicated writable output parents. Verify root and track-directory invocations agree. Negative mounts: overlapping output/input, symlink inputs, commas/newlines, missing file, stale result pin, duplicate output, changed prepared artifact.
7. PDF negatives: image-only/empty text, missing source, unreadable/malformed, truly password-required, credential-free readable encryption marker, per-page failures and maximum bounds. No password/decryption attempt or fallback parser.
8. Capture-import negatives: malformed/duplicate JSON, wrong page/offset/quote/request, boolean integer confusion, non-finite values, duplicate or unknown request entries, failed/unattempted rows, missing/oversized unsafe captures. Verify all denominators and original-byte retention.

## C. Apertus integration (separately authorized source/provider use)

- The exact included adapter source already passed 38 normal/38 optimized authored checks and 20 independent adversarial mock checks. Reproduce the guarded suite inside the intended assembled runner before a live request, without changing converter hashes or semantic gates. This is not a full product or real-PDF pass.
- Confirm the actual endpoint/model entitlement, request recipient, approved source scope and explicit call/token/cost bound. Keep credentials out of the repository and messages. No automatic retry or paid-service setup.
- Execute one bounded real request from an authorized PDF; retain preparation pin, attempt reservation, exact request, safe raw envelope, decoded-content derivative, finish/model/usage evidence, explicit errors and strict import result.
- Demonstrate that partial/truncated/invalid response remains rejected and counted, with the original preserved where safe. Verify unchanged unadjudicated/answer-ineligible review state.
- Test the template environment-variable route only after the adapter is accepted; default `make run` must remain a clearly labeled offline engineering demonstration or be changed under a separately reviewed explicit real-model mode.

## D. Challenge evidence and finalization

- Freeze rights-cleared multilingual/multilevel real-source coverage and actual manually checked references before evaluating. There is no verified numerical minimum in the challenge; disclose the small scope rather than inventing a quota or claiming broad generality.
- Record field/event correctness and failures with agreed denominators; account for unattempted requests and unresolved pages. Human checking must be genuine and attributable.
- Answer a bounded cross-parliament question against documented API/search/official-page/manual-PDF baselines, including negative findings.
- Reconcile the six-page report with actual results, including failed and skipped stages. Complete the publication/submission checks in [RELEASE_GATES.md](RELEASE_GATES.md).
