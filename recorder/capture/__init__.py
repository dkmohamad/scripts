"""Capture pipeline package: record, transcribe, summarise, compress, publish.

Re-exports ``main`` so the ``capture`` console script
(``recorder.capture:main``) keeps resolving after the split from a single
module into this package.
"""

from .cli import main

__all__ = ["main"]
