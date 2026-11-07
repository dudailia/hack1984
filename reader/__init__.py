"""Reader: turns web text into validated typed claims. Pure: no network, no file reads at call time.

The Reader never sees the memo, the question, need ids, session ids or secrets (invariant 3). It builds the
Anthropic request body; the Gate sends it.
"""
from reader.composer import compose
from reader.parse import parse_response
from reader.request import build_request
from reader.validator import validate

__all__ = ["build_request", "parse_response", "validate", "compose"]
