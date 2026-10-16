# Parliamentary comparison worksheet contract

A local read-only comparison queue for:

> What was proposed or recommended, and what substantive decision is actually evidenced?

Use the [canonical run guide](../../README.md) for `make comparison-demo` and `make test`. This component assembles explicitly selected current converter review packets. Its historical frozen-ledger branch requires the separate complete private checkout; that source-bearing dataset is not included in this release. Runtime code and tests are unchanged; this README has been adapted to the isolated layout. It does not parse new parliamentary sources, run a model, fetch a URL, classify events, merge affairs, adjudicate evidence, or change any historical evaluation. It reuses the existing converter and gap-ledger checks without editing them.

Every row is **UNADJUDICATED**, **UNMAPPED** and **answer-ineligible**. Blank manual cells are a worksheet, not a new review authority. Editing a JSON copy does not create independent review, semantic truth or answer eligibility; there is no worksheet import/adjudication command.

## What the view adds

- A single question-first index across selected documents, rather than manually collecting candidate JSON from separate page-first packets.
- Document author, acting body and addressee shown separately. Event/outcome wording, all conflicting alternatives, original dates and exact quote offsets stay intact.
- One stable identity per original candidate or historical annotation. No equivalence or conflict resolution across sources is inferred. Selecting a second packet does not overwrite another event.
- Every converter page and request outcome remains represented, including unresolved native text, failed/malformed/unattempted requests, and structurally valid zero-candidate responses. No candidate is never evidence of no relevant event.
- Original converter review packets are copied byte-for-byte to local sibling paths; row links reach the source-first page and original PDF page. No original packet is edited.
- Converter-packet baselines remain unknown, with blank manual baseline-receipt cells. Historical baseline observations require the separately held ledger data; they are not new results of this release.
- Blank proposed-mapping, explanation, author/date, unresolved-evidence and multiple-interpretation cells. Suggested vocabulary includes proposal, recommendation, several decision scopes, unmappable and multiple interpretations. No option is automatically selected.

## Local operation

The public owned demonstration is `make comparison-demo`; prerequisites and exact output paths are in the [run guide](../../README.md). It uses only synthetic converter packets. No model call or dependency installation occurs inside the worksheet.

Advanced direct use requires the existing pinned Python environment. From the repository root, the script is `track_2a/src/track_2a_comparison/worksheet.py`; `--repo-root` must identify the absolute `track_2a/src` directory, alongside an explicit `--selection` and fresh `--out`. This is a path reference, not a recorded execution result.

The output parent must exist and the output directory must be new. Open `worksheet.html`. Its styles are inline, it contains no scripts or remote assets, and every generated link is a local sibling or fragment. Source URLs and source-controlled strings are escaped inert text. `worksheet.json` is the strict JSON template; `selection.original.json` preserves exact selection bytes. `result.json` records output hashes and is written last. A failed admission creates no worksheet output; a later IO failure may leave an incomplete directory with no successful result receipt. Do not reuse incomplete directories.

Paths in the selection may be absolute or relative to the selection file; symlinks and parent traversal are rejected. Keep inputs and outputs in trusted private directories. The renderer is not a hostile multi-user filesystem sandbox. Copying or externally sharing the output also shares the selected converter sources and original captures; this tool does not authorize sharing or determine rights.

## Exact selection contract

All keys below are required; unspecified keys reject. Either `converter_packets` or `frozen_gap_ledger` must select something.

```json
{
  "profile": "opd-question-selection-1",
  "converter_packets": [
    {
      "selection_id": "selected-report",
      "label": "Explicitly selected local report",
      "prepared_directory": "/local/work/prepared",
      "imported_directory": "/local/work/imported",
      "review_directory": "/local/work/review",
      "expected_prepare_sha256": "EXACT_INDEPENDENTLY_RETAINED_PREPARATION_PIN",
      "expected_import_sha256": "EXACT_INDEPENDENTLY_RETAINED_IMPORT_PIN",
      "expected_review_sha256": "EXACT_INDEPENDENTLY_RETAINED_REVIEW_PIN"
    }
  ],
  "frozen_gap_ledger": null
}
```

Each pin must be 64 lowercase hexadecimal characters. Retain successful converter stdout receipts at creation time or use an independently retained trusted receipt. Reading a pin from an untrusted incoming packet and echoing it into the selection is not continuity verification. Hashes establish consistency with selected bytes, not authorship, semantic correctness, model identity, human review or rights.

The `frozen_gap_ledger` field is `null` in the distributed converter-only example. Historical ledger manifests and source-bearing data are intentionally absent. Do not substitute authored examples, infer a new trusted pin or treat the retained ledger validator as a bundled real-source dataset.

## Admission and scope

Converter admission reuses `verify_result`, `load_prepared` and `validate_candidate`; checks preparation bounds and extraction/bundle agreement; replays the importer's classification order from the original index and retained original captures using its entry/schema/location helpers; checks exact units, capture identities, failure records and coverage counts; and regenerates the source-first review with `export_review` in a disposable local directory. Every non-lifecycle review artifact must match the selected packet exactly. Current converter 0.2.0/policy 2 only; older preparations, stale schemas/prompts, unsupported claims, malformed JSON, duplicate keys, missing required packet bytes and tampering fail closed. Original malformed response captures and declared failures to read capture bytes remain valid *failure records* in a correctly generated packet; they are not admitted as candidates. A historical read failure is a retained declaration, not proof of what bytes were available at capture time.

Gap-ledger admission requires the selected manifest pin and the existing `run()` freeze, schema, source binding and denominator checks. These validate the ledger's declared selected historical text and researcher locators, not original PDFs. The ledger's original frozen code/data/tests remain unchanged. Every selected family keeps all registered events and sources, including sources with no event or uninspected minutes. The worksheet has no event/date filters that could hide unresolved rows.

Output rows preserve original candidate/annotation objects. Converter date fields are deliberately shown as unassessed because the converter contract has no date fields. The historical ledger has no document-author field; its author cell is unassessed and never filled from the event actor. These missing distinctions must be recorded manually or addressed in a separately designed contract, not inferred by this view.

Caps: at most 16 selected converter packets, 32 explicitly selected ledger families, 4,096 output rows, 1 MiB selection JSON, 32 MiB per generated JSON/HTML, and 128 MiB copied converter packet bytes. Underlying converter/ledger limits still apply. Output admission is deterministic for the same selected artifacts; manifest-order changes do not reorder rows or the canonical worksheet. Invocation/result receipt identities intentionally vary, and original selection bytes are preserved separately.

## Engineering checks and owned demo

Use the canonical `make test` route. Its worksheet wrapper explicitly skips the two tests that need excluded historical ledger data. Running the unscoped upstream test-discovery command would incorrectly expect that private dataset. The assembled Docker test route has not yet run; prior tests describe their original scopes only.

Tests cover proposal/recommendation/decision distinctions from unchanged source fields, wrong actor with a real quote, repeated-phrase exact offsets, conflicting outcomes and dates, missing/unresolved pages, zero candidates, malformed/missing/duplicate captures, unknown/blocked baselines, stable ordering, preserved separate identities, stale versions, unsafe paths, immutable input bytes, XSS, missing pins/files, tampering, coherently rehashed review promotion and captured-candidate suppression through forged import statuses. Socket access is denied during a generation test. Structural tests are authored controls, not semantic accuracy or human review.

The demo creates two new owned synthetic sources and authored candidate captures. One contains a committee recommendation and an unresolved annex; the other contains an agenda decision. Unresolved and unattempted pages remain visible. It performs zero inference and makes no real-world evidence claim.

## What remains unproven

No independent source reader has reviewed or mapped the rows. No completeness, source-rights clearance, model quality, API deficit, correctness-preserving time saving or user benefit is established. The excluded historical sample is researcher-seen and partly locator-only; it supplies no new evaluation coverage for this release. A real quote with a fabricated actor can pass structural checks and remains answer-ineligible. Native text may differ from visual reading order. Original converter filesystem race limitations remain; no security certification is claimed.

The next meaningful evidence is an authorized independent reader completing this one question, recording why each mapping succeeds or fails and comparing the same question with the existing API/search/manual-source baseline. An honest negative finding that the baseline already answers the task is a valid outcome.
