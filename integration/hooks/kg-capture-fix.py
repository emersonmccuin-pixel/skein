#!/usr/bin/env python3
"""PostToolUse hook: detect fix-complete patterns and nudge capture.

Tracks recent test/build failures in a state file. When a test/build command
succeeds within 30 minutes of a prior failure of the same suite, fires a nudge
telling Claude to capture what was learned.

State file: ~/.claude/hooks/kg-fix-state.json
"""

import json
import re
import sys
import time
from pathlib import Path

STATE_FILE = Path.home() / ".claude" / "hooks" / "kg-fix-state.json"
FAILURE_WINDOW_SECONDS = 30 * 60  # 30 minutes

# Patterns that identify test/build commands
TEST_BUILD_PATTERNS = [
    (r"\bpytest\b", "pytest"),
    (r"\bnpm\s+test\b", "npm-test"),
    (r"\bnpm\s+run\s+test\b", "npm-test"),
    (r"\brspec\b", "rspec"),
    (r"\bjest\b", "jest"),
    (r"\bcargo\s+test\b", "cargo-test"),
    (r"\bgo\s+test\b", "go-test"),
    (r"\bnpm\s+run\s+build\b", "npm-build"),
    (r"\bcargo\s+build\b", "cargo-build"),
    (r"\bmake\b", "make"),
    (r"\buv\s+run\s+.*pytest\b", "pytest"),
]


def _identify_suite(command: str) -> str | None:
    """Return a suite identifier if the command is a test/build command."""
    for pattern, suite in TEST_BUILD_PATTERNS:
        if re.search(pattern, command):
            return suite
    return None


def _load_state() -> dict:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        pass
    return {"failures": {}}


def _save_state(state: dict):
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state))
    except OSError:
        pass


def _is_failure(tool_output: str) -> bool:
    """Heuristic: did the command fail?"""
    output = str(tool_output)
    # Check for explicit exit code indicators
    if re.search(r"exit\s*code[:\s]+[1-9]", output, re.IGNORECASE):
        return True
    if re.search(r"FAILED|FAILURE|ERROR|error:", output):
        return True
    if re.search(r"(\d+)\s+failed", output) and not re.search(r"0\s+failed", output):
        return True
    return False


def _is_success(tool_output: str) -> bool:
    """Heuristic: did the command succeed?"""
    output = str(tool_output)
    if re.search(r"(\d+)\s+passed", output) and not _is_failure(tool_output):
        return True
    if re.search(r"Build\s+succeeded|BUILD\s+SUCCESSFUL", output, re.IGNORECASE):
        return True
    if re.search(r"0\s+errors?", output) and not _is_failure(tool_output):
        return True
    # "All tests passed" type messages
    if re.search(r"all\s+\d+\s+tests?\s+passed", output, re.IGNORECASE):
        return True
    return False


def _prune_old_failures(state: dict):
    """Remove failures older than the window."""
    now = time.time()
    state["failures"] = {
        suite: entry
        for suite, entry in state.get("failures", {}).items()
        if now - entry.get("timestamp", 0) < FAILURE_WINDOW_SECONDS
    }


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
    suite = _identify_suite(command)
    if not suite:
        sys.exit(0)

    output_str = str(tool_output)
    state = _load_state()
    _prune_old_failures(state)

    if _is_failure(output_str):
        # Record the failure
        state.setdefault("failures", {})[suite] = {
            "timestamp": time.time(),
            "command": command[:200],
        }
        _save_state(state)
        sys.exit(0)

    if _is_success(output_str):
        # Check if there was a recent failure for this suite
        failure = state.get("failures", {}).get(suite)
        if failure:
            elapsed = time.time() - failure.get("timestamp", 0)
            if elapsed < FAILURE_WINDOW_SECONDS:
                # Clear the failure
                del state["failures"][suite]
                _save_state(state)

                nudge = (
                    f"Fix confirmed: {suite} now passing (was failing {int(elapsed // 60)} min ago).\n\n"
                    "Capture what you learned during this fix to Project KG:\n"
                    "- What was the root cause? -> kg_add type='discovery'\n"
                    "- Non-obvious debugging step? -> kg_add type='pattern'\n"
                    "- Workaround applied? -> kg_add type='discovery'\n\n"
                    "If the fix was trivial, skip. Decide yourself — do not ask the user."
                )
                print(nudge, file=sys.stderr)
                sys.exit(2)

    _save_state(state)
    sys.exit(0)


if __name__ == "__main__":
    main()
