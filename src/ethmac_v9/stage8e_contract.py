"""Stage 8E v8 wrapper preserving the frozen v7 hard-guard semantics."""
from __future__ import annotations

from .stage8d_contract import REQUIRED, base_action, resolve_output as resolve_v7


def resolve_output(output: dict, record: dict) -> dict:
    if not isinstance(output, dict) or set(output) != REQUIRED:
        raise ValueError("L2 v8 output keys mismatch")
    if output.get("v") != "l2_semantic_exception_v8" or output.get("id") != record["id"]:
        raise ValueError("L2 v8 version/id mismatch")
    translated = dict(output)
    translated["v"] = "l2_semantic_exception_v7"
    resolved = resolve_v7(translated, record)
    resolved["raw_output"] = output
    return resolved


__all__ = ["base_action", "resolve_output"]
