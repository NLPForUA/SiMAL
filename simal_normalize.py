"""Utilities for normalizing SiMAL text without changing semantics.

Today this focuses on indentation removal.

Important: The SiMAL tokenizer ignores spaces/tabs outside of strings/heredocs.
So stripping leading indentation is semantically safe for syntax.
However, heredoc bodies are turned into STRING tokens and represent user text;
we preserve those by default to avoid destroying formatting (e.g., code blocks).
"""

from __future__ import annotations

import re
from typing import Optional


_HEREDOC_START_RE = re.compile(r"<<(\S+)")


def remove_leading_indentation(text: str, *, preserve_heredocs: bool = True) -> str:
    """Remove leading spaces/tabs from each line, preserving newlines.

    - Newlines are preserved exactly (line count and line endings).
    - By default, heredoc body lines are preserved as-is to avoid changing
      description text formatting.

    Args:
        text: Original SiMAL text.
        preserve_heredocs: If True, do not strip indentation inside heredoc bodies.

    Returns:
        Normalized text.
    """

    if not text:
        return text

    out: list[str] = []
    in_heredoc = False
    heredoc_label: Optional[str] = None

    # Keep line endings exactly as in the input.
    for line in text.splitlines(keepends=True):
        if in_heredoc and preserve_heredocs:
            # End label line closes heredoc (tokenizer uses strip() comparison).
            if heredoc_label is not None and line.strip() == heredoc_label:
                out.append(line.lstrip(" \t"))
                in_heredoc = False
                heredoc_label = None
            else:
                out.append(line)
            continue

        # Normal lines: strip leading indentation.
        stripped = line.lstrip(" \t")
        out.append(stripped)

        if preserve_heredocs and not in_heredoc:
            # Detect heredoc start. Heuristic: only consider <<LABEL if it appears
            # before any quote on the line (so we don't accidentally trigger inside
            # quoted strings).
            idx = stripped.find("<<")
            if idx != -1:
                dq = stripped.find('"')
                sq = stripped.find("'")
                first_quote = min([x for x in (dq, sq) if x != -1], default=-1)
                if first_quote == -1 or idx < first_quote:
                    m = _HEREDOC_START_RE.search(stripped)
                    if m:
                        in_heredoc = True
                        heredoc_label = m.group(1)

    return "".join(out)
