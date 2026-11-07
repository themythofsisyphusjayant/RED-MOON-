#!/usr/bin/env python3
"""Qasida compiler CLI — thin shim.

The real entry point is forge_lang.cli:main (installed as the
`qasida` command). This file exists so a checkout keeps working
as `python3 forge.py ...` and so `bin/qasida` keeps finding it.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from forge_lang.cli import main  # noqa: E402
from forge_lang import __version__ as VERSION  # noqa: E402
# VERSION stays importable from here (forge_lang/__init__.py
# __version__ is the single source of truth).

if __name__ == "__main__":
    raise SystemExit(main())
