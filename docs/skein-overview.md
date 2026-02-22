# Skein — Knowledge Graph for AI-Assisted Work

## What It Does

Skein is a knowledge graph that accumulates what you learn across projects — decisions you made, patterns you noticed, discoveries, commits, documents — and makes all of it searchable by meaning, not just keywords.

The problem it solves: when you're working across multiple projects over time, useful context gets buried in old activity logs, commit messages, and forgotten documents. Skein captures all of that into a single searchable graph so AI agents (and humans) can surface relevant knowledge when they need it.

## How It Works

### Storage

A single SQLite file (`skein.db`) with four tables:

- **nodes** — each piece of knowledge (a decision, a pattern, a document, a commit, a note)
- **edges** — explicit relationships between nodes (depends_on, informed_by, supersedes, relates_to, etc.)
- **embeddings** — 384-dimension vectors generated locally by fastembed, stored as raw BLOBs
- **sync_state** — tracks incremental sync cursors for each data source

### Search

When you query Skein, it runs two searches in parallel:

1. **Full-text search (FTS5)** — keyword matching with BM25 ranking
2. **Vector similarity** — embeds your query text, computes cosine similarity against all stored vectors using brute-force NumPy

Both scores are normalized to [0, 1] and combined with a weighted sum (40% FTS, 60% vector). This means you get results whether you use the exact words or just describe the concept in different language.

### Interface

Skein runs as an MCP (Model Context Protocol) server, exposing 5 tools that any Claude Code session can call:

| Tool | What It Does |
|------|-------------|
| `skein_search` | Combined FTS + vector search, with optional type/project filters |
| `skein_get` | Retrieve a node and its graph neighborhood (configurable depth) |
| `skein_add` | Add a knowledge node — auto-generates embedding, optional edges |
| `skein_connect` | Create a relationship edge between two existing nodes |
| `skein_status` | Overview: counts by type/project, recent nodes, sync state |

### Tech Stack

- **Python** — better ecosystem for embeddings and vector math
- **SQLite with FTS5** — single-file embedded database, no server dependency
- **fastembed** (BAAI/bge-small-en-v1.5) — local ONNX-based embeddings, runs on CPU, no API key needed
- **NumPy** — brute-force cosine similarity (fast enough for thousands of nodes)
- **FastMCP** — MCP server framework (stdio transport for Claude Code integration)

Everything runs locally. No external services, no API keys, no network dependency.

## How Skein Interacts with WCP

**WCP** (Work Context Protocol) is a structured work tracker that stores work items as markdown files with YAML frontmatter — tasks, bugs, features, each with status, priority, activity logs, and attached artifacts (PRDs, architecture plans, etc.).

**Skein reads WCP data as one of its input sources.** The key design point: WCP doesn't know Skein exists. WCP keeps doing its thing — structured work tracking. Skein reads those files and builds a searchable knowledge graph on top.

```
+-------------------+          +-------------------+
|   wcp-data/       |  reads   |   Skein           |
|                   +--------->|                   |
|  SKEIN/SKEIN-1.md |  files   |  nodes table      |
|  PIPE/PIPE-3.md   | directly |  embeddings table |
|  artifacts/       |          |  edges table      |
+-------------------+          +-------------------+
```

The WCP connector:

- Reads markdown files directly from the `wcp-data/` directory (not through the WCP MCP server)
- Each work item becomes a `work_item` node in the graph
- Each artifact file (PRDs, plans, proposals) becomes a `document` node
- Parent/child relationships and artifact attachments become edges
- Activity logs are stored as part of the work item node body
- Runs incrementally — checks timestamps and only processes what changed

### Other Data Sources (Planned)

Beyond WCP, Skein will also ingest:

- **Git history** — commits become nodes, commit messages referencing work items create cross-links
- **Filesystem** — standalone markdown files in configured directories become document nodes

## The End State

When you're working on any project, you can search Skein and find relevant decisions and patterns from *other* projects — connections that would otherwise stay buried in old activity logs and forgotten documents. The graph grows over time as you work, and the more you put in, the more useful cross-project connections emerge.
