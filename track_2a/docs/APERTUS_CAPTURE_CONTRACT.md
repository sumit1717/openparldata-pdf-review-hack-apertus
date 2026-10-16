# Compatible Apertus capture contract

The optional source adapter lives at `../src/apertus_capture/`. Its [README](../src/apertus_capture/README.md) and exact pinned implementation are authoritative for commands and bounds. No real request, key access, native/PDF engine, provider result or paid service has been executed to validate it. The standard Docker demo stays offline; the capture route is separate and requires its own authorized execution.

## Exact pipeline boundary

The adapter verifies converter 0.2.0 pipeline/prompt/schema hashes, then calls the unchanged `load_prepared(prepared, independently_retained_prepare_pin)`. It selects exactly one verified request. The system message is the exact prepared prompt; user content is a JSON object containing `required_output_schema` and the complete prepared `request`. It retains exact prepared bytes separately from the derived serialized wire request. No gold, target quotation, repair example or expected answer is inserted. The historical H03/H04/H08 fixed-input runner is not used or translated.

The provider destination remains `https://api.inference.cscs.ch/v1/chat/completions`; model `swiss-ai/Apertus-v1.5-70B`; temperature 0; nonstreaming; 4,096 output tokens maximum; 90-second total transport deadline; 128 KiB wire request and 1 MiB response-body caps. There is one explicit attempt, no automatic retry, redirect, proxy routing, fallback or batching. Token limits do not establish a price guarantee or free account entitlement.

## Template environment interface

- `LLM_NAME`, if set, must be exactly `swiss-ai/Apertus-v1.5-70B`.
- `LLM_BASE_URL`, if set, must be exactly `https://api.inference.cscs.ch` or `https://api.inference.cscs.ch/v1`, optionally with one trailing slash. Missing selectors use the fixed defaults. Alternate origins, paths, ports, userinfo, queries, fragments or whitespace reject before key access.
- Only explicit `send`, after public configuration/preparation validation, reads an existing process `LLM_API_KEY`. It does not persist, print or configure the value. If absent, an authorized operator may use private getpass. A blank value cancels; invalid present values fail without fallback. `inspect`, `verify`, imports and default offline commands never read the key.

There is no credential-store lookup, dotenv reader, key file, command-line key flag or new credential creation. The assistant must not obtain or transmit keys through chat/tools. Interface source/mock testing does not establish actual runner/provider acceptance. The default offline launcher forwards none of these variables.

## Custody, failure and import

A deterministic preparation-pin/request-ID directory is reserved durably before transmission. It is never overwritten or resumed. Transport uncertainty leaves an attempted failure and a reservation; it is not safe evidence for retry. This is local at-most-one-attempt behavior within the selected store, not provider-side idempotency or global deduplication.

Complete credential-safe response-body bytes are retained before parsing. Incomplete, compressed, non-UTF-8, NUL-containing, oversized or possible credential-echo bodies are explicitly withheld rather than redacted into a pretend original. Screening does not prove protection against every possible encoding. The strict envelope must identify the fixed model, exactly one indexed assistant choice, ordinary `stop`, no refusal/tool call and coherent known bounded integer usage. Provider usage is not billing proof.

The exact decoded assistant string is written as UTF-8 without trimming, code-fence removal, normalization, repair or offset correction. It is labeled a decoded derivative of the preserved raw envelope. Malformed candidate JSON can be captured faithfully and rejected by the unchanged importer. Transport or valid envelope metadata does not admit a candidate semantically.

Finalization binds exact file inventory and hashes in a receipt. The converter-compatible `index.json` becomes available only after durable receipt creation and successful verification; failure must not leave an import-ready index. Before any generic import, explicitly run adapter `verify` against the independently retained receipt pin. The generic importer alone does not authenticate provider custody.

The index remains exactly `{profile, prepare_result_sha256, entries}`, profile `formrehearsal-pdf-review-1`. A selected entry is `captured` with a decoded-content relative path, or `failed` with a bounded error code. Unselected requests stay unattempted in the unchanged converter denominator. Pass the original independent preparation pin to import. All accepted structural candidates remain unadjudicated and answer-ineligible; provider receipts cannot create human gold or semantic-accuracy credit.

## Testing boundary

The adapter's source tests use authored inert JSON/byte inventories and mocked HTTP, key/terminal and configuration paths. No placeholder PDF is parsed. See `GUARDED_TESTS.md` for the unchanged kernel socket-denial plus Python process/socket audit route. The assembled image, real provider acceptance, actual PDF chain, human references, rights, publication and final submission remain outstanding even if those pure tests pass.
