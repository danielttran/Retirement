from __future__ import annotations

from decimal import getcontext

ENGINE_VERSION = "0.1.0"

getcontext().prec = 28

__all__ = ["ENGINE_VERSION"]

