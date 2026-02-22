# Skein

A knowledge graph for AI-assisted knowledge work. Skein ingests data from work trackers, git repos, and markdown files, builds a searchable graph of decisions, patterns, and discoveries, and exposes it to AI agents via MCP.

## What it does

- **Semantic search** across all your knowledge (FTS + vector similarity)
- **Graph traversal** to explore connected decisions and context
- **Connectors** that sync external data sources into the graph
- **MCP server** so Claude Code (or any MCP client) can query it directly

## Quick start

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
# Clone and install
git clone https://github.com/yourusername/skein.git
cd skein
uv sync

# Configure
cp skein.yaml.example skein.yaml
# Edit skein.yaml — set your paths

# Run the MCP server
uv run python -m skein
```

## Register with Claude Code

Add to `~/.claude.json` under `mcpServers`:

```json
{
  "mcpServers": {
    "skein": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/skein", "python", "-m", "skein"]
    }
  }
}
```

Restart Claude Code. You'll have these tools available:

| Tool | What it does |
|------|-------------|
| `skein_search` | FTS + vector similarity search, filtered by type/project |
| `skein_get` | Get a node + its graph neighborhood (N hops) |
| `skein_add` | Add a knowledge node with auto-embedding |
| `skein_connect` | Create an edge between two nodes |
| `skein_sync` | Run connectors to ingest external data |
| `skein_status` | Counts by type/project, recent nodes, sync state |

## Configuration

`skein.yaml`:

```yaml
# Path to SQLite database (created on first run)
db_path: ./skein.db

# Local embedding model (no API key needed)
embedding_model: BAAI/bge-small-en-v1.5

# WCP data directory (optional — only if you use WCP)
wcp_data_path: /path/to/your/wcp-data
```

## Connectors

### WCP (Work Context Protocol)

If you use [WCP](https://github.com/yourusername/wcp) for work tracking, Skein can sync all your work items and artifacts into the graph.

Set `wcp_data_path` in `skein.yaml` to your WCP data directory, then:

```
skein_sync connector=wcp
```

This creates:
- One `work_item` node per WCP item (with activity logs)
- One `document` node per artifact file
- `depends_on` edges from parent relationships
- `relates_to` edges from artifact attachments

Incremental by default — only re-processes files modified since last sync. Use `full=true` to re-sync everything.

### Git / Filesystem (planned)

Git connector (commit history + cross-links to work items) and filesystem connector (markdown file scanning) are planned for future phases.

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
