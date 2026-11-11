"""HTTP URL pattern routing supporting :param captures."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .context import ApiContext

Handler = Callable[[ApiContext], tuple[int, dict[str, Any]]]


@dataclass
class _Route:
    method: str
    pattern: str
    segments: list[str]
    handler: Handler


def _split_path(path: str) -> list[str]:
    return [s for s in path.strip("/").split("/") if s]


class Router:
    """Matches HTTP method and parameterized paths (e.g. /v1/tenants/:id)."""

    def __init__(self) -> None:
        self._routes: list[_Route] = []

    def add(self, method: str, pattern: str, handler: Handler) -> None:
        """Register a handler for an HTTP method and path pattern."""
        segments = _split_path(pattern)
        self._routes.append(
            _Route(
                method=method.upper(),
                pattern=pattern,
                segments=segments,
                handler=handler,
            )
        )

    def match(self, method: str, raw_path: str) -> tuple[Handler, dict[str, str]] | None:
        """Find matching handler and extracted path parameters."""
        req_method = method.upper()
        req_segments = _split_path(raw_path)

        for r in self._routes:
            if r.method != req_method or len(r.segments) != len(req_segments):
                continue
            params: dict[str, str] = {}
            matched = True
            for pat_seg, path_seg in zip(r.segments, req_segments, strict=True):
                if pat_seg.startswith(":"):
                    params[pat_seg[1:]] = path_seg
                elif pat_seg != path_seg:
                    matched = False
                    break
            if matched:
                return r.handler, params
        return None
