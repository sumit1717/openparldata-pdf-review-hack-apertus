# PDF converter contract and limits

Use the [canonical run and review guide](../../README.md) for this release's Docker commands, prerequisites and output paths. This component reference describes converter **0.2.0**, extraction policy `credential-free-native-text-2`. Runtime code, prompt, schema and tests remain unchanged from their pinned upstream source; this README has been adapted to the isolated release layout.

The converter prepares a bounded local PDF, imports separately captured original assistant content, and exports a source-first viewing queue. It does not perform inference, provider custody verification or human adjudication. The [separate Apertus adapter](../apertus_capture/README.md) supplies an optional authorized capture route. All candidates remain `unadjudicated` and `answer_eligible=false`; a real quote with an incorrect actor can still pass structural checks.

Preparations from converter 0.1 must be rerun into fresh directories for the 0.2 lifecycle; old captures stay with their original preparation and must not be rebound to new request IDs. Historical protocols and scores are not migrated.

## Response contract

A response is one strict JSON object with exactly `request_id`, `binding`, `reviewed_scope` and `events`. Copy the first three fields unchanged from the prepared request. `response.schema.json` defines the full exact shape; unspecified keys reject. A candidate has a unique local `candidate_id`, one or more `anchors`, and separate typed fields:

- `source_type`: type of source document
- `affair`: the matter being discussed
- `author`: document or assertion author
- `actor`: person/body performing the event
- `addressee`: intended recipient or target body
- `event`: candidate action; proposals, recommendations and decisions must not be collapsed
- `outcome`: the stated outcome, separate from the action

Locations contain 1-based `page`, half-open `start`/`end` Unicode-code-point offsets into the **whole unnormalized page text**, and exact `quote`. Offsets must fall within the corresponding chunk, including when the same quote occurs elsewhere. No location from a different page/chunk/document is accepted.

Each typed field always has `state`, `value`, `evidence`, `alternatives`, `reviewed_scope` and `reason`:

| State | Contract |
| --- | --- |
| `present` | Nonempty value and evidence; no alternatives/scope |
| `explicit_absence` | Null value, explicit evidence, nonempty reason; no alternatives/scope |
| `not_stated_within_reviewed_scope` | Null value; no evidence/alternatives; exact complete request chunk scope and reason |
| `unassessed` | Null value; no evidence, alternatives or scope |
| `not_applicable` | Null value, evidence and reason; no alternatives/scope |
| `conflicting` | Null value and no top-level evidence/scope; at least two distinct alternatives, each with its own evidence |

Conflict alternatives distinguish a present value from explicit absence. They are retained, never resolved by choosing the last occurrence. These new prospective states do not migrate or reinterpret old `unknown`/`absent` labels. Scoped not-stated remains a provisional claim about that native-text chunk only, not an exhaustive PDF scan or global absence.

## Determinism, bindings and lifecycle

Preparation copies exact source bytes and hashes them. Native page text is extracted by pinned pypdf in plain mode with no normalization. Page order is complete and 1-based. `text_extracted`, `no_text_unresolved`, and `extraction_failed` are explicit, with `ocr_status=not_attempted` for every page. Empty extracted text is never called blank, scanned, OCR-successful or semantically reviewed.

The reader remains `PdfReader(..., strict=True)` with no password argument. A PDF encryption marker alone no longer rejects a document: a source that this ordinary reader can open and read without credentials is admitted. The converter makes no explicit decryption call, supplies no reader password, changes no PDF permissions/protection, and has no alternate-reader or parser-repair retry. Ordinary accessibility is not rights clearance or permission to redistribute.

`source_access` records `opened_without_credentials` and the reader's `is_encrypted` marker; it makes no claim that every page yielded text. `page_status_counts` always lists extracted, unresolved-no-text, and failed page counts, including zeros, in preparation and review artifacts. A known page whose retrieval or text extraction fails retains its page number, empty text hash, `extraction_failed` status and stable error; it receives no request. Even an all-failed or all-no-text preparation can complete as an explicit unresolved inventory with zero requests, never as successful text/semantic coverage.

Sources that actually need a password fail with `pdf_password_required`. Unreadable source structure fails with `pdf_unreadable` or `pdf_page_inventory_unreadable`; an unavailable reader dependency has its own error. The worker's failed `extraction.json` and preparation `failure.json` retain the stable code, and no successful `result.json`, bundle or requests are emitted. Child interruption/timeout remains `pdf_extraction_process_failed` instead of being guessed to mean password protection. Per-page password/dependency failures remain explicit and never trigger a credential attempt.

Chunks are deterministic, nonoverlapping, exhaustive fixed Unicode-code-point slices of each successfully extracted page, default 4,000 characters (admitted range 256–8,000). They may cut sentences; no contextual stitching, cross-page event synthesis or complete-event recall is claimed. No-text/failed pages have no inference request and remain visible in the page denominator. Requests bind original PDF bytes, page text, chunk span/text, schema, prompt and extractor metadata. Request identity hashes the complete request body before its own ID is added; the artifact inventory separately hashes its full serialized bytes.

The same PDF/extractor policy and version/chunk size/schema/prompt yields identical `bundle.json` and request bytes. Invocation UUIDs and result hashes intentionally differ. Byte compatibility is not claimed across converter versions. This is the new pipeline's own lifecycle, not a claim to reuse an unavailable historical ingestion implementation:

1. Each command requires a fresh exclusive output directory and creates `invocation.json` with `status=started`.
2. A completed command writes `result.json` last, binding operation, invocation, inputs and every artifact's bytes/hash.
3. Errors write `failure.json` when possible and never a successful result manifest. Crash/interruption may leave only partial files; do not reuse that directory.
4. Import requires an independently retained preparation result pin. Review requires the selected import result pin and revalidates both artifact chains, schemas/prompts and copied snapshots. Do not read a pin blindly from an untrusted incoming artifact and call it continuity.
5. Existing output directories are never overwritten or resumed. Use a new directory for a reviewed new invocation. There is no stale-lock recovery, output selection by modification time, hidden retry or latest-result alias.

Hashes establish consistency with a selected pin, not authenticity, authority, model identity or proof of human review. Coherently regenerated artifacts under newly selected pins are new declarations. Work in private, trusted local directories; this is not a hostile multi-user filesystem sandbox.

## Import outcomes and denominators

A successful import exit means the import operation completed, **not** that responses were valid. Check its `denominators` and the review queue. Every planned request appears exactly once independently of index entries:

- `structurally_valid_unadjudicated`: original JSON, schema, exact bindings and locations passed; no semantic credit
- `attempt_failed`: a declared attempted failure, without a candidate
- `rejected_capture`: malformed, duplicate, missing, inconsistent, out-of-scope or otherwise invalid evidence; no candidate
- `unattempted`: no declared attempt for that planned request

`planned`, `attempted`, `unattempted`, `structurally_valid`, `rejected` and `failed` are retained. Attempted and unattempted partition planned units. Rejected entries can include a contradictory declared-unattempted row; rejected is a validation outcome, not a separate partition that should be added to attempted. Unknown IDs and duplicate index entries remain in a separate original-capture/rejection inventory; they never expand or shrink the expected-request denominator. Duplicate responses are all retained/rejected rather than selecting a winner. A `response_path` attached to a declared unattempted row conservatively counts attempted and rejects the contradiction.

Original index bytes are retained before strict parsing. Original response bytes, including malformed JSON, are copied before schema validation. Strict parsing rejects duplicate decoded keys, trailing data, invalid UTF-8/scalars, BOMs, nonfinite/overflowed numbers, excessive depth and unknown properties. Unsafe/unavailable/oversized captures cannot be copied; their exact failure remains explicit. No repaired response replaces an original. A malformed index stops the operation with its original bytes and a failure record, not a successful denominator report.

## Bounds and limitations

- Input PDF: 32 MiB, 1–500 pages; actual password-required or ordinary-reader-unreadable sources reject, even when some encrypted-marked sources are readable
- Native text: 1 MiB per page, 8 MiB total; per-page extraction errors stay explicit
- PDF extraction child: 60-second parent deadline, 45-second CPU limit, 768 MiB address-space limit; no inherited environment and suppressed parser diagnostics
- At most 2,048 prepared requests and 4,096 index entries
- Index: 1 MiB; each response: 1 MiB; retained responses: 32 MiB total
- JSON/artifact write cap: 32 MiB; oversized aggregate HTML/JSON fails explicitly rather than truncating a success artifact

Resource limits bound extraction but do not constitute a native-code security sandbox. No OCR engine, encrypted-document password, page rendering, visual verification, automatic repair, provider receipt verification, legal clearance, independent human review, timed-user test or generalization study is included. Image-only documents remain unresolved. Native text ordering can differ from visual reading order. A model can omit or misinterpret source events even when all structural checks pass.

Concurrent filesystem changes, output-directory races and concurrent source replacement have not been independently revalidated. The current functional suite explicitly skips two filesystem-only checks, including in hosted execution. Functional passes are not a security audit or security certification; use private, trusted local directories.

## Engineering checks

Use `make test` and `make run` as documented in the [canonical guide](../../README.md). This candidate's assembled runtime remains unverified. Authored controls cover malformed sources/captures, readable encryption markers, genuinely password-required synthetic fixtures, per-page failures, complete unresolved inventories, deterministic identities and answer-ineligible review. The two existing filesystem-only skips remain explicit.

The owned demo performs zero inference. Its outputs are engineering conformance material, not model quality, human gold or user-benefit evidence. The review is a noninteractive local HTML/JSON packet with no scripts or external resources. Sharing it shares the complete original source and retained captures.

For advanced use in an already prepared Python 3.12 Linux environment with the pinned dependencies, run `compatibility_diagnostic.py` from this component directory with `--pdf` and an independently retained `--expected-sha256`. The diagnostic emits only status, counts and hashes; it cannot establish redistribution rights, visual correctness or semantic accuracy. It is not part of the default demonstration and has not been newly executed here.
