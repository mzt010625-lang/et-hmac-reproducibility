from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping

from .api_client import ChatAPIConfig
from .stage6_contracts import validate_l2_request


def load_stage6_cases(path: Path) -> List[Dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError("Stage 6 input is empty")
    seen = set()
    for row in rows:
        if set(row) != {"case_id", "l2_request", "execution_context"}:
            raise ValueError("Stage 6 case must contain case_id, l2_request, execution_context")
        if row["case_id"] in seen:
            raise ValueError("duplicate Stage 6 case_id")
        seen.add(row["case_id"])
        validate_l2_request(row["l2_request"])
        context = row["execution_context"]
        if set(context) != {"fast_action", "fast_source"}:
            raise ValueError("execution_context must contain only fast_action and fast_source")
        if context["fast_action"] not in set(row["l2_request"]["allowed_actions"]):
            raise ValueError("fast action is illegal at the current snapshot")
    return rows


def build_l2_payload(
    config: ChatAPIConfig,
    system_prompt: str,
    case: Mapping[str, Any],
) -> Dict[str, Any]:
    request = case["l2_request"]
    validate_l2_request(request)
    return {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": "请对下列当前可见快照进行深度决策，并严格返回JSON：\n"
                + json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            },
        ],
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "stream": config.stream,
        **({"response_format": {"type": "json_object"}} if config.response_format_json_object else {}),
    }
