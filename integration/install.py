#!/usr/bin/env python3
"""Install (or uninstall) Project KG Claude Code integration.

Copies hooks and skills into the user's ~/.claude/ directory and
registers PostToolUse hooks in settings.json.

Usage:
    python integration/install.py           # install
    python integration/install.py --uninstall  # remove everything
    python integration/install.py --check      # verify installation
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

INTEGRATION_DIR = Path(__file__).parent
CLAUDE_DIR = Path.home() / ".claude"
HOOKS_DIR = CLAUDE_DIR / "hooks"
SKILLS_DIR = CLAUDE_DIR / "skills"
SETTINGS_FILE = CLAUDE_DIR / "settings.json"

HOOK_FILES = [
    "hooks/kg-capture-commit.py",
    "hooks/kg-capture-fix.py",
]

SKILL_DIR_NAME = "kg-interviewer"

# The hook entry we add to settings.json PostToolUse
KG_HOOK_ENTRY = {
    "matcher": "Bash",
    "hooks": [
        {
            "type": "command",
            "command": f'python "{HOOKS_DIR / "kg-capture-commit.py"}"',
        },
        {
            "type": "command",
            "command": f'python "{HOOKS_DIR / "kg-capture-fix.py"}"',
        },
    ],
}

# Marker to identify our hook entry for uninstall
KG_HOOK_MARKER = "kg-capture-commit.py"


def install():
    print("Installing Project KG integration...\n")
    results = []

    # 1. Copy hooks
    HOOKS_DIR.mkdir(parents=True, exist_ok=True)
    for hook_rel in HOOK_FILES:
        src = INTEGRATION_DIR / hook_rel
        dst = HOOKS_DIR / Path(hook_rel).name
        if not src.exists():
            print(f"  [SKIP] {src} not found")
            continue
        shutil.copy2(src, dst)
        results.append(f"  [OK] Copied {dst}")
        print(results[-1])

    # 2. Copy skill
    src_skill = INTEGRATION_DIR / "skills" / SKILL_DIR_NAME
    dst_skill = SKILLS_DIR / SKILL_DIR_NAME
    if src_skill.exists():
        if dst_skill.exists():
            shutil.rmtree(dst_skill)
        shutil.copytree(src_skill, dst_skill)
        results.append(f"  [OK] Copied skill to {dst_skill}")
        print(results[-1])

    # 3. Register hooks in settings.json
    _register_hooks()

    # 4. Print CLAUDE.md snippet
    snippet_file = INTEGRATION_DIR / "claude-md-snippet.md"
    if snippet_file.exists():
        snippet = snippet_file.read_text().strip()
        print(f"\n{'=' * 60}")
        print("Add this to your ~/.claude/CLAUDE.md (or project CLAUDE.md):")
        print(f"{'=' * 60}")
        print(snippet)
        print(f"{'=' * 60}\n")

    # 5. Check MCP server config
    _check_mcp_config()

    print("\nInstallation complete.")


def _register_hooks():
    """Add KG hooks to settings.json PostToolUse without clobbering existing hooks."""
    if not SETTINGS_FILE.exists():
        print("  [WARN] settings.json not found — creating minimal one")
        settings = {}
    else:
        try:
            settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("  [ERROR] settings.json is malformed — skipping hook registration")
            return

    hooks = settings.setdefault("hooks", {})
    post_tool = hooks.setdefault("PostToolUse", [])

    # Check if we already have a KG hook entry
    already_installed = any(
        KG_HOOK_MARKER in json.dumps(entry)
        for entry in post_tool
    )
    if already_installed:
        print("  [OK] Hooks already registered in settings.json")
        return

    post_tool.append(KG_HOOK_ENTRY)

    # Write back with the same formatting
    SETTINGS_FILE.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print("  [OK] Registered PostToolUse hooks in settings.json")


def _check_mcp_config():
    """Check if project-kg MCP server is configured somewhere."""
    locations_checked = []

    # Check global .claude.json
    global_config = Path.home() / ".claude.json"
    if global_config.exists():
        try:
            data = json.loads(global_config.read_text(encoding="utf-8"))
            servers = data.get("mcpServers", {})
            if "project-kg" in servers:
                print("  [OK] MCP server configured in ~/.claude.json")
                return
        except json.JSONDecodeError:
            pass
        locations_checked.append(str(global_config))

    # Check for .mcp.json in common locations
    cwd = Path.cwd()
    for search_dir in [cwd, cwd.parent, cwd.parent.parent]:
        mcp_json = search_dir / ".mcp.json"
        if mcp_json.exists():
            try:
                data = json.loads(mcp_json.read_text(encoding="utf-8"))
                servers = data.get("mcpServers", {})
                if "project-kg" in servers:
                    print(f"  [OK] MCP server configured in {mcp_json}")
                    return
            except json.JSONDecodeError:
                pass
            locations_checked.append(str(mcp_json))

    print(
        "  [WARN] project-kg MCP server not found in config.\n"
        "         Add it to ~/.claude.json or your project's .mcp.json.\n"
        "         Example:\n"
        '         "project-kg": {\n'
        '           "type": "stdio",\n'
        '           "command": "uv",\n'
        '           "args": ["run", "--directory", "/path/to/project-kg", '
        '"python", "-m", "project_kg"]\n'
        "         }"
    )


def uninstall():
    print("Uninstalling Project KG integration...\n")

    # 1. Remove hooks
    for hook_rel in HOOK_FILES:
        dst = HOOKS_DIR / Path(hook_rel).name
        if dst.exists():
            dst.unlink()
            print(f"  [OK] Removed {dst}")

    # Remove state file if present
    state_file = HOOKS_DIR / "kg-fix-state.json"
    if state_file.exists():
        state_file.unlink()
        print(f"  [OK] Removed {state_file}")

    # 2. Remove skill
    dst_skill = SKILLS_DIR / SKILL_DIR_NAME
    if dst_skill.exists():
        shutil.rmtree(dst_skill)
        print(f"  [OK] Removed {dst_skill}")

    # 3. Deregister hooks from settings.json
    if SETTINGS_FILE.exists():
        try:
            settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            post_tool = settings.get("hooks", {}).get("PostToolUse", [])
            original_len = len(post_tool)
            post_tool[:] = [
                entry for entry in post_tool
                if KG_HOOK_MARKER not in json.dumps(entry)
            ]
            if len(post_tool) < original_len:
                SETTINGS_FILE.write_text(
                    json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                print("  [OK] Removed hooks from settings.json")
        except json.JSONDecodeError:
            print("  [WARN] Could not parse settings.json")

    print(
        "\nUninstallation complete.\n"
        "Remember to remove the Project KG section from your CLAUDE.md if you added it."
    )


def check():
    print("Checking Project KG integration...\n")
    all_ok = True

    # Check hooks exist
    for hook_rel in HOOK_FILES:
        dst = HOOKS_DIR / Path(hook_rel).name
        if dst.exists():
            print(f"  [OK] {dst}")
        else:
            print(f"  [MISSING] {dst}")
            all_ok = False

    # Check skill exists
    dst_skill = SKILLS_DIR / SKILL_DIR_NAME / "SKILL.md"
    if dst_skill.exists():
        print(f"  [OK] {dst_skill}")
    else:
        print(f"  [MISSING] {dst_skill}")
        all_ok = False

    # Check hooks registered
    if SETTINGS_FILE.exists():
        try:
            settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            post_tool = settings.get("hooks", {}).get("PostToolUse", [])
            registered = any(
                KG_HOOK_MARKER in json.dumps(entry) for entry in post_tool
            )
            if registered:
                print("  [OK] Hooks registered in settings.json")
            else:
                print("  [MISSING] Hooks not registered in settings.json")
                all_ok = False
        except json.JSONDecodeError:
            print("  [WARN] settings.json malformed")
            all_ok = False

    # Check MCP config
    _check_mcp_config()

    if all_ok:
        print("\nAll checks passed.")
    else:
        print("\nSome components missing. Run: python integration/install.py")


def main():
    parser = argparse.ArgumentParser(description="Project KG integration installer")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--uninstall", action="store_true", help="Remove integration")
    group.add_argument("--check", action="store_true", help="Verify installation")
    args = parser.parse_args()

    if args.uninstall:
        uninstall()
    elif args.check:
        check()
    else:
        install()


if __name__ == "__main__":
    main()
