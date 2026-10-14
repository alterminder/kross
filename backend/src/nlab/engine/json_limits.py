"""Bound JSON documents before recursive validators or model-context serialization."""

import json
import math
from collections.abc import Iterable
from typing import Any


def bounded_json[T](
    value: T,
    *,
    max_bytes: int,
    max_depth: int = 16,
    max_items: int = 200,
    max_string: int = 200_000,
) -> T:
    pending: list[tuple[Any, int]] = [(value, 0)]
    nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if depth > max_depth:
            raise ValueError(f"Document depth exceeds {max_depth}")
        if nodes > 10_000:
            raise ValueError("Document has too many values")
        if isinstance(item, (dict, list)):
            if len(item) > max_items:
                raise ValueError(f"A collection has more than {max_items} entries")
            children: Iterable[Any]
            if isinstance(item, dict):
                if any(not isinstance(key, str) or len(key) > 200 for key in item):
                    raise ValueError("Document keys must be strings of at most 200 characters")
                children = item.values()
            else:
                children = item
            pending.extend((child, depth + 1) for child in children)
        elif isinstance(item, str):
            if len(item) > max_string:
                raise ValueError(f"A text field exceeds {max_string} characters")
        elif isinstance(item, float) and not math.isfinite(item):
            raise ValueError("Document numbers must be finite")
        elif item is not None and not isinstance(item, (bool, int, float)):
            raise ValueError("Document contains a non-JSON value")
    if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")) > max_bytes:
        raise ValueError(f"Document exceeds {max_bytes} UTF-8 bytes")
    return value
