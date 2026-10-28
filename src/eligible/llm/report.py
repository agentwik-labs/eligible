"""Print the cost/token summary of a ledger: `uv run python -m eligible.llm.report [path]`."""

from __future__ import annotations

import sys
from pathlib import Path

from eligible.config import get_settings
from eligible.llm.ledger import Ledger, render_markdown, summarize


def main(argv: list[str]) -> int:
    path = Path(argv[0]) if argv else get_settings().ledger_path
    responses = Ledger(path).read()
    if not responses:
        print(f"no LLM calls recorded in {path}")
        return 0
    print(render_markdown(summarize(responses)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
