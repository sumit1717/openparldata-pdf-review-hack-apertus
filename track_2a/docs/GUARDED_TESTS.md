# Self-contained dispatcher test guard closure

The optional adapter's authored tests require actual kernel-level socket creation denial, followed by the existing Python process/socket audit hook. Docker `--network=none` alone is insufficient because it still permits socket creation. Audit-only execution is not an equivalent test route.

The unchanged guard files and exact hashes are in `GUARD_SOURCE_PINS.json`. They are copied as source under `src/tools`, `src/evaluation` and `src/tests`, preserving their original relative dependency layout. The generic existing `run-affected-checks.py` contains other historical command lists, but those commands are not invoked by this test route. The only body used is its existing `install_network_boundary` function, loaded by the pinned outer launcher. The Node guard is hash-checked by that launcher but is not executed for Python tests.

The intended container test route, after separately authorized Docker verification, is:

```sh
python -B /app/src/tools/product_improvements_v1/run_offline.py \
  python /app/src/tests/run_guarded.py /app/tests/test_apertus_capture.py
```

`make test` invokes this route after converter and scoped worksheet checks. The outer loader installs the Linux x86_64 seccomp boundary and probes `socket.socket` for EPERM. The inner guard probes it again and installs a Python audit hook rejecting process/exec/fork/spawn/system and socket activity before importing the authored test module. Pure mocked transport is required. Unsupported platforms or unavailable controls must fail; no unguarded fallback is supplied.

No guard or test in the newly assembled Docker image has been executed. Existing worker receipts describe their exact source-only/mock execution context and do not establish a new container pass. No test here constitutes actual PDF extraction, model performance, human gold, provider API compatibility, security certification or publication readiness.
