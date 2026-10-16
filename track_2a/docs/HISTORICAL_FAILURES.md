# Historical Apertus failures: separate contracts and evidence

These historical observations do not establish execution of the generic converter or the newly assembled candidate. Private original source/capture text is not reproduced here. Source references below identify existing project evidence and may not be publicly accessible.

Earlier H03 8B runs `37759878285` and `37832819185` each planned three units, reserved/attempted one, and admitted zero. Strict JSON failed; H04 and H08 remained unattempted in those cohorts. Source: private repository `track_2a_evaluation/REVIEW.md` at current commit `7c41afde120ccbd3671684ed620ba529c30e309f`.

Later H08 R11 and R12 each attempted one exposed development case and admitted zero of one. R11 hit `length` at 1,024 completion tokens. R12 used `swiss-ai/Apertus-v1.5-70B` at CSCS, ended with ordinary `stop` and passed its response schema, but failed exact evidence binding: two actor/author occurrences claimed offsets `[138,193)` while their quoted substring occupied `[138,159)`. Nine of eleven matching occurrences did not admit the candidate. It remained UNMAPPED and answer-ineligible, with formal correctness/strict scores zero. No repaired response replaced the original.

R12 reported 2,902 prompt and 895 completion tokens (3,797 total); this is provider-reported usage, not billing proof. The original request commit was `83d457be9113e4c8b9612c2e55046ec88b157dba`; [historical run 38181658286](https://github.com/sumit1717/doru-formrehearsal/actions/runs/38181658286). Supporting private paths: `evaluation/H08_RECOVERY_R12.md`, `evaluation/prior-evidence-h08-r12/import-receipt.json`, and pinned request/reference/source-proof under `evaluation/packet-h08-r12/`.

The generic prospective converter has a separate seven-field event contract with complete request binding and chunk-scoped evidence. These historical captures must not be fed through an invented translator, silently repaired, relabeled as generic outputs or used as actual manually checked gold. They motivate exact admission and failure accounting, not a claim that the new pipeline succeeds.
