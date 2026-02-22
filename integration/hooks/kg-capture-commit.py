#!/usr/bin/env python3
"""PostToolUse hook: nudge Claude to capture knowledge after a successful git commit.

Reads hook JSON from stdin. Fires only when:
- Tool is Bash
- Command contains 'git commit'
- Output indicates the commit succeeded (contains [branch hash] pattern)

Exits with code 2 + nudge message on match; code 0 (silent pass) otherwise.
"""

import json
import re
import sys


def main():
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    tool_output = data.get("tool_output", "")

    if tool_name != "Bash":
        sys.exit(0)

    command = tool_input.get("command", "")
    if not re.search(r"git\s+commit\b", command):
        sys.exit(0)

    # Confirm commit succeeded — git outputs "[branch hash] message"
    output_str = str(tool_output)
    if not re.search(r"\[[\w/.+-]+\s+[0-9a-f]{7,}\]", output_str):
        sys.exit(0)

    # Extract commit message for context
    msg_match = re.search(r"""-m\s+["'](.+?)["']""", command)
    if not msg_match:
        # Try heredoc pattern: -m "$(cat <<'EOF'\n...\nEOF\n)"
        msg_match = re.search(r"EOF\n(.+?)\n", command, re.DOTALL)
    commit_msg = msg_match.group(1).strip().split("\n")[0] if msg_match else "(see diff)"

    nudge = (
        f"Commit landed: {commit_msg}\n\n"
        "Did you learn anything during the work that led to this commit? "
        "If yes, capture it to Project KG:\n"
        "- Debugging breakthroughs -> kg_add type='discovery'\n"
        "- Patterns or conventions found -> kg_add type='pattern'\n"
        "- Workarounds for unexpected behavior -> kg_add type='discovery'\n"
        "- Procedural knowledge (non-obvious steps) -> kg_add type='pattern'\n\n"
        "If this was a straightforward change with nothing novel, skip capture. "
        "Decide yourself — do not ask the user."
    )

    print(nudge, file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
