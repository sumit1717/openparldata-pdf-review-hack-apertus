# OpenParlData PDF Review

Track 2A Technical Report

**Entrant and team:** Sumit Aswal
HackApertus Online | 16 October 2026 | Partial engineering result | Six pages

### Summary

OpenParlData PDF Review is a source-bound parliamentary extraction and review pipeline. It prepares local PDFs, constructs bounded Apertus requests, imports original responses under strict evidence checks, and presents candidates for review. Its central design rule is that a proposal, a recommendation and an adopted outcome must remain distinguishable. Missing evidence and conflicting statements stay visible. [1-3]

The contribution currently established is **implemented source, a documented schema and tested capture-component contracts**. The isolated candidate has not completed a real-PDF-to-Apertus-to-review run, a clean-checkout Docker run or evaluation against a manually checked multilingual and multilevel reference. No semantic-accuracy or user-benefit result is claimed. [2-4]

### Problem and intended use

A civic-data editor needs to know who acted, on which affair, at what procedural stage, and what the evidence actually supports. Public parliamentary material mixes proposals, committee recommendations, agenda events, decisions and reported outcomes. Treating every positive status or vote as policy adoption risks changing its meaning. The intended workflow helps a reviewer inspect a bounded candidate and its source before deciding whether it can support an answer.

The project does not assume that the OpenParlData API lacks these facts. Earlier authored Federal, Ticino and Vaud comparisons found that complete API retrieval already supplied important procedural facts. Those separate, exposed exhibits motivate stage-aware representation and fair baselines; they are not automatic extraction results or evidence of an incremental model benefit. [5]

### What is included

| Component | Current contribution |
| --- | --- |
| Preparation | Bounded native-text extraction, exact source retention and complete page accounting. |
| Representation | Seven candidate fields, explicit uncertainty states and page-text evidence locations. |
| Apertus adapter | One-request capture with fixed destination, original-response retention and verified receipts. |
| Review | Strict import ledger, offline source-first HTML and a bounded comparison worksheet. |

This report covers the 73-file release, derived from a reviewed 56-file source baseline. The source release is published; submission remains pending. [4]

---

## Representation and source evidence

### PDF preparation

Converter 0.2.0 accepts a local PDF up to 32 MiB and 500 pages. It retains the original bytes and SHA-256, extracts native text with pinned pypdf, and records every page as text_extracted, no_text_unresolved or extraction_failed. A subprocess limits extraction time, CPU and address space. Text is not normalized; OCR and visual interpretation are not implemented. Empty native text does not establish that a page is blank. [2]

Nonoverlapping fixed-size chunks use half-open Unicode-code-point offsets into each page's decoded text. Every prepared request binds the source bytes, page text, chunk, prompt, response schema and extractor metadata. A preparation receipt must be retained independently; accepting a pin solely from an untrusted incoming bundle would weaken the binding.

### A bounded common contract

| Candidate field | Distinction retained |
| --- | --- |
| source_type and affair | Document role and parliamentary affair are separate. |
| author | Who authored the source or proposal. |
| actor and addressee | Who acts, versus whom a request addresses. |
| event and outcome | What happened, versus what result is actually evidenced. |

Each field distinguishes present, explicit_absence, not_stated_within_reviewed_scope, unassessed, not_applicable and conflicting. Conflicting alternatives carry their own evidence. A local not-stated finding does not imply document-wide absence. An empty events array does not establish that the PDF contains no event. The versioned contract is deliberately narrower than a universal parliamentary ontology. [2]

### Strict import and review

Import rejects duplicate JSON keys, non-finite numbers, unknown fields, invalid types, changed bindings, wrong pages and quotes that do not match their exact offsets. Boolean values cannot masquerade as integers. Safely readable malformed originals are retained. Planned requests remain in the denominator, including failed and unattempted units. [2, 3]

The escaped, offline HTML shows source evidence and a review queue. Every structurally accepted candidate remains **unadjudicated** and **answer_eligible=false**. An exact quotation establishes a location, not entailment; an incorrect actor can still be paired with real source words. The current workflow does not automatically admit facts after capture or invent a human adjudication.

Structure limits: fixed chunks can split sentences; cross-page event synthesis, image/table interpretation and annex completeness are unestablished. Hashes prove consistency of selected bytes, not source authority, legal rights or semantic correctness.

---

## Apertus integration and reproducibility

### Source bound request

The optional adapter targets **swiss-ai/Apertus-v1.5-70B** at https://api.inference.cscs.ch/v1/chat/completions. It verifies the exact converter, prompt and schema hashes, loads a preparation using its independently retained pin, and selects one request. The system message is the prepared prompt; user content contains the required schema and complete prepared request. No gold answer, expected quotation or repair example is inserted. [3]

| Setting | Implemented bound |
| --- | --- |
| Generation | Temperature 0; nonstreaming; maximum 4,096 output tokens. |
| Transport | One explicit attempt; 90-second total deadline; 128 KiB request and 1 MiB response-body caps. |
| Routing | Fixed HTTPS endpoint/model; no automatic retry, redirect, proxy, fallback or batching. |
| Configuration | Constrained LLM_NAME and LLM_BASE_URL; key access only during explicit send. |

### Original response custody

Before transmission, the adapter durably reserves a preparation-pin/request-ID directory. It cannot overwrite or resume that attempt. Transport uncertainty remains an attempted failure; local reservation is not provider-side idempotency. Complete response-body bytes are retained when safe. Incomplete, oversized, compressed, invalid-text or possible credential-echo bodies are withheld with an explicit reason. Screening is not a guarantee against every secret encoding. [3]

Envelope checks require the fixed model, one assistant choice, ordinary stop, no refusal/tool call and coherent bounded integer usage. The decoded assistant string is saved without trimming, normalization, fence removal or repair, and labeled as a derivative of the original envelope. Reported usage is not billing proof. An import index is published last, after the durable receipt and originals verify.

The operator must explicitly verify that receipt against an independently retained pin before generic import. The ordinary importer does not authenticate provider custody. Successful transport, envelope validation and structural import are separate gates; none grants semantic correctness or human-reference status.

### Intended reproducible runtime

Root make run delegates to Track 2A and is intended to build a pinned Linux amd64 Python 3.12.14 image with hash-locked dependencies, then run an owned synthetic PDF and authored-capture demonstration. Runtime is specified as non-root, network-disabled and read-only except dedicated output and temporary storage. The live adapter is separate. This exact Docker wiring has not run; no GPU is required for the offline route. [2, 4]

---

## Engineering results and historical failures

### Source baseline and assembled release

| Evidence | Observed result and boundary |
| --- | --- |
| Reviewed source baseline | 56 files and ZIP readback verified: 20 upstream pins, 5 adapter files, 4 guard files, 21 Python syntax trees and 7 strict JSON files. Baseline data directory: 1,025 bytes. |
| Assembled release | 73 files; 21 Python ASTs and 9 JSON files checked. 33 core files match the prior release byte-for-byte. Static-only; no project execution. |
| Authored adapter tests | 38 passed in normal Python; the same 38 passed in optimized Python. Relocation repeated the same 38. These are not 114 unique tests. |
| Independent mock checks | 20 adversarial JSON/file/mock checks passed, including receipt failure, tampering and import-index finalization cases. |
| Full execution and evaluation | No candidate PDF/native extraction, Docker or provider workflow executed. No manually checked semantic reference or measured task benefit. |

The retained component tests used the pinned kernel socket-denial and Python process/socket-audit route, authored inventories and mocked transport. No real keys, PDF parsing or model output were used. Repeated mock runs and new static checks do not establish real wire compatibility, runtime behavior or extraction quality. [3, 4]

### Preserved actual model failures

Earlier fixed-input experiments used a different contract. Two H03 Apertus 8B cohorts each planned three units, attempted one and admitted zero after strict JSON failure; two units remained unattempted. Exposed H08 runs R11 and R12 each attempted one case and admitted zero. These historical failures are not evaluations of this generic converter. [5]

| H08 observation | R11 | R12 |
| --- | --- | --- |
| Completion cap / reported tokens | 1,024 / 1,024 | 2,048 / 895 |
| Terminal evidence | length; truncated | stop; quote mismatch |
| Admitted cases | 0 of 1 | 0 of 1 |

R12 used Apertus v1.5 70B and passed schema, but two of eleven evidence occurrences claimed [138,193) while their quotation occupied [138,159). Nine matches did not admit the candidate; it stayed unmapped and answer-ineligible. No repair or recredit followed. Provider-reported usage was 2,902 prompt plus 895 completion tokens. [5]

R11 and R12 changed prompt and cap together, preventing causal attribution. Private originals remain excluded; external auditability is limited to the historical summary and component evidence.

---

## Evaluation design and remaining limitations

### A reference that actually tests semantics

The challenge calls for a multilingual, multilevel sample evaluated against manually checked gold. That reference is still missing. Agent-authored labels, synthetic fixtures and AI review cannot satisfy a manual-human requirement. No numerical minimum, mandatory two-reviewer rule or fixed gold-file format is asserted here. A small sample should disclose its languages, government levels, selection method, reviewer competence and any assistance. [1, 4]

Before evaluation, freeze rights-cleared sources and field/event reference judgments, including uncertainty and conflicts. Keep exposed development material separate from unseen cases. Record what each reviewer inspected and which language judgments they independently verified. If that coverage cannot be obtained, report an incomplete evaluation rather than relabeling authored material as gold.

### Metrics and a fair comparative question

For every cohort, report planned, attempted, ordinary-completion, structurally valid, rejected, failed and unattempted units separately. Compare field/event extraction with the manual reference, inspecting omitted events, wrong actors, recommendation/decision conflation, conflicting dates and unsupported outcomes. Keep abstentions, unresolved pages and partial coverage in declared denominators. Structural admission and semantic correctness must have different counts.

The proposed question is: **What was proposed or recommended across parliaments, and which substantive decisions are actually evidenced?** Retain baseline receipts for relevant API, search, official-page and manual-PDF routes before attributing any benefit to the converter. The included two-packet worksheet uses owned synthetic examples; it does not demonstrate a real cross-parliament answer. Existing authored examples often show API sufficiency. No superiority, time-saving or generalization estimate is available. [2, 5]

### Practical and safety limits

Image-only pages, failed extraction and missing annexes remain unresolved. Native reading order and fixed chunk boundaries can lose context. No OCR, visual-table reasoning, document-wide coverage guarantee or cross-page semantic merger is established. Resource bounds are not a hostile-PDF or hostile-filesystem security certification. Exact hashes and quotations cannot establish provider identity, legal rights or human review.

### Required evidence before a working submission claim

The remaining gates are fresh exact-candidate Docker build/run/test receipts; a genuine authorized real-PDF Apertus capture with unchanged strict import; actual manually checked language/level coverage; and a supported comparative question with baseline results. Two worksheet checks requiring excluded historical source data are explicitly skipped, and earlier converter filesystem-only skips remain disclosed. These limits must be carried into any fresh test report. [4]

The brief permits negative or partial insight, but no explicit converter/evaluation waiver was found. Packaging cannot close these evidence gates.

---

## Release scope and references

### Release and reproducibility record

The 73-file release extends the reviewed 56-file baseline with report and license/attribution files. Documentation cleanup preserves executable code, tests, prompts, schemas and locks. Licenses: Apache-2.0 code; CC-BY-4.0 documentation; CDLA-Permissive-2.0 authored data. Source publication is verified at a1c596d; original history stays private.

The release contains authored code, prompts, tests and synthetic recipes, with no real parliamentary PDF/text fixture or provider capture. Small historical identifiers and date assertions remain. Future real-source redistribution requires item-specific rights review. Original dependency notices are included; project licenses do not relicense those dependencies or parliamentary sources. [2, 4]

**56-file source-baseline manifest SHA-256:**
beebf6cd62cd83038ae0b57ebc5c1346bde85196a838ef10e030c7590f77d4f1
**56-file source-baseline archive SHA-256:**
41b7154662b5c31d51f4d0d82e911ac3e672ffe150ee043360860d433f6179cc

These are historical 56-file baseline hashes. The current 73-file inventory is CANDIDATE_MANIFEST.json; SOURCE_PINS.json records unchanged source and documentation derivatives. Template pin: 09f8e9e2b588db3325869b23c6d5132f5c3756f7. Root make run and make test remain unexecuted intended commands.

### References and evidence scope

**[1] Official challenge and submission requirements.** [Track 2A OpenParlData brief](https://hackapertus.notion.site/track-2a-openparldata); [submission portal](https://hackapertus.ch/online-hack/submissions); [pinned project template](https://github.com/HackApertus/project-template/tree/09f8e9e2b588db3325869b23c6d5132f5c3756f7). Retained read-only browser observations dated 15 October 2026; the selected form requires a PDF of at most six pages. This report has six total, including references. Requirements observations do not establish submission acceptance.

**[2] Assembled implementation.** track_2a/README.md; src/track_2a_converter/pipeline.py, prompt.txt and response.schema.json; src/track_2a_comparison/worksheet.py; root SOURCE_PINS.json and CANDIDATE_MANIFEST.json. Converter 0.2.0, prompts, schemas and executable code remain byte-identical; updated documentation describes the current layout. This establishes implementation, not execution.

**[3] Capture contract and component evidence.** track_2a/docs/APERTUS_CAPTURE_CONTRACT.md; src/apertus_capture/capture.py and README.md; docs/validation/dispatcher-component-manifest.json and normal, optimized and independent test logs. Adapter source SHA-256: f2244001e5304c9a3c68df72a2f8c637602f1f2826f6c70114698a76609a12cd. Mock tests do not authenticate real provider custody.

**[4] Review scopes and open gates.** track_2a/docs/RELEASE_GATES.md, REMAINING_TESTS.md and DEPENDENCIES_AND_ATTRIBUTION.md. Retained validation/assembly-static-check.json and the 15 October independent review concern the earlier source baseline. Current file hashes are in CANDIDATE_MANIFEST.json. Source publication at a1c596d is verified through repository metadata; anonymous rendering is unverified. No runtime or evaluation credit is added.

**[5] Historical context.** track_2a/docs/HISTORICAL_FAILURES.md summarizes the actual H03, R11 and R12 failures without redistributing source/capture text. The separate six-page report Linked parliamentary decisions, 13 October 2026, records the earlier authored API-linked exhibit. Its raw historical evidence remains private. Neither contract nor evaluation credit transfers to this candidate.

**Document license:** CC-BY-4.0. Credit: Sumit Aswal, OpenParlData PDF Review, 2026. [Public repository](https://github.com/sumit1717/openparldata-pdf-review-hack-apertus).
