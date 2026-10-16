# Optional one-request Apertus capture bridge

This source-only candidate supplies the missing transport between the existing
generic PDF converter's preparation and original-capture import. It does not
replace or alter converter 0.2.0, its prompt, its schema, the historical R11/R12
seven-field protocol, or any recorded model response. No provider call has been
made to validate this candidate. A human-checked reference set is still missing.

Importing `apertus_capture`, running `inspect`, and the default offline demo make
zero provider calls. Only the separate, explicit `send` command may make one call.
Do not add it to default demos, offline CI, an automatic import, or a retry loop.
No installation, paid-service setup, new credentials, or credential-store lookup
is implemented. An authorized operator supplies an existing key through an
approved runner's existing process environment or a private local terminal;
the assistant must not obtain or transmit that key through chat/tools.

The template interface is deliberately constrained. If present, `LLM_NAME` must
be exactly `swiss-ai/Apertus-v1.5-70B`. `LLM_BASE_URL` must be exactly
`https://api.inference.cscs.ch` or `https://api.inference.cscs.ch/v1`, optionally
ending in one slash. Missing selectors use those fixed defaults. Other models,
origins, schemes, userinfo, explicit ports, queries, fragments, paths, whitespace,
or doubled trailing slashes reject before credential access. These variables
never change the fixed `/v1/chat/completions` destination.

Only the explicit `send` command reads an existing process `LLM_API_KEY`, after
validating public configuration and the preparation. It never configures,
modifies, prints or writes that value. An absent variable uses private getpass;
a present blank value cancels, and a present invalid value fails without fallback.
`inspect` and `verify` never read the key. No dotenv file, keychain, key file,
command-line key flag or subprocess credential propagation is supported. Source
and mock interface compatibility is tested; actual runner/provider acceptance
and submission readiness remain unverified.

## Exact compatibility contract

- The installed converter's pipeline, prompt and schema are pinned to the reviewed
  0.2.0 bytes listed in `capture.py`. A converter update requires a new review.
- `load_prepared(prepared, independently_retained_prepare_result_sha256)` checks
  the full artifact inventory, source PDF identity, pages, schema/prompt bindings,
  extractor policy, and every reconstructed request. No PDF is parsed here.
- Exactly one selected request is sent. The system message is the unchanged
  prepared prompt. The user message is a JSON object with
  `required_output_schema` equal to the prepared schema and `request` equal to
  the complete prepared request. The exact prepared request/schema/prompt bytes
  and the exact new wire bytes are retained separately. Wire serialization is
  not described as an untouched prepared-file byte stream.
- Fixed destination: `https://api.inference.cscs.ch/v1/chat/completions`.
  Fixed model: `swiss-ai/Apertus-v1.5-70B`; temperature 0, nonstreaming,
  maximum 4,096 output tokens, 90-second total transport deadline, 128 KiB
  wire request limit, 1 MiB response-body limit. No configurable endpoint/model,
  automatic retry, redirect, proxy-environment routing, fallback, or batching.
- A private, deterministic `PREPARE_PIN-REQUEST_ID` attempt directory is created
  and durably reserved before sending. A crash or uncertain transport outcome
  leaves the reservation in place. Never delete it to retry or select another
  store to evade it. This is local at-most-one-attempt behavior within that
  capture store, not a global deduplication service or provider idempotency.

The provider API's acceptance of this generic wire request is untested. Failure
must remain a failure; do not change models, reroute, or silently adapt responses.
The token cap may truncate complex chunks. A `length` finish remains failed;
this bridge does not repair or automatically resend it.

## Custody and conservative failures

The private store must be owned by the operator and mode 0700. New files use
mode 0600 and exclusive, no-follow, fsynced writes. Existing attempts are never
overwritten or resumed. Work only in trusted private local directories; these
checks are not a hostile multi-user filesystem or native-code security sandbox.

The complete response body is retained as `response.original.bin` before strict
JSON parsing, subject to bounds and secret screening. Incomplete, compressed,
non-UTF-8, NUL-containing, oversized or possible credential-echo bodies are
withheld completely and explained in the receipt. A withheld body is never
represented as a retained original. No partial body is written and no redacted
replacement is substituted. Screening covers the exact key and common reversible
encodings, not every possible adversarial encoding. Python cannot promise key
erasure from RAM or OS swap. Core dumps are disabled in the interactive CLI;
exception/provider text and HTTP debug logs are never printed.

The envelope must be strict JSON, identify the fixed model, contain one indexed
assistant choice, finish with `stop`, have no refusal/tool call, and carry sane,
consistent integer token counts within the output limit. Successful metadata
checks only permit extracting the exact decoded string at
`choices[0].message.content`, encoded as UTF-8 without any stripping, code-fence
removal, normalization, JSON reserialization, schema repair or semantic repair.
That file is named `assistant-content.decoded.utf8` and explicitly labeled as a
derivative of the raw envelope, not raw HTTP bytes. Strict JSON decoding is the
only envelope-to-content transformation.

`index.json` uses the unchanged converter profile and exact entry shape:
`{profile, prepare_result_sha256, entries}`. One entry is either `captured` with
the decoded-content relative path or `failed` with a bounded error code. Other
prepared requests are omitted and remain unattempted in the converter's complete
denominator. A malformed candidate string can be captured faithfully and then
rejected by the unchanged importer. Successful transport metadata never implies
candidate-schema validity, accurate extraction or semantic correctness.

The receipt binds the planned index bytes and is written durably first. Its
readback, retained originals, envelope/content derivation and held index bytes
are verified before the final `index.json` is published as the last artifact.
A receipt-write failure or failed verification therefore leaves no final index
for the unchanged importer to consume. Original evidence and the reservation
remain; no retry or automatic repair follows. An index-write failure leaves an
incomplete capture that cannot pass full custody verification.

Save the printed receipt SHA-256 independently and run `verify` before import.
Verification checks the exact inventory, every file hash,
the strict envelope gate and the byte-for-byte assistant-content derivation.
An index by itself is only a declaration: the unchanged converter does not
independently verify provider receipts. Hashes establish consistency with a
chosen pin, not authenticity, model identity, legal authority, proof that a call
occurred, charges, or human review. A reservation without both the verified
receipt and final index, or any failed custody check, is not import-ready and
must never be automatically resumed.

## Future authorized local execution

These commands are documentation, not evidence that they have run. First follow
the [canonical run guide](../../README.md) for preparation and the standard
offline route. For the advanced module commands below, use an already prepared
Python 3.12 Linux environment with the pinned converter dependencies, and change
from the repository root into `track_2a/src`:

```sh
cd track_2a/src
```

The converter and this package are then beside one another on the Python path.
These commands do not set up an account or install software. The offline Docker
launcher remains separate and must not gain provider access. This README's path
guidance was updated for the isolated release; implementation and historical
component test records remain unchanged.

First prepare the PDF using the existing converter through its separately
authorized workflow. Independently retain its successful preparation pin.
Inspect one exact request without a credential prompt or network:

```sh
python -m apertus_capture inspect \
  --prepared /private/work/prepared \
  --expected-prepare EXACT_INDEPENDENT_PREPARE_RESULT_SHA256 \
  --request-id EXACT_PREPARED_REQUEST_ID
```

Before sending, a human must approve transmitting this exact source text to
CSCS and any applicable charge. No no-cost execution claim is made. Protect
the input and output directories; their content can include sensitive source
text. Never put a key on a command line, in a config file, logs, a real-key test
fixture, a repository, or a chat. The local path prompts privately. An approved
runner may instead supply an already configured process `LLM_API_KEY`; this
package neither configures nor persists it. Protect that runner and environment,
which can be visible to other sufficiently privileged processes. Both routes
require POSIX support; only the private prompt requires a terminal:

```sh
python -m apertus_capture send \
  --prepared /private/work/prepared \
  --expected-prepare EXACT_INDEPENDENT_PREPARE_RESULT_SHA256 \
  --request-id EXACT_PREPARED_REQUEST_ID \
  --out-parent /private/work/captures
```

Entering a blank key or a present blank `LLM_API_KEY` cancels. This command performs at most one POST and prints
only fixed diagnostics and a receipt pin. Retain that pin outside the capture
directory. A network failure does not establish that the provider did nothing
or incurred no charge. Inspect the result instead of retrying.

```sh
python -m apertus_capture verify \
  --capture /private/work/captures/PREPARE_PIN-REQUEST_ID \
  --expected-receipt EXACT_INDEPENDENT_RECEIPT_SHA256 && \
python track_2a_converter/pipeline.py import \
  --prepared /private/work/prepared \
  --expected-prepare EXACT_INDEPENDENT_PREPARE_RESULT_SHA256 \
  --index /private/work/captures/PREPARE_PIN-REQUEST_ID/index.json \
  --out /private/work/imported
```

Save the import result pin and use the unchanged converter `review` command.
All imported candidates remain unadjudicated and answer-ineligible. This bridge
does not produce human gold, extraction-quality scores, complete-document
coverage, or submission readiness. Preserve raw envelope/receipt custody with
the review evidence even though the converter review copies only the indexed
assistant-content bytes. Sharing a capture directory shares source material;
obtain the required permission first.

## Engineering verification scope

Tests use authored inert byte/JSON inventories, including a nonparsed placeholder
PDF header. They do not run the PDF parser, prepare/extract workflow, app server,
native engine, model, real provider transport, dependency install or paid service.
The pinned existing kernel socket-denial launcher is combined with the existing
Python socket/process audit guard. Pure mocked HTTP objects also exercise the
transport implementation without opening any socket. Direct function tests of
the unchanged importer verify failed/unattempted counts, malformed original
retention and unadjudicated status. These are contract checks, never real-PDF,
provider, model-quality or human-validation evidence.

The retained component manifest and test logs describe the original source/mock
review, including this README before its layout clarification. They remain
unchanged historical records. The [current release manifest](../../../CANDIDATE_MANIFEST.json)
records this documentation adaptation; it does not claim a new test or provider run.
