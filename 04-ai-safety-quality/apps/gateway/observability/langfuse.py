from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.common.config import settings


@dataclass
class TraceHandle:
    trace_id: str
    _trace: Any


class LangfuseClient:
    """Optional Langfuse integration.

    If LANGFUSE_* env vars are not set, this becomes a no-op client.
    """

    def __init__(self) -> None:
        self.enabled = bool(settings.langfuse_public_key and settings.langfuse_secret_key)
        self._lf = None
        if self.enabled:
            try:
                from langfuse import Langfuse  # type: ignore

                self._lf = Langfuse(
                    public_key=settings.langfuse_public_key,
                    secret_key=settings.langfuse_secret_key,
                    host=settings.langfuse_host or None,
                )
            except Exception:
                self.enabled = False

    def start_trace(self, name: str, metadata: dict[str, Any]) -> TraceHandle:
        if not self.enabled or self._lf is None:
            return TraceHandle(trace_id="", _trace=None)
        t = self._lf.trace(name=name, metadata=metadata)
        return TraceHandle(trace_id=t.id, _trace=t)

    def event(self, trace: TraceHandle, name: str, metadata: dict[str, Any]) -> None:
        if not self.enabled or trace._trace is None:
            return
        trace._trace.event(name=name, metadata=metadata)

    def end_trace(self, trace: TraceHandle, output: dict[str, Any]) -> None:
        if not self.enabled or trace._trace is None:
            return
        trace._trace.update(output=output)
