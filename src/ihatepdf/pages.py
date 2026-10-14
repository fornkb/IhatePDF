"""One-based page selections for document operations."""

import re


def parse_pages(spec: str, count: int, *, duplicates: bool = False) -> list[int]:
    """Return zero-based indices in requested order; ranges may run backwards."""
    if count < 1:
        raise ValueError("The PDF has no pages.")
    selected: list[int] = []
    for token in spec.lower().split(","):
        token = token.strip()
        if token == "all":
            indices = list(range(count))
        elif token in {"odd", "even"}:
            indices = list(range(0 if token == "odd" else 1, count, 2))
        else:
            match = re.fullmatch(r"(\d+|last)(?:\s*-\s*(\d+|last))?", token)
            if not match:
                raise ValueError(f"Invalid page selection '{token}'. Use e.g. 1-5,8,last,odd.")
            first = count if match[1] == "last" else int(match[1])
            last = first if match[2] is None else (count if match[2] == "last" else int(match[2]))
            if not (1 <= first <= count and 1 <= last <= count):
                raise ValueError(f"Page selection '{token}' is outside 1-{count}.")
            step = 1 if last >= first else -1
            indices = list(range(first - 1, last - 1 + step, step))
        selected.extend(indices)
    if not selected:
        raise ValueError("The selection contains no pages.")
    return selected if duplicates else list(dict.fromkeys(selected))

