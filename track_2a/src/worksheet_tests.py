"""Owned-converter worksheet scope; two real-ledger tests are explicitly skipped.

Original tests stay unchanged. This is not the full historical comparison suite.
"""
import importlib.util
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
os.environ['WORKSHEET_REPO_ROOT'] = str(ROOT)
EXCLUDED = {
    'test_real_frozen_ledger_dates_baselines_uninspected_annexes',
    'test_unknown_family_and_tampered_ledger_failclosed',
}


def main():
    spec = importlib.util.spec_from_file_location(
        'sealed_worksheet_tests', ROOT / 'track_2a_comparison/tests/test_worksheet.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in sorted(EXCLUDED):
        original = getattr(module.WorksheetTests, name)
        reason = ('OUTSIDE ORIGINAL-ONLY CANDIDATE: historical source-bearing ledger data '
                  'is excluded pending rights clearance; run the complete private checkout suite')
        setattr(module.WorksheetTests, name, unittest.skip(reason)(original))
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(module))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
