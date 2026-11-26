#!/usr/bin/env python3
"""Patstack's own CI, run in the agent by tools/local_ci.py instead of on GitHub.

The same command the removed .github/workflows/ci.yml ran (Python 3.12, Node 24):
the package check with manifest, links, privacy, formats and every test suite.
"""
import subprocess
import sys

sys.exit(subprocess.run([sys.executable, "scripts/check.py"]).returncode)
