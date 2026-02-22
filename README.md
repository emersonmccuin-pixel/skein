# Project KG

A knowledge graph for AI-assisted knowledge work. Project KG ingests data from work trackers, git repos, and markdown files, builds a searchable graph of decisions, patterns, and discoveries, and exposes it to AI agents via MCP.

## What it does

- **Semantic search** across all your knowledge (FTS + vector similarity)
- **Graph traversal** to explore connected decisions and context
- **Connectors** that sync external data sources into the graph
- **MCP server** so Claude Code (or any MCP client) can query it directly

## Quick start

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
# Clone and install
git clone https://github.com/emersonmccuin-pixel/project-kg.git
cd project-kg
uv sync

# Configure
cp kg.yaml.example kg.yaml
# Edit kg.yaml — set your paths

# Run the MCP server
uv run python -m project_kg
```

## Register with Claude Code

Add to `~/.claude.json` under `mcpServers`:

```json
{
  "mcpServers": {
    "project-kg": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/project-kg", "python", "-m", "project_kg"]
    }
  }
}
```

Restart Claude Code. You'll have these tools available:

| Tool | What it does |
|------|-------------|
| `kg_search` | FTS + vector similarity search, filtered by type/project |
| `kg_context` | Pre-action retrieval — "what should I know before doing X?" |
| `kg_get` | Get a node + its graph neighborhood (N hops) |
| `kg_add` | Add a knowledge node with auto-embedding |
| `kg_connect` | Create an edge between two nodes |
| `kg_sync` | Run connectors to ingest external data |
| `kg_status` | Counts by type/project, recent nodes, sync state |

## Configuration

`kg.yaml`:

```yaml
# Path to SQLite database (created on first run)
db_path: ./kg.db

# Local embedding model (no API key needed)
embedding_model: BAAI/bge-small-en-v1.5

# WCP data directory (optional — only if you use WCP)
wcp_data_path: /path/to/your/wcp-data
```

## Connectors

### WCP (Work Context Protocol)

If you use [WCP](https://github.com/emersonmccuin-pixel/wcp) for work tracking, Project KG can sync all your work items and artifacts into the graph.

Set `wcp_data_path` in `kg.yaml` to your WCP data directory, then:

```
kg_sync connector=wcp
```

This creates:
- One `work_item` node per WCP item (with activity logs)
- One `document` node per artifact file
- `depends_on` edges from parent relationships
- `relates_to` edges from artifact attachments

Incremental by default — only re-processes files modified since last sync. Use `full=true` to re-sync everything.

### Git / Filesystem (planned)

Git connector (commit history + cross-links to work items) and filesystem connector (markdown file scanning) are planned for future phases.

## Proactive intelligence (optional)

Project KG includes an integration layer that makes Claude Code automatically capture and retrieve knowledge as you work. This is optional — the MCP server works fine without it.

**What it adds:**
- **`kg_context` tool** — smarter retrieval with cross-project search and recency weighting
- **Commit capture hook** — nudges Claude to capture lessons learned after each commit
- **Fix-complete hook** — detects when a failing test starts passing and nudges capture
- **kg-interviewer skill** — interview variant that searches KG before output and captures decisions afterward
- **CLAUDE.md instruction** — tells Claude to check KG before non-trivial work

### Install the integration

```bash
# From the project-kg directory
python integration/install.py
```

This copies hooks and skills into `~/.claude/` and registers them in settings.json. It prints a CLAUDE.md snippet for you to add manually.

```bash
# Check what's installed
python integration/install.py --check

# Remove everything
python integration/install.py --uninstall
```

### Or ask Claude Code to do it

If you've already registered the MCP server, you can tell Claude Code:

> Install the Project KG integration. Run `python integration/install.py` from the project-kg directory, then add the CLAUDE.md snippet it prints to my global CLAUDE.md.

## How it works

- **SQLite** stores nodes, edges, and sync state
- **FTS5** provides full-text search with BM25 ranking
- **fastembed** (BAAI/bge-small-en-v1.5) generates 384-dim embeddings locally — no API keys, works offline
- **NumPy** does brute-force cosine similarity (fast enough for thousands of nodes)
- Search combines FTS and vector scores with weighted fusion (0.4/0.6)

## Node types

`decision`, `pattern`, `discovery`, `work_item`, `document`, `commit`, `note`

## Edge types

`depends_on`, `informed_by`, `supersedes`, `relates_to`, `implements`, `extracted_from`
