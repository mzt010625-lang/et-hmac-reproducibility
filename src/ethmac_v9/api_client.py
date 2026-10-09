from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


class APIRequestError(RuntimeError):
    def __init__(self, message: str, attempts: List[Dict[str, Any]]) -> None:
        super().__init__(message)
        self.attempts = attempts


@dataclass(frozen=True)
class ChatAPIConfig:
    base_url: str
    chat_completions_path: str
    model: str
    temperature: float
    max_tokens: int
    timeout_seconds: int
    max_attempts: int
    retry_status_codes: Tuple[int, ...]
    retry_backoff_seconds: Tuple[float, ...]
    stream: bool
    response_format_json_object: bool
    thinking: Optional[Dict[str, str]] = None
    reasoning_effort: Optional[str] = None

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "ChatAPIConfig":
        return cls(
            base_url=str(value["base_url"]).rstrip("/"),
            chat_completions_path="/" + str(value["chat_completions_path"]).lstrip("/"),
            model=str(value["model"]),
            temperature=float(value["temperature"]),
            max_tokens=int(value["max_tokens"]),
            timeout_seconds=int(value["timeout_seconds"]),
            max_attempts=int(value["max_attempts"]),
            retry_status_codes=tuple(int(code) for code in value["retry_status_codes"]),
            retry_backoff_seconds=tuple(float(x) for x in value["retry_backoff_seconds"]),
            stream=bool(value.get("stream", False)),
            response_format_json_object=bool(value.get("response_format_json_object", False)),
            thinking=dict(value["thinking"]) if value.get("thinking") is not None else None,
            reasoning_effort=str(value["reasoning_effort"]) if value.get("reasoning_effort") is not None else None,
        )

    @property
    def endpoint(self) -> str:
        return self.base_url + self.chat_completions_path


def build_chat_payload(config: ChatAPIConfig, system_prompt: str, record: Dict[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": "请评估下面的当前轮记录并严格返回JSON：\n" + json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            },
        ],
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "stream": config.stream,
    }
    if config.response_format_json_object:
        payload["response_format"] = {"type": "json_object"}
    if config.thinking is not None:
        payload["thinking"] = dict(config.thinking)
    if config.reasoning_effort is not None:
        payload["reasoning_effort"] = config.reasoning_effort
    return payload


def call_chat_completions(
    config: ChatAPIConfig,
    api_key: str,
    payload: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if not api_key:
        raise ValueError("API key is empty")
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    attempts: List[Dict[str, Any]] = []
    last_message = "request did not start"
    for attempt_index in range(1, config.max_attempts + 1):
        started = time.monotonic()
        request = urllib.request.Request(
            config.endpoint,
            data=encoded,
            method="POST",
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "ET-HMAC-v9/Stage5",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
                body = response.read().decode("utf-8")
                elapsed_ms = round((time.monotonic() - started) * 1000, 3)
                parsed = json.loads(body)
                attempts.append({
                    "attempt": attempt_index,
                    "status": int(response.status),
                    "elapsed_ms": elapsed_ms,
                    "retry": False,
                })
                return parsed, attempts
        except urllib.error.HTTPError as exc:
            elapsed_ms = round((time.monotonic() - started) * 1000, 3)
            error_body = exc.read().decode("utf-8", errors="replace")
            safe_error_body = error_body.replace(api_key, "[REDACTED]")
            retry = int(exc.code) in config.retry_status_codes and attempt_index < config.max_attempts
            attempts.append({
                "attempt": attempt_index,
                "status": int(exc.code),
                "elapsed_ms": elapsed_ms,
                "retry": retry,
                "error_body": safe_error_body[:2000],
            })
            last_message = f"HTTP {exc.code}: {safe_error_body[:500]}"
            if not retry:
                break
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError,
                json.JSONDecodeError) as exc:
            elapsed_ms = round((time.monotonic() - started) * 1000, 3)
            retry = attempt_index < config.max_attempts
            attempts.append({
                "attempt": attempt_index,
                "status": "transport_or_decode_error",
                "elapsed_ms": elapsed_ms,
                "retry": retry,
                "error": str(exc)[:1000],
            })
            last_message = f"transport/decode error: {exc}"
            if not retry:
                break
        if attempts[-1]["retry"]:
            wait_index = min(attempt_index - 1, len(config.retry_backoff_seconds) - 1)
            time.sleep(config.retry_backoff_seconds[wait_index])
    raise APIRequestError(last_message, attempts)


def extract_message_content_with_source(response: Dict[str, Any]) -> Tuple[str, str]:
    try:
        message = response["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("response misses choices[0].message") from exc
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip(), "content"
    reasoning_content = message.get("reasoning_content")
    if isinstance(reasoning_content, str) and reasoning_content.strip():
        return reasoning_content.strip(), "reasoning_content_fallback"
    raise ValueError("response content and reasoning_content are empty or not strings")


def extract_message_content(response: Dict[str, Any]) -> str:
    content, _ = extract_message_content_with_source(response)
    return content


def parse_json_content(content: str) -> Dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().lower() in {"```", "```json"}:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("model content must decode to a JSON object")
    return parsed
