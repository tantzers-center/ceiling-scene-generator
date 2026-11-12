#!/usr/bin/env python
"""Run the whole suite: ``python tests/run_tests.py`` (or ``python tests/run_tests.py -v``).

Needs nothing but the Python standard library.  Node unlocks the extra checks
(JS parity, YAML parsing, card syntax); install the YAML parser with
``npm install --prefix tools``.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent


def main() -> int:
    sys.path.insert(0, str(HERE))
    verbosity = 2 if "-v" in sys.argv or "--verbose" in sys.argv else 1
    suite = unittest.defaultTestLoader.discover(
        str(HERE), pattern="test_*.py", top_level_dir=str(HERE)
    )
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    print()
    print(f"ran {result.testsRun} tests · "
          f"failures {len(result.failures)} · errors {len(result.errors)} · "
          f"skipped {len(result.skipped)}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
