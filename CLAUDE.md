# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```sh
uv run python -m pytest                          # run all tests
uv run python -m pytest tests/test_drain.py      # run one test file
uv run python -m pytest -k "test_fuzzy"          # run tests matching name
uv run seshi                           # launch the TUI
uv run seshi doctor --fix              # health check + auto-repair
```

## Architecture

Seshi is a session manager for Claude Code. It captures session metadata via a hook, stores it in SQLite, and provides a TUI and CLI for searching/resuming sessions.

### Data flow

```
Claude Code → hook.sh → ~/.seshi/queue.jsonl → drain_queue() → SQLite → TUI/CLI
```

1. **Hook** (`hook/hook.sh`): Bash script registered in `~/.claude/settings.json` on `SessionStart` and `Stop` events. Reads JSON from stdin, captures argv/git/env, appends JSONL to the queue. Must never write to stdout/stderr.
2. **Queue drain** (`drain.py`): Runs on every CLI invocation before any subcommand. Reads the JSONL queue, upserts into SQLite in a single transaction, truncates the queue. `INSERT OR IGNORE` for starts, `UPDATE` for stops.
3. **Startup tasks** (`cli.py`): After draining the queue, `age_frecency_ranks()` decays session scores (rate-limited to every 300s) and `auto_scan()` discovers new sessions from `~/.claude/projects/` (rate-limited to every 120s). Both are rate-limited via settings and wrapped in try/except to never break startup.
4. **Registry** (`db.py`): SQLite with WAL mode. Tables: `sessions`, `tags`, `settings`, `project_favorites`, `prompts`, `prompt_index_meta`. `open_db()` context manager auto-initializes schema.

### Stdout protocol (critical constraint)

The shell wrapper `seshi()` captures stdout via `$(command seshi "$@")` and `eval`s resume lines. This means:
- The TUI renders to `/dev/tty`, never stdout
- Resume lines (`cd <cwd> && exec claude --resume <id>`) go to real stdout via `sys.__stdout__`
- `launch_tui()` in `tui/app.py` handles the `/dev/tty` redirection

### CLI structure

`cli.py` defines a `SeshiGroup` (Click group) that routes unknown subcommands to fuzzy resume. Each command in `commands/` registers itself on the `main` group via import at the bottom of `cli.py`.

### Session resolution

All commands that take a session identifier use `search.session_resolve()`: try `custom_name` (case-insensitive) first, then `session_id`. Fuzzy resume uses `rank_sessions()` with weighted field scores (name×4, prompt×2, cwd×1, transcript×1 via FTS5, individual prompts×1.5), boosted by frecency (1×–2× multiplier) so frequently-used sessions win ties. Transcript search uses FTS5 full-text indexing with Porter stemming and prefix matching.

### Path unsanitization

Claude Code encodes project dirs by replacing `/` with `-`. `paths.unsanitize_path()` uses power-set enumeration (≤6 dashes) to resolve the ambiguity. `resolve_best_cwd()` picks the first candidate that exists on disk.

### Settings patch

`settings.py` patches `~/.claude/settings.json` to register the hook. `hook_manager.py` copies the bundled `hook.sh` to `~/.seshi/hook.sh`. Both operations are idempotent.

### Transcript index

`transcript_index.py` provides FTS5 full-text indexing of session transcripts. `extract_full_text()` reads JSONL transcript files and extracts text content. `index_session()` indexes a single session, `index_pending()` indexes all unindexed sessions. `search_transcripts()` runs FTS5 queries with Porter stemming and prefix matching. Indexing runs asynchronously on TUI mount (via Textual worker) and after `seshi scan`. Query terms are double-quoted to prevent FTS5 boolean operator interpretation.

### Prompt index

`prompt_index.py` extracts individual user prompts from JSONL transcripts and stores them in the `prompts` table. `index_session_prompts()` indexes a single session, `index_pending_prompts()` indexes all unindexed sessions. Uses `prompt_index_meta` to track file sizes for incremental re-indexing. Runs alongside transcript FTS indexing in both `scan_projects()` and the TUI's async background worker.

### TUI

Built with Textual. `SeshiApp` has four views (sessions, overview, projects, help) switched via tab/number keys. `SessionsList` is the primary widget handling navigation, inline rename, tagging, and bulk selection. Each session displays its user prompts as indented sub-rows (with `│` connector), all expanded by default. Sessions can be collapsed/expanded with `e` (single) or `E` (all). Search auto-expands sessions with matching prompts. The preview pane focuses on the selected prompt's conversation context and highlights search terms.

### Dependencies

Before starting work, check all dependencies in `pyproject.toml` against their latest versions (`uv pip list --outdated` or PyPI). Suggest updates for any outdated packages. When adding new imports, verify the package is listed in `[project.dependencies]` — if missing, add it and run `uv lock && uv sync`. After any dependency changes, commit the updated `pyproject.toml` and `uv.lock` together.

### Testing

Tests use a `tmp_db` fixture (in-memory SQLite with schema initialized). Tests mock paths like `CLAUDE_SETTINGS` and `QUEUE_PATH` to avoid touching real user data. The suite includes unit tests for core logic and Textual-based TUI regression tests.
