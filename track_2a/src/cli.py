"""Minimal offline Track 2A entrypoint; no provider or credential path."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        raise SystemExit('Choose demo, prepare, import, review, comparison-demo or test')
    operation, rest = args[0], args[1:]
    if operation in ('prepare', 'import', 'review'):
        from track_2a_converter.pipeline import main as pipeline_main
        return pipeline_main(args)
    if operation == 'demo':
        from track_2a_converter.fixture_demo import main as demo_main
        sys.argv = ['fixture_demo.py', *rest]
        return demo_main()
    if operation == 'comparison-demo':
        from track_2a_comparison.demo import main as demo_main
        sys.argv = ['demo.py', '--repo-root', str(ROOT), *rest]
        return demo_main()
    if args == ['test']:
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', WORKSHEET_REPO_ROOT=str(ROOT))
        commands = [
            [sys.executable, '-B', '-m', 'unittest', 'discover',
             '-s', str(ROOT / 'track_2a_converter/tests'), '-v'],
            [sys.executable, '-B', str(ROOT / 'worksheet_tests.py')],
            [sys.executable, '-B', str(ROOT / 'tools/product_improvements_v1/run_offline.py'),
             'python', str(ROOT / 'tests/run_guarded.py'),
             str(ROOT.parent / 'tests/test_apertus_capture.py')],
        ]
        for command in commands:
            result = subprocess.call(command, cwd=ROOT, env=env)
            if result:
                return result
        return 0
    raise SystemExit('Unsupported operation. Capture integration is not enabled in this candidate.')


if __name__ == '__main__':
    raise SystemExit(main())
