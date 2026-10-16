# OpenParlData PDF Review

Track 2A, OpenParlData. Entrant and team: **Sumit Aswal**.

A source-bound parliamentary PDF preparation and review pipeline: prepare native text, capture an Apertus response through a separate adapter, strictly import the original, and inspect the candidate beside its evidence. Separate event and outcome fields help a reviewer distinguish proposals, recommendations and adopted outcomes.

**Start here: [run and review guide](track_2a/README.md).** The intended first command is `make run` from the repository root. It builds a Docker-based, owned synthetic demonstration with zero model calls; this assembled runtime has not yet been verified.

- [Six-page technical report](track_2a/Sumit_Aswal_Report.pdf) and [text version](track_2a/technical_report.md)
- [Current evidence gaps](track_2a/docs/RELEASE_GATES.md) and [exact verification checklist](track_2a/docs/REMAINING_TESTS.md)
- [Source provenance](SOURCE_PINS.json), [current file manifest](CANDIDATE_MANIFEST.json) and [data scope](track_2a/data/README.md)

## Evidence status

This is a documentation-cleaned successor to the 73-file release candidate, itself assembled from the reviewed 56-file source baseline. Executable code, tests, prompts, schemas, dependency locks and historical evidence are unchanged. Existing checks establish static identity and mocked capture-component behavior only. Real-PDF/provider execution, clean-checkout Docker verification, actual manually checked multilingual/multilevel references and a supported real comparison with baselines remain open. All candidates remain unadjudicated and answer-ineligible.

[Public repository](https://github.com/sumit1717/openparldata-pdf-review-hack-apertus): source publication is verified at [a1c596d](https://github.com/sumit1717/openparldata-pdf-review-hack-apertus/commit/a1c596d5552e519b838684ae2d04d7817fbe2062), following template starter `58272f3575871c894a9dbe381319c86fded26223`. Submission remains pending. Public visibility is verified through repository metadata; anonymous rendering is unverified. Original development history remains private.

## Licensing

Original code/build configuration: Apache-2.0. Original documentation, prompts and report: CC-BY-4.0. Authored synthetic data: CDLA-Permissive-2.0. Third-party material retains its own terms. See [LICENSE_POLICY.md](LICENSE_POLICY.md), [NOTICE](NOTICE) and [dependency attribution](track_2a/docs/DEPENDENCIES_AND_ATTRIBUTION.md). No real parliamentary corpus or provider capture is redistributed. AI assistance is disclosed and is not manual-human gold.
