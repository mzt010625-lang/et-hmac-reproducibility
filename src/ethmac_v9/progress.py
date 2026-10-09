from __future__ import annotations

import sys
import threading
import time
from datetime import datetime, timedelta
from typing import Optional, TextIO


def render_indeterminate_bar(step: int, width: int = 24) -> str:
    if width < 3:
        raise ValueError("progress width must be at least 3")
    cycle = 2 * (width - 1)
    offset = step % cycle
    position = offset if offset < width else cycle - offset
    cells = ["·"] * width
    cells[position] = "▶"
    return "".join(cells)


def render_batch_bar(completed: int, total: int, width: int = 20) -> str:
    if total <= 0:
        raise ValueError("total must be positive")
    if not 0 <= completed <= total:
        raise ValueError("completed must be in [0, total]")
    filled = min(width, int(width * completed / total))
    cells = ["█"] * filled + ["·"] * (width - filled)
    if completed < total:
        cells[min(filled, width - 1)] = "▶"
    return "".join(cells)


def format_duration(seconds: float) -> str:
    value = max(0, int(round(seconds)))
    hours, remainder = divmod(value, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class TerminalProgress:
    """Dependency-free indeterminate progress display for blocking API calls."""

    def __init__(
        self,
        label: str,
        stream: Optional[TextIO] = None,
        interval_seconds: float = 1.0,
        enabled: Optional[bool] = None,
        current_index: int = 1,
        total: int = 1,
        expected_seconds_per_record: float = 24.0,
    ) -> None:
        self.label = label
        self.stream = stream or sys.stderr
        self.interval_seconds = interval_seconds
        self.enabled = self.stream.isatty() if enabled is None else enabled
        self.current_index = current_index
        self.total = total
        self.expected_seconds_per_record = max(0.1, expected_seconds_per_record)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._started = 0.0
        self._last_width = 0

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    def _estimate(self, elapsed: float) -> tuple[float, str]:
        current_remaining = max(0.0, self.expected_seconds_per_record - elapsed)
        future_remaining = max(0, self.total - self.current_index) * self.expected_seconds_per_record
        remaining = current_remaining + future_remaining
        finish_at = datetime.now() + timedelta(seconds=remaining)
        return remaining, finish_at.strftime("%H:%M:%S")

    def start(self) -> None:
        self._started = time.monotonic()
        if not self.enabled:
            remaining, finish_at = self._estimate(0.0)
            self.stream.write(
                f"{self.label}：等待API响应；预计剩余{format_duration(remaining)}，预计完成{finish_at}\n"
            )
            self.stream.flush()
            return
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()

    def _animate(self) -> None:
        step = 0
        while not self._stop.is_set():
            elapsed = time.monotonic() - self._started
            remaining, finish_at = self._estimate(elapsed)
            completed_before = self.current_index - 1
            percent = completed_before / self.total * 100
            line = (
                f"{self.label} [{render_batch_bar(completed_before, self.total)}] "
                f"{percent:5.1f}% | 本条{elapsed:5.1f}s | "
                f"预计剩余{format_duration(remaining)} | 完成{finish_at} | {render_indeterminate_bar(step, 8)}"
            )
            self._last_width = max(self._last_width, len(line))
            self.stream.write("\r" + line)
            self.stream.flush()
            step += 1
            self._stop.wait(self.interval_seconds)

    def stop(self, status: str) -> float:
        elapsed = time.monotonic() - self._started
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.interval_seconds * 3))
        if self.enabled:
            line = (
                f"{self.label} [{render_batch_bar(self.current_index, self.total)}] "
                f"{self.current_index / self.total * 100:5.1f}% | {status} | 本条{elapsed:5.1f}s"
            )
            padding = " " * max(0, self._last_width - len(line))
            self.stream.write("\r" + line + padding + "\n")
            self.stream.flush()
        return elapsed
