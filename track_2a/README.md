# OpenParlData PDF Review: run and review guide

Entrant and team: **Sumit Aswal**. This is the canonical command guide for the isolated Track 2A release. The [six-page report](Sumit_Aswal_Report.pdf) describes the implemented contribution and evidence limits.

The pipeline prepares native PDF text, binds chunk requests to source/prompt/schema hashes, imports unchanged captures under strict checks, and exports source-first review packets. Its comparison worksheet asks: **What was proposed or recommended, and what substantive decision is actually evidenced?** A quotation locates evidence; it does not establish entailment. Every current candidate remains unadjudicated and answer-ineligible.

## 1. Run the owned offline example

Prerequisites: Docker with a Linux amd64 engine/image target, Make, a POSIX shell and a non-root host account. No host Python or GPU is required. Initial image build needs the official Python image and package registry. Runtime is unprivileged, network-disabled and read-only except its dedicated output parent and temporary directory; no model key is forwarded.

From either the repository root or `track_2a/`:

```sh
make run
```

Intended outputs under `track_2a/artifacts/demo/`:

- `synthetic-source.pdf`: a newly authored three-page source
- `prepared/` and `captures/`: source-bound requests and authored original responses
- `imported/`: strict import accounting and retained malformed originals
- `review/review.html`: the source-first review packet

Open `review/review.html`. Inspect the unresolved empty-text page, one structurally valid unadjudicated authored candidate, and one deliberately malformed original. These are synthetic engineering controls, with zero inference. **No generated output is shipped, and this assembled Docker route has not yet run.**

Existing outputs are never overwritten. To repeat with a fresh name or view the two-source question worksheet:

```sh
make run OUTPUT_NAME=demo-second
make comparison-demo OUTPUT_NAME=two-packet-example
```

The comparison output is intended at `track_2a/artifacts/two-packet-example/worksheet/worksheet.html`. It contrasts a synthetic committee recommendation with an agenda decision; its baselines are unknown and manual review is not started. It is not a real cross-parliament finding.

## 2. Verify the assembled release

```sh
make build
make test
```

These are verification instructions, not execution receipts. `make test` includes converter tests, the scoped worksheet suite and guarded Apertus mock checks. Two historical-ledger worksheet tests are explicitly skipped because their source-bearing dataset is not distributed; existing converter filesystem-only skips also remain disclosed. See [the exact checks and expected boundaries](docs/REMAINING_TESTS.md), including repeat-output, mount, PDF and malformed-capture cases. Component mock results do not establish a clean-checkout product pass.

## 3. Prepare a separately acquired PDF

Use an input whose access and intended processing are authorized, in private trusted directories. This launcher is not a hostile-filesystem security boundary. Input paths must be absolute and contain no commas/newlines. Writable output parents must be separate from inputs and source code; inside this repository only `track_2a/artifacts` is permitted. Keep an import index in a dedicated capture-only directory because its entire parent is mounted read-only. Create private output parents first.

```sh
make prepare PDF=/private/inputs/source.pdf \
  OUTPUT_ROOT=/private/preparation-output OUTPUT_NAME=prepared
```

Retain the printed `result_sha256` independently. Preparation includes exact `source.pdf`, `bundle.json`, `requests/`, `prompt.txt` and `response.schema.json`. Do not adopt a pin solely because it appears inside an untrusted incoming bundle. Native-text gaps remain unresolved; no OCR or visual interpretation is supplied.

## 4. Capture separately, then import and review

The optional [Apertus capture guide](src/apertus_capture/README.md) documents its separate `inspect`, explicit one-request `send` and receipt `verify` commands. It supports constrained `LLM_NAME`, `LLM_BASE_URL` and `LLM_API_KEY` configuration; its fixed model is `swiss-ai/Apertus-v1.5-70B`. Actual provider availability, entitlement and wire compatibility remain unverified. The default Docker launcher has no provider route.

Before any transmission, establish the authorized destination, source scope and applicable cost/rights approval. Before import, verify the adapter receipt against an independently retained receipt pin. The generic importer does not authenticate provider custody. Historical fixed-input Apertus captures use a different contract and are not interchangeable with this converter.

For captured originals, the index uses this exact profile, the independently retained preparation pin and one entry per declared attempt. Uppercase values below are placeholders:

```json
{
  "profile": "formrehearsal-pdf-review-1",
  "prepare_result_sha256": "EXACT_INDEPENDENT_PREPARATION_PIN",
  "entries": [
    {"request_id": "EXACT_PREPARED_REQUEST_ID", "status": "captured", "response_path": "request-1.original.json"}
  ]
}
```

Failed entries use `status: failed` with a bounded lowercase `error_code`. Explicitly unattempted entries contain only `request_id` and `status`; omitted planned requests remain unattempted. Preserve original assistant content without trimming, repair or replacement. Authored examples are not provider captures.

```sh
make import PREPARED=/private/preparation-output/prepared \
  INDEX=/private/captures/index.json EXPECTED_PREPARE=EXACT_PREPARATION_PIN \
  OUTPUT_ROOT=/private/import-output OUTPUT_NAME=imported

make review PREPARED=/private/preparation-output/prepared \
  IMPORTED=/private/import-output/imported EXPECTED_IMPORT=EXACT_IMPORT_PIN \
  OUTPUT_ROOT=/private/review-output OUTPUT_NAME=review
```

Retain the successful import pin independently for `EXPECTED_IMPORT`. Inspect `review.html`, `review-queue.json`, original captures, page counts and denominators. A completed import can contain only rejections; command success is not accuracy or evidence of a genuine provider call. Sharing a review packet also shares its original PDF and response content and needs the appropriate permission.

## Reference and release status

- [Converter contract and limits](src/track_2a_converter/README.md), [comparison contract](src/track_2a_comparison/README.md) and [capture contract](docs/APERTUS_CAPTURE_CONTRACT.md)
- [Open evidence gates](docs/RELEASE_GATES.md), [data scope](data/README.md) and [licenses](../LICENSE_POLICY.md)
- [Historical failures](docs/HISTORICAL_FAILURES.md) and [historical system prompt](docs/prompts/historical-apertus-system.txt), retained solely as separate-protocol provenance

The required layout follows [the pinned official template](https://github.com/HackApertus/project-template/tree/09f8e9e2b588db3325869b23c6d5132f5c3756f7). The challenge requires an Apertus-based solution; the offline example alone does not meet that requirement. The [public repository](https://github.com/sumit1717/openparldata-pdf-review-hack-apertus) contains the source release published at [a1c596d](https://github.com/sumit1717/openparldata-pdf-review-hack-apertus/commit/a1c596d5552e519b838684ae2d04d7817fbe2062); final submission remains pending. Public visibility is verified through repository metadata; anonymous rendering is unverified. The required manually checked semantic reference is still missing.
