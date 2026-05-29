# Seshi — Specification

## 1. Executive Summary

**Seshi** (invoked as `seshi`) is a global session manager and resumer for Claude Code. It solves a specific problem: Claude Code sessions are ephemeral and hard to find after closing. Users who work across many projects accumulate hundreds of chat sessions with no way to search, organize, or quickly resume them. Seshi captures metadata from every Claude Code session via a transparent hook, indexes it into a local registry, and provides a terminal UI (TUI) and CLI for searching, tagging, renaming, filtering, and resuming any session from any directory.

The tool intercepts session lifecycle events (start/stop) from Claude Code through its hook system, stores structured metadata in a local database, and renders a multi-view TUI with live search. When the user selects a session, the tool emits a shell command that `cd`s into the original project directory and resumes the Claude Code process with its original flags. The shell wrapper `eval`s this output so the parent shell actually changes directory — a critical design constraint that shapes the entire stdout protocol.

- **Project type**: CLI tool with interactive TUI
- **Complexity assessment**: moderate
- **Estimated rebuild effort**: 3–4 developer-weeks

---

## 2. Project Statistics

> Statistics as of initial specification. Current values may differ.

| Metric | Value |
|--------|-------|
| Source files | ~40 |
| Total LOC | ~3,100 |
| Test files | 15 |
| Test cases | 108 |

---

## 3. Architecture

### Architecture Pattern

Event-driven pipeline with command dispatch. The system has three layers:

1. **Event capture** — a hook script fires on every Claude Code `SessionStart` and `Stop` event, appending a JSON line to an append-only queue file.
2. **Registry** — on every CLI invocation, the queue is drained into a local database (idempotent upserts). The database is the source of truth for all session metadata.
3. **Interface** — a command dispatcher routes to subcommands. The TUI is the primary interface; CLI subcommands handle automation and one-shot operations.

### System Components

| Component | Responsibility |
|-----------|---------------|
| **Hook** | Captures session metadata (cwd, argv, git state, env vars, transcript stats) on start/stop events. Writes to an append-only queue. Must be completely silent (no stdout/stderr). |
| **Queue drainer** | Reads the JSONL queue, upserts into the database within a transaction, then truncates the queue file. Idempotent — `INSERT OR IGNORE` keyed on `session_id`. |
| **Registry (database)** | Stores sessions, tags, settings, project favorites, individual user prompts, and indexing metadata. Provides indexed queries for listing, filtering, and searching. |
| **Search engine** | Fuzzy matching with configurable field weights, plus FTS5 full-text transcript search with Porter stemming and prefix matching. Filters by cwd, tags (AND semantics), and text query. |
| **TUI** | Four-view terminal interface (sessions, overview, projects, help) rendered to `/dev/tty` to avoid polluting captured stdout. |
| **Resume builder** | Constructs a `cd <cwd> && exec claude <flags> --resume <id>` line, stripping prior `--resume` flags and shell-quoting all values. |
| **Shell wrapper** | A shell function (`seshi()`) that captures the binary's stdout and `eval`s resume lines. Non-resume output is printed directly. |
| **Path resolver** | Reverse-engineers filesystem paths from Claude's dash-encoded project directory names, handling ambiguous dash-vs-slash boundaries via power-set enumeration. |

### External Dependencies

| Dependency | Role |
|------------|------|
| Claude Code | The application being managed. Required on PATH for `auto-name` (shells out to `claude -p`). |
| `/dev/tty` | The TUI renders here to keep stdout clean for the shell wrapper protocol. |
| `~/.claude/projects/` | Claude Code's transcript storage. Read for backfill scanning, export, grep, and preview. |
| `~/.claude/settings.json` | Patched to register the hook on `SessionStart` and `Stop` events. |

---

## 4. Functional Requirements

### 5.1 Session Capture

**Description**: Automatically capture metadata for every Claude Code session without user intervention.

**Acceptance criteria**:
- Hook fires on every `SessionStart` and `Stop` event
- Hook never writes to stdout or stderr (completely silent)
- Captured data: `session_id`, `cwd`, parent process argv, git branch/SHA, environment variables (`ANTHROPIC_MODEL`, `ANTHROPIC_BASE_URL`, `CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX`, `CLAUDE_CODE_MAX_OUTPUT_TOKENS`), `origin_host`
- On stop: `message_count`, `token_count`, `first_prompt` (first 200 chars of first user message)
- Missing `session_id` → silent exit (no error)
- Queue file is append-only; draining is handled by the CLI binary

**Business rules**:
- Parent argv captured via `/proc/$PPID/cmdline` (Linux) or `ps -o args=` (macOS)
- Git metadata only captured if `cwd` is a git repository
- First prompt extracted from transcript JSONL: first message where `role === "user"`, truncated to 200 characters
- Token count = sum of `input_tokens + output_tokens` from all usage blocks

### 5.2 Session Registry

**Description**: Maintain a durable, queryable index of all sessions.

**Acceptance criteria**:
- Queue drained on every CLI invocation (before any subcommand runs)
- After draining, `age_frecency_ranks()` decays session scores (rate-limited to every 300s) and `auto_scan()` discovers new sessions from transcript files on disk (rate-limited to every 120s). Both are silent on failure.
- Draining is idempotent: `INSERT OR IGNORE` keyed on `session_id`
- Draining preserves user-set metadata (`custom_name`, `is_favorite`, tags)
- Stop events update `message_count`, `token_count`, `last_activity_at`, and `status`
- `first_prompt` populated at stop time only if not already set at start time (`COALESCE`)
- Queue file truncated after successful drain

**Edge cases**:
- Malformed JSON lines in queue are silently skipped
- Missing queue file is a no-op
- Stop event for unknown `session_id` is silently ignored

### 5.3 Backfill Scanning

**Description**: Discover existing sessions from Claude Code's transcript files on disk.

**Flags**:
- `--verbose`: print progress during scanning (directories visited, sessions discovered, transcripts parsed)

**Acceptance criteria**:
- Scans Claude Code's projects directory for session transcripts
- After scanning, triggers FTS transcript indexing via `index_pending()` to build the full-text search index
- Two patterns recognized:
  - **Pattern A**: `<session-id>.jsonl` files at the project subdirectory level
  - **Pattern B**: `<session-id>/` directories (UUID format) with no matching top-level JSONL
- Backfilled sessions marked with `is_backfilled = 1`
- Idempotent: re-running returns 0 newly inserted
- `skill-injections.jsonl` excluded from scanning
- Parses transcripts to extract `first_prompt`, `message_count`, `token_count`, timestamps

**Business rules**:
- Project directory names use Claude's dash-encoding: leading dash = `/`, subsequent dashes are ambiguous (could be path separator or literal dash in directory name)
- Path resolution uses power-set enumeration for up to 6 ambiguous dashes (≤64 candidates); falls back to heuristic for more
- For dotfile directories (e.g. `/.vault`), Claude encodes as `--vault`; the resolver handles `--` → `-.` rewriting
- Existing filesystem paths are preferred over candidates that don't resolve
- Repair pass: fixes backfilled rows whose stored `cwd` no longer resolves on disk (from older buggy unsanitization)

### 5.4 TUI — Sessions View

**Description**: Interactive session picker with BM25-ranked search, project-path grouping, sort modes, and inline actions.

**Acceptance criteria**:
- Sessions displayed in groups: `★ favorites` first, then grouped by project path with headers showing `── ~/path (lang) Xh ago ──`
- Each row shows: favorite mark, title (custom_name or first_prompt), tag chips (at ≥60 char width)
- Live search: any typed character filters the list in real time
- `#tag` tokens in search filter by tag (AND semantics for multiple tags)
- Selected row highlighted with accent-colored background

**Sort modes**: three sort modes, cycled with the `s` key. Active sort mode displayed in the search bar area.

| Mode | Behavior | Default |
|------|----------|---------|
| **Frecency** | Combines recency and frequency into a single score (see section 9) | Yes |
| **Recency** | Ordered by `last_activity_at DESC` (most recently active first) | No |
| **Frequency** | Ordered by session count per `cwd`, then by `last_activity_at DESC` within each group | No |

Favorites always sort to the top regardless of sort mode. Sort mode is persisted in the `sort_mode` setting.

**Navigation**: `↑↓`/`jk` move, `Ctrl-u`/`Ctrl-d` page, `g`/`G` top/bottom

**Actions**:
| Key | Action | Details |
|-----|--------|---------|
| `Enter` | Resume | Emits resume line to stdout |
| `r` | Rename | Inline edit; sets `custom_name` (null to clear) |
| `t` | Tag | Toggle a tag on/off for current session (or bulk selection) |
| `f` | Favorite | Toggles `is_favorite` (favorites sort to top) |
| `u` | Archive | Toggles `is_archived` (hides from views). Reversible alternative to delete |
| `d` | Delete | Removes from registry (with confirmation). Bulk: deletes all selected |
| `s` | Sort mode | Cycles through: frecency → recency → frequency (persisted) |
| `H` | Hide missing | Toggles `hide_missing_dirs` setting (persisted) |
| `Space` | Select | Toggles row in/out of bulk selection (`[x]` mark) |
| `Ctrl-a` | Select all | Adds all visible rows to selection |
| `Esc` | Clear/Quit | Clears selection if non-empty; otherwise quits |

**Tag input rules**: only `[\w\-]` characters allowed. Toggle behavior: if session already has the tag, remove it; otherwise add it.

**Delete recovery**: deleted sessions can be re-discovered by running `seshi scan`, since transcript files on disk are never removed. For reversible hiding, use archive (`u` key) instead of delete.

### 5.5 TUI — Overview View

**Description**: Aggregate statistics dashboard.

**Content**:
- Totals: sessions, favorites, messages, tokens, estimated cost
- 30-day session sparkline (Unicode block characters `▁▂▃▄▅▆▇█`)
- This-week summary: sessions, tokens, cost
- By-model breakdown: per-model session count and aggregate cost, sorted by cost descending (top 8)
- Span: oldest and newest session dates

### 5.6 TUI — Projects View

**Description**: Per-directory session grouping with visual bar chart.

**Content**:
- Rows grouped by `cwd`, ordered by last activity
- Language tag per project (detected from manifest files on disk)
- Horizontal bar sized proportionally to session count
- Session count and relative time per project

### 5.7 TUI — Help View

**Description**: Full keymap reference, grouped by category (navigation, actions, bulk select, search & filter, shell-only commands).

### 5.8 Resume and Search Resume

**Description**: Resume a session by ID, name, or search query.

**Explicit resume** (`seshi resume <id|name>`): looks up the session by exact `session_id` or case-insensitive `custom_name` match. If not found, exits with error. Intended for scripting and tab-completed invocations.

**TUI search** (`seshi <query>`): opens the TUI with the search bar pre-populated with `<query>` and results filtered. When the argument doesn't match a subcommand, the CLI routes to the TUI. For non-interactive search resume, use `seshi resume <query>`.

**Business rules**:
1. **Exact match**: case-insensitive `custom_name` or `session_id` match → resume immediately (no prompt)
2. **Multiple exact matches**: open TUI pre-filtered
3. **Fuzzy ranking**: score = max of (`custom_name` × 4, `first_prompt` × 2, `cwd` × 1)
4. **Clear winner**: if top score ≥ second score × 1.4, show confirmation prompt
5. **Ambiguous**: open TUI pre-filtered with query

When `--here` is active, only sessions matching the current `cwd` are considered.

**Confirmation prompt** (rendered to `/dev/tty`):
- Shows: matched name, original query, cwd
- Keys: `Enter` = resume, `t` = open TUI, anything else = cancel
- No controlling terminal → abort (fail closed)

### 5.9 Tab Completion

**Description**: Shell tab-completion for `seshi <name>`. Invoked via `seshi init --completions`.

**Output**: all subcommand names (`resume`, `list`, `rename`, `tag`, `favorite`, `delete`, `archive`, `stats`, `config`, `scan`, `doctor`, `prune`, `export`, `grep`, `auto-name`, `theme`, `init`, `uninstall`) + all distinct `custom_name` values from the registry.

**Shell support**:
- Bash: `complete -F` with `compgen -W`
- Zsh: `compdef` + `compadd` (modern API, not legacy `compctl`). Auto-loads `compinit` if not already loaded.
- Fish: `complete -c seshi -f -a`

### 5.10 Shell Wrapper and Init

**Description**: A shell function (`seshi()`) that makes the parent shell `cd` into the project directory before resuming Claude.

**`seshi init`**: prints the shell wrapper and completion setup. Auto-detects the current shell from `$SHELL` when no argument is provided. Explicit argument (`bash`, `zsh`, `fish`) overrides detection.

**Flags**:
- `--completions`: print only the tab-completion registration (without the wrapper function)

**Protocol**:
- Resume lines match pattern: starts with `cd ` AND contains `&& exec ` → `eval`
- Everything else → `printf '%s\n'` (pass-through)
- Empty output → no-op

### 5.11 Transcript Export

**Description**: Dump a session transcript to stdout.

**Modes**:
- **Raw** (default): outputs the JSONL transcript file as-is
- **Markdown** (`--md`): renders a structured markdown document
- **JSON** (`--json`): outputs a single JSON object with session metadata and messages array

**Markdown format**:
```
# <title>

`<cwd>` · <date> · <N> messages · <N> tokens

---

### user

<message text>

---

### assistant

<message text>

---
```

- Tool-use blocks render as fenced code with the tool name as language hint
- Tool results render in `tool-result` fences
- Title priority: `custom_name` > `first_prompt` > `session_id`
- Session resolved via standard lookup (see section 9)

**Input validation**: rejects IDs containing `/` or `..` (path traversal prevention).

### 5.12 Transcript Grep

**Description**: Full-text search across all session transcripts.

**Flags**:
- `--limit <n>`: max matching messages shown per session (default: 3)
- `--role user|assistant`: filter matches to a specific message role
- `--json`: output as a JSON array of match objects (`session_id`, `cwd`, `last_activity_at`, `role`, `snippet`, `match_offset`)
- `--here`: inherited from global flag — search only sessions matching current cwd

**Behavior**:
- Case-insensitive substring match against message content
- Results sorted by last activity (most recent first)
- Output: session ID (truncated to 8 chars), cwd (home-shortened), relative time, matching role + snippet
- ANSI coral highlighting only when stdout is a TTY and `--no-color` is not set
- Skips `subagents` and `tool-results` directories
- Skips `skill-injections.jsonl`

### 5.13 Auto-Name

**Description**: Generate a human-readable name for a session by summarizing its transcript via Claude.

**Flags**:
- `--all`: batch mode — name all unnamed sessions
- `--limit <n>`: max sessions to name in batch mode (default: 10)

**Behavior**:
- Extracts first 5 messages (max 200 chars each) from transcript
- Sends to `claude -p` with prompt: "Summarize this Claude Code conversation in 3-5 words, kebab-case, lowercase, no quotes."
- Validates output against `/^[a-z][a-z0-9-]+$/`
- Single session (`seshi auto-name <id>`) or batch mode (`--all`)
- Requires `claude` on PATH (checked before starting)

### 5.14 Theme System

**Description**: Five built-in color palettes, switchable and persisted.

| Name | Vibe |
|------|------|
| `coral` (default) | Claude brand — coral on warm off-white |
| `catppuccin` | Catppuccin Mocha — pink/lavender |
| `gruvbox` | Gruvbox dark — burnt orange |
| `nord` | Nord — frost cyan on slate |
| `mono` | Pure monochrome — works on any terminal |

**Palette fields**: `accent`, `accentSoft`, `accentDeep`, `fg`, `fgMuted`, `fgDim`, `bgSelected`, `fgSelected`, `border`, `borderDim`, `user`, `assistant`

**Commands**: `theme list`, `theme <name>`, `theme reset`

**Relationship to `seshi config`**: `seshi theme <name>` is a convenience command equivalent to `seshi config theme <name>`, but also supports `list` (preview all palettes) and `reset` (restore default). Use `seshi theme` for interactive exploration; `seshi config theme` for scripting.

### 5.15 Prune

**Description**: Delete old sessions from registry.

**Flags**:
- `--dry-run`: preview which sessions would be deleted without mutating the database. Prints count and list of affected sessions.
- `--days <n>`: override the persisted `prune_days` setting for this invocation only (does not change the stored setting)

**Rules**:
- Controlled by `prune_days` setting (default `0` = disabled), overridden by `--days`
- Only deletes sessions where: `last_activity_at < cutoff` AND `is_favorite = 0` AND `custom_name IS NULL`
- Favorites and named sessions are always protected

### 5.16 Doctor

**Description**: Health check with 5 checks.

**Flags**:
- `--fix`: auto-repair common issues (create missing directories, re-install hook script, re-patch settings). Reports each fix applied.

| Check | What it verifies | Auto-fix action |
|-------|------------------|-----------------|
| Registry directory | `~/.seshi/` exists | Create directory |
| Hook installed | Hook script exists and is executable (mode `& 0o111`) | Re-install hook script |
| Registry DB | Database file exists | Initialize database |
| Settings patched | `~/.claude/settings.json` contains hook commands referencing `.seshi/hook.sh` | Re-patch settings |
| Claude on PATH | `claude` binary is findable in `$PATH` | (no auto-fix — manual install required) |

### 5.17 Uninstall

**Description**: Removes the hook and settings patch. Registry is preserved unless `--purge` is passed.

**Flags**:
- `--purge`: also deletes the `~/.seshi/` directory (database, queue, hook script). Requires interactive confirmation unless combined with `--force`.

### 5.18 List

**Description**: Non-interactive session listing for scripting and piping.

**Output formats**:
- Default (human-readable): one line per session with truncated fields, similar to TUI row format
- `--json`: JSON array of session objects (all fields)
- `--tsv`: tab-separated values with header row

**Flags**:
- `--limit <n>`: max number of sessions to output (default: all)
- `--tag <tag>`: filter to sessions with this tag. Repeatable for AND semantics (`--tag bug --tag wip` = sessions with both tags)
- `--sort frecency|recency|frequency`: override the persisted `sort_mode` for this invocation
- `--archived`: include archived sessions in output
- `--here`: inherited from global flag — filter to current cwd

**Ordering**: uses `--sort` if provided, otherwise respects the persisted `sort_mode` setting.

### 5.19 Rename

**Description**: Set or clear a session's custom name from the CLI.

**Usage**: `seshi rename <id|name> <new-name>`

**Flags**:
- `--clear`: remove the custom name (set to null)

**Business rules**:
- Session resolved via standard lookup (see section 9)
- New name validated against same rules as TUI rename (non-empty string)
- Warns if name is already in use by another session (but allows it)
- Prints confirmation: `renamed <session_id_short> → <new-name>`

### 5.20 Tag

**Description**: Add or remove a tag on a session from the CLI.

**Usage**: `seshi tag <id|name> <tag>`

**Flags**:
- `--remove`: remove the tag instead of adding it

**Business rules**:
- Tag validated against `[\w\-]` character set
- If the tag already exists on the session (and `--remove` is not set), no-op with informational message
- If `--remove` is set and the tag doesn't exist, no-op with informational message
- Session resolved via standard lookup (see section 9)

### 5.21 Favorite

**Description**: Toggle a session's favorite status from the CLI.

**Usage**: `seshi favorite <id|name>`

**Business rules**:
- Toggles `is_favorite` between 0 and 1
- Prints new state: `<session_id_short> favorited` or `<session_id_short> unfavorited`
- Session resolved via standard lookup (see section 9)

### 5.22 Delete

**Description**: Delete a session from the registry via the CLI.

**Usage**: `seshi delete <id|name>`

**Flags**:
- `--force`: skip confirmation prompt

**Design note**: The TUI `d` key deletes without confirmation (optimized for fast interactive workflow where the user can see exactly what's selected). The CLI `delete` command requires `--force` or interactive confirmation because CLI invocations may be scripted and the user can't visually verify the target.

**Business rules**:
- Without `--force`: prompts for confirmation on `/dev/tty` ("delete session <name>? [y/N]")
- Non-interactive terminal without `--force`: exits with error (fail closed)
- Cascades to tags (same as TUI delete)
- Does not delete the underlying JSONL transcript on disk
- Session resolved via standard lookup (see section 9)

### 5.23 Stats

**Description**: Print aggregate statistics to stdout (CLI equivalent of the Overview view).

**Content**:
- Total sessions, favorites, messages, tokens, estimated cost
- This-week summary: sessions, tokens, cost
- Per-model breakdown: session count and cost (top 8)
- Oldest and newest session dates

**Flags**:
- `--json`: output as a single JSON object
- `--here`: inherited from global flag — scope stats to current cwd

### 5.24 Config

**Description**: View or modify persisted settings from the CLI.

**Usage**:
- `seshi config` — list all settings with current values
- `seshi config <key>` — print the value of a single setting
- `seshi config <key> <value>` — set a setting to a new value

**Valid keys**: all keys from the settings table (`prune_days`, `hide_missing_dirs`, `theme`, `sort_mode`, etc.)

**Business rules**:
- Unknown key → error: `unknown setting '<key>'. Available: <comma-separated list>`
- Value validation: `sort_mode` must be one of `frecency`, `recency`, `frequency`; `theme` must be a known theme name; `prune_days` must be a non-negative integer
- List output format: `<key> = <value>` per line

### 5.25 Archive

**Description**: Toggle a session's archived status from the CLI. Archiving is a reversible soft-delete — the session is hidden from all views and listings by default but can be restored.

**Usage**: `seshi archive <id|name>`

**Business rules**:
- Toggles `is_archived` between 0 and 1
- Session resolved via standard lookup (see section 9)
- Archived sessions are excluded from TUI, `seshi list`, `seshi last`, and all other views by default
- `seshi list --archived` includes archived sessions in output
- Prints new state: `<session_id_short> archived` or `<session_id_short> unarchived`

### 5.26 Project Favorite

**Description**: Toggle a project's favorite status or rename its label in the Projects view.

**Usage**:
- `seshi project favorite [<cwd>]` — toggle favorite for the given directory (defaults to current directory)
- `seshi project rename [<cwd>] <name>` — set a display name for the project

**Business rules**:
- Project favorite creates or removes a row in the `project_favorites` table
- Project favorites sort to the top of the Projects view (same pattern as session favorites)
- `custom_name` on `project_favorites` overrides the directory path as the display label in the Projects view
- If `<cwd>` is omitted, uses the current working directory

### 5.27 Project View Actions

**Description**: TUI keys for project management in the Projects view.

| Key | Action | Details |
|-----|--------|---------|
| `f` | Favorite project | Toggles project favorite for the selected project's cwd |
| `r` | Rename project | Sets `custom_name` on the `project_favorites` table for the selected project |
| `Enter` | Open project | Opens TUI Sessions view pre-filtered to the selected project's cwd |

---

## 5. Non-Functional Requirements

### Performance
- Queue drain runs within a database transaction (single write batch)
- TUI session list queries use `useMemo` — re-query only when search/filter/tick state changes
- Lazy loading: command modules imported dynamically only when dispatched
- Tag lookup: single bulk query, O(sessions), cached per render tick
- Language detection: memoized per cwd (avoids repeated filesystem checks)
- Color forcing: `FORCE_COLOR=3` set before any module import to ensure truecolor ANSI

### Reliability
- Hook is fully defensive: every operation wrapped in `|| exit 0` or `|| true`
- Database uses WAL journal mode for crash resistance
- Queue drain is transactional: partial drains are impossible
- Idempotent upserts: re-draining the same events is safe
- Path resolution gracefully degrades: returns first candidate if none exist on disk

### Compatibility
- **Platforms**: Linux and macOS only. Windows is explicitly unsupported (relies on `/proc` and `ps -o args=`)
- **Shells**: bash, zsh, fish. Unknown shells fall back to bash wrapper
- **Terminal**: requires a controlling terminal (`/dev/tty`) for the TUI. Non-interactive invocations fail with a clear error message

---

## 6. Data Model and Storage

### Storage Mechanism

Local embedded database at `~/.seshi/db.sqlite`. WAL journal mode. Foreign keys enabled.

### Schema

#### sessions

| Field | Type | Constraints | Default | Description |
|-------|------|-------------|---------|-------------|
| `session_id` | TEXT | PRIMARY KEY | — | Claude Code session UUID |
| `cwd` | TEXT | NOT NULL | — | Working directory at session start |
| `launch_argv_json` | TEXT | NOT NULL | — | JSON array of the parent `claude` command's argv |
| `env_json` | TEXT | nullable | — | JSON object of captured environment variables |
| `git_branch` | TEXT | nullable | — | Git branch at session start |
| `git_sha` | TEXT | nullable | — | Git commit SHA at session start |
| `first_prompt` | TEXT | nullable | — | First 200 chars of first user message |
| `custom_name` | TEXT | nullable | — | User-assigned memorable name |
| `is_favorite` | INTEGER | NOT NULL | 0 | 1 = pinned to top of list |
| `is_archived` | INTEGER | NOT NULL | 0 | 1 = archived (hidden from views by default, shown with `--archived` flag) |
| `is_backfilled` | INTEGER | NOT NULL | 0 | 1 = discovered from disk scan, not hook |
| `message_count` | INTEGER | NOT NULL | 0 | Total messages in transcript |
| `token_count` | INTEGER | NOT NULL | 0 | Total tokens (input + output) |
| `status` | TEXT | nullable | — | `"done"` when stop event received |
| `created_at` | INTEGER | NOT NULL | — | Unix timestamp of session start |
| `last_activity_at` | INTEGER | NOT NULL | — | Unix timestamp of last event |
| `origin_host` | TEXT | nullable | — | Hostname where session ran (reserved for future multi-machine sync) |
| `schema_version` | INTEGER | NOT NULL | 1 | Schema version for forward compatibility |
| `resume_count` | INTEGER | NOT NULL | 0 | Number of times this session has been resumed |
| `frecency_rank` | REAL | NOT NULL | 1.0 | Decaying frecency score, incremented on resume, scaled down by aging |

**Indexes**:
- `idx_sessions_last_activity`: `(last_activity_at DESC)`
- `idx_sessions_cwd`: `(cwd)`
- `idx_sessions_favorite`: `(is_favorite) WHERE is_favorite = 1` (partial)

#### tags

| Field | Type | Constraints | Default | Description |
|-------|------|-------------|---------|-------------|
| `session_id` | TEXT | NOT NULL, FK → sessions ON DELETE CASCADE | — | Parent session |
| `tag` | TEXT | NOT NULL | — | Tag label (lowercase, `[\w\-]`) |

**Primary key**: `(session_id, tag)`
**Index**: `idx_tags_tag` on `(tag)`

#### settings

| Field | Type | Constraints | Default | Description |
|-------|------|-------------|---------|-------------|
| `key` | TEXT | PRIMARY KEY | — | Setting name |
| `value` | TEXT | — | — | Setting value (string-encoded) |

**Default settings**:

| Key | Default | Description |
|-----|---------|-------------|
| `prune_days` | `"0"` | Days after which non-favorite, non-named sessions can be pruned (0 = disabled) |
| `hide_missing_dirs` | `"0"` | Hide sessions whose `cwd` no longer exists on disk |
| `delete_jsonl_with_session` | `"ask"` | Reserved for future TUI delete confirmation behavior |
| `accent_color` | `"#D97757"` | Legacy accent color override |
| `theme` | `"coral"` | Active TUI palette name |
| `sort_mode` | `"frecency"` | Session list sort mode (`frecency`, `recency`, or `frequency`) |
| `hide_stale_sessions` | `"1"` | Hide sessions whose transcript JSONL no longer exists on disk |
| `schema_version` | `"1"` | Schema version |

#### project_favorites

| Field | Type | Constraints | Default | Description |
|-------|------|-------------|---------|-------------|
| `cwd` | TEXT | PRIMARY KEY | — | Project directory path |
| `custom_name` | TEXT | nullable | — | User-assigned project name |

Used by the Projects view (section 4.27) and `seshi project` CLI commands (section 4.26) to pin and label projects.

#### transcript_fts (FTS5 virtual table)

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | TEXT | Session UUID (used as rowid alias for lookups) |
| `content` | TEXT | Full extracted text content from the session's transcript JSONL |

FTS5 virtual table with Porter stemmer tokenizer. Supports prefix queries and stemmed matching. Populated by `index_pending()` on TUI mount and after `seshi scan`.

#### transcript_index_meta

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `session_id` | TEXT | PRIMARY KEY | Session UUID |
| `file_size` | INTEGER | NOT NULL | Size of the transcript JSONL file at last index time |

Tracks which sessions have been indexed and at what file size, enabling incremental re-indexing when transcripts grow.

### Data Lifecycle

- **Creation**: sessions inserted via queue drain (hook events) or backfill scan
- **Updates**: `custom_name`, `is_favorite`, `is_archived`, tags modified through TUI actions or CLI commands (`seshi rename`, `seshi tag`, `seshi favorite`, `seshi archive`); `message_count`/`token_count`/`status` updated on stop event
- **Aging**: on every CLI invocation (throttled to once per 5 minutes), if the sum of `frecency_rank` across all live (non-archived, non-stale) sessions exceeds 1000, all live ranks are scaled by `0.9 × 1000 / total`. Sessions whose rank falls below 1.0 are auto-archived — unless they are favorited, named, or tagged.
- **Archival**: `seshi archive` or `u` key in TUI toggles `is_archived` — hides session from views without deleting data. Reversible.
- **Hard deletion**: `d` key in TUI (with confirmation dialog) or `seshi delete` (requires `--force` or interactive confirm). Cascades to tags. `seshi prune` bulk-deletes old unprotected sessions.
- **Recovery**: deleted sessions can be re-discovered by running `seshi scan`, since transcript files on disk are never deleted

---

## 7. CLI Interface

### Global Flags

These flags are available on all commands:

| Flag | Description |
|------|-------------|
| `--help`, `-h` | Show help for any command or subcommand |
| `--version`, `-V` | Print version and exit |
| `--no-color` | Disable ANSI color output |
| `--here` | Scope to current working directory (filters sessions whose `cwd` matches). Applies to: TUI, `last`, `resume`, `grep`, `list`, `stats`, `prune`, `auto-name --all` |

`seshi here` is a backward-compatible alias for `seshi --here`.

### Commands

| Command | Flags | Description | Example |
|---------|-------|-------------|---------|
| `seshi` | — | Open TUI session picker | `seshi` |
| `seshi --here` | — | TUI pre-filtered to current directory | `seshi --here` |
| `seshi last` | — | Resume most recent session (no TUI) | `seshi last` |
| `seshi last --here` | — | Resume most recent session in current directory | `seshi last --here` |
| `seshi <query>` | — | Open TUI with search pre-filled | `seshi auth` |
| `seshi resume` | `<id\|name>` | Explicitly resume a session by ID or custom name | `seshi resume auth-rewrite` |
| `seshi list` | `[--json\|--tsv]`, `--limit <n>`, `--tag <tag>`, `--sort <mode>`, `--archived` | List sessions non-interactively (for scripting) | `seshi list --json --here` |
| `seshi rename` | `<id\|name> <new-name>`, `--clear` | Rename a session (--clear removes the name) | `seshi rename abc123 auth-rewrite` |
| `seshi tag` | `<id\|name> <tag>`, `--remove` | Add or remove a tag on a session | `seshi tag auth-rewrite bug` |
| `seshi favorite` | `<id\|name>` | Toggle favorite status | `seshi favorite auth-rewrite` |
| `seshi delete` | `<id\|name>`, `--force` | Delete session from registry | `seshi delete abc123 --force` |
| `seshi archive` | `<id\|name>` | Toggle archive status (reversible soft-delete) | `seshi archive abc123` |
| `seshi project favorite` | `[<cwd>]` | Toggle project favorite (defaults to current dir) | `seshi project favorite` |
| `seshi project rename` | `[<cwd>] <name>` | Set project display name | `seshi project rename my-api` |
| `seshi stats` | `[--json]` | Print overview stats (sessions, tokens, cost, per-model) | `seshi stats --here` |
| `seshi config` | `[<key> [value]]` | Get or set a config value. No args = list all | `seshi config sort_mode recency` |
| `seshi scan` | `[--verbose]` | Backfill sessions from transcript files on disk | `seshi scan` |
| `seshi doctor` | `[--fix]` | Health check (5 checks). --fix auto-repairs issues | `seshi doctor --fix` |
| `seshi prune` | `[--dry-run]`, `[--days <n>]` | Delete sessions older than threshold | `seshi prune --dry-run` |
| `seshi export` | `<id\|name> [--md\|--json]` | Dump session transcript | `seshi export auth-rewrite --md` |
| `seshi grep` | `<pattern>`, `[--limit <n>]`, `[--role user\|assistant]`, `[--json]` | Search message content across transcripts | `seshi grep "websocket" --here` |
| `seshi auto-name` | `<id>` or `--all [--limit <n>]` | Generate name via Claude | `seshi auto-name --all --limit 20` |
| `seshi theme` | `list\|<name>\|reset` | Manage TUI theme | `seshi theme nord` |
| `seshi init` | `[bash\|zsh\|fish]`, `[--completions]` | Print shell wrapper for `eval`. Auto-detects shell if omitted | `eval "$(seshi init)"` |
| `seshi uninstall` | `[--purge]` | Remove hook and settings patch. --purge also deletes `~/.seshi/` | `seshi uninstall` |

---

## 8. User Interface Requirements

### Row Format

Each session row contains:
- **Gutter** (11 chars): selection/favorite mark (`[x]`, `*`, or space), language tag
- **Title** (38 chars): `custom_name` or `first_prompt` or "(untitled)"
- **CWD** (30 chars): shortened with mid-ellipsis if too long
- **Relative time**: "just now", "17m ago", "3h ago", "yesterday", "3d ago", or ISO date for >60 days
- **Tag chips**: `#bug #wip` (shown only if terminal width > 80)

### Language Tags

Detected from manifest files in the session's `cwd`:

| Tag | Detection |
|-----|-----------|
| `rs` | `Cargo.toml` exists |
| `go` | `go.mod` exists |
| `py` | `pyproject.toml` or `requirements.txt` or `setup.py` |
| `ts` | `package.json` + `tsconfig.json` |
| `js` | `package.json` without `tsconfig.json` |
| `rb` | `Gemfile` |
| `dn` | `deno.json` or `deno.jsonc` |
| `jv` | `pom.xml` or `build.gradle` |
| `git` | `.git` directory (fallback when no language manifest found) |

### Time Bucketing

| Bucket | Condition |
|--------|-----------|
| `favorites` | `is_favorite = 1` (always first, regardless of age) |
| `today` | `delta < 86400` |
| `yesterday` | `delta < 2 * 86400` |
| `this week` | `delta < 7 * 86400` |
| `this month` | `delta < 30 * 86400` |
| `older` | everything else |

Buckets use rolling time windows relative to the current moment, not calendar day boundaries.

### Preview Pane

- Shows cwd, message count, token count
- Loads last N messages from the JSONL transcript on disk (lazy, per selection change)
- Role labels: `you` (user), `asst` (assistant), `sys` (system), `tool`
- Messages truncated to 200 chars, whitespace collapsed

### View Navigation

| Key | Action |
|-----|--------|
| `Tab` / `Shift-Tab` | Cycle through views |
| `1` | Sessions |
| `2` | Overview |
| `3` | Projects |
| `?` | Help |

---

## 9. Business Logic and Algorithms

### Session Resolution

Standard lookup used by all commands that accept a session identifier (`resume`, `export`, `rename`, `tag`, `favorite`, `delete`, `archive`, `auto-name`):

```
sessionResolve(identifier):
  match = SELECT WHERE custom_name = identifier (case-insensitive)
  if match: return most recently active match
  match = SELECT WHERE session_id = identifier
  if match: return match
  return NOT_FOUND → exit with "session not found: <identifier>"
```

When multiple sessions share the same `custom_name`, the most recently active one (highest `last_activity_at`) is returned. `seshi rename` warns if the chosen name is already in use but allows it.

### Search Ranking

For `seshi <query>` and `seshi resume <query>`, sessions are ranked via a BM25+RRF pipeline:

1. **Dual FTS5 search**: Session metadata (name, first_prompt, cwd, prompt_text) is indexed into two FTS5 tables — one with Porter stemming (for word-level matching) and one with trigram tokenization (for substring/camelCase matching). Both are queried with per-field BM25 weights: `name=5×, first_prompt=2×, cwd=1×, prompt_text=1.5×`.
2. **Transcript FTS5**: The existing transcript FTS5 table (Porter stemming) is also queried.
3. **RRF merge**: Results from all three sources are combined via Reciprocal Rank Fusion (K=60): `score = Σ 1/(K + rank + 1)` per session across all result lists.
4. **Fallback**: If RRF returns nothing, query terms are corrected via Levenshtein edit distance against a vocabulary table, then RRF is re-run on the corrected query.
5. **Proximity reranking**: Multi-term queries get boosted by title match (terms in session name), minimum span (tightest window containing all terms), and adjacent phrase pairs.

Clear winner threshold: `top_score >= second_score × 1.4`

Search scores are boosted by frecency: `blended = score × (1 + frecency / max_frecency)`. This gives a 1×–2× boost based on relative frecency across the result set, so frequently-used sessions win ties without overriding strong text matches.

### Cost Estimation

Total token count is split into estimated input/output using a fixed 1:3 ratio:

```
input_tokens  = token_count × 0.25
output_tokens = token_count × 0.75
cost = (input_tokens × rate.input + output_tokens × rate.output) / 1,000,000
```

**Per-million-token rates**:

| Model | Input | Output |
|-------|-------|--------|
| claude-opus-4 / 4-1 / 4-5 / 4-7 | $15 | $75 |
| claude-sonnet-4 / 4-5 / 4-6 | $3 | $15 |
| claude-haiku-4-5 | $1 | $5 |
| claude-3-5-sonnet | $3 | $15 |
| claude-3-5-haiku | $0.80 | $4 |
| (unknown/fallback) | $3 | $15 |

**Model detection priority**: `ANTHROPIC_MODEL` env var (from `env_json`) → `--model` flag (from `launch_argv_json`) → fallback

**Currency formatting**: `<$0.01` for tiny amounts, `$X.XX` for < $100, `$X,XXX` (rounded, with comma separator) for ≥ $100

### Path Unsanitization (Dash Ambiguity Resolution)

Claude Code encodes project directories by replacing `/` with `-`. This is ambiguous because directory names can contain literal dashes. The resolver handles this via:

1. Leading `-` always represents `/`
2. For ≤6 ambiguous dashes: enumerate all 2^N combinations of dash-as-separator vs dash-as-literal (power-set)
3. For >6 ambiguous dashes: fall back to all-slashes plus single-dash-preserved variants
4. Special case: `--` may represent `/.` (dotfile directory)
5. Return the first candidate that exists on the filesystem; if none exist, return the all-slashes form

### Resume Line Construction

```
buildResumeLine(session):
  argv = parse(session.launch_argv_json)
  remove any --resume / --resume=<val> from argv
  ensure argv[0] is "claude"
  append --resume <session_id>
  shell-quote each argument
  return "cd <quoted_cwd> && exec <quoted_argv>\n"
```

**Shell quoting**: arguments matching `/^[A-Za-z0-9_./@:=-]+$/` pass through unquoted; everything else wrapped in single quotes with internal `'` escaped as `'\''`.

### Session List Ordering

Sessions are ordered according to the active sort mode. Favorites always sort first (`is_favorite DESC`).

**Recency**: ordered by `last_activity_at DESC`.

**Frequency**: sessions ordered by `resume_count` descending, then by `last_activity_at DESC` to break ties.

**Frecency** (default): combines recency and frequency into a single score per session using multiplicative blending:

```
frecencyScore(session, now):
  age_hours = (now - last_activity_at) / 3600
  multiplier = stepFunction(age_hours):
    < 4 hours  → 4.0
    < 1 day    → 2.0
    < 1 week   → 1.0
    < 4 weeks  → 0.5
    ≥ 4 weeks  → 0.25
  return frecency_rank × multiplier
```

`frecency_rank` starts at 1.0 for new sessions and increments by 1.0 on each resume. The step-function decay gives a strong boost to sessions accessed in the last few hours while penalizing stale ones. The multiplicative blend means frequently-resumed sessions always score proportionally higher than rarely-used ones at the same age.

Then filtered client-side by: cwd match → tag AND filter → BM25+RRF text search (if query present).

---

## 10. Cross-Cutting Concerns

### Error Handling Strategy

- **Hook**: fully defensive. Every command wrapped in `|| exit 0` or `|| true`. Never crashes, never produces output.
- **CLI commands**: errors written to stderr, exit with non-zero status. Database always closed in `finally` blocks.
- **TUI**: renders to `/dev/tty` independently of stdout. If `/dev/tty` is unavailable, exits with clear error message.
- **Queue drain**: malformed JSON lines silently skipped. Wrapped in a database transaction — atomically committed or rolled back.
- **Path resolution**: returns best-effort result; never throws.

### Stdout Protocol

The single most important cross-cutting constraint: **stdout is a communication channel to the shell wrapper, not a display channel to the user.**

- TUI renders to `/dev/tty`, never stdout
- Only resume lines (`cd ... && exec ...`) go to stdout
- The shell wrapper distinguishes resume lines from informational output by pattern matching
- All user-visible output (doctor, scan summary, help) also goes to stdout but doesn't match the resume pattern, so the wrapper prints it directly

### Color Handling

- `FORCE_COLOR=3` set at process startup (before any module imports) to force truecolor ANSI
- This is necessary because the shell wrapper captures stdout via `$(...)`, which makes chalk's auto-detect see a non-TTY pipe and disable colors
- Since the TUI renders to `/dev/tty` (not the captured pipe), forced truecolor is correct
- `--no-color` global flag disables all ANSI output (sets `NO_COLOR=1`, overrides `FORCE_COLOR`)
- Grep output conditionally uses ANSI: only when `process.stdout.isTTY` is true and `--no-color` is not set

### Database Access Pattern

- All commands open the database, operate, and close in a `try/finally` block
- Settings reads use `readonly: true` where possible (theme loading at module import time)
- The TUI keeps the database open for its entire lifecycle (passed as a prop)
- Bulk operations use prepared statements within transactions

---

## 11. Error Taxonomy

| Error Condition | Component | User-Facing Message | Exit Code |
|-----------------|-----------|---------------------|-----------|
| No controlling terminal | TUI | "seshi: no controlling terminal — run `seshi` interactively from a shell." | 1 |
| No controlling terminal (confirm) | Fuzzy | "seshi: no terminal for confirmation; aborting." | 0 (silent cancel) |
| No sessions in registry | `last` | "no sessions in registry. Run `seshi scan` to discover existing sessions." | 1 |
| Session not found | `resume`, `export`, `rename`, `tag`, `favorite`, `delete`, `archive`, `auto-name` | "session not found: <id>" | 1 |
| Claude not on PATH | `auto-name` | "error: 'claude' not found on PATH. Install Claude Code first." | 1 |
| Auto-name generation failed | `auto-name` | "could not generate a valid name (no transcript or claude returned invalid output)" | 1 |
| Projects directory not found | `export`, `grep` | "projects directory not found: <path>" | 1 |
| No transcript found | `export` | "no transcript found for session <id>" | 1 |
| Invalid session ID (path traversal) | `export` | "invalid session id" | 2 |
| Missing usage arguments | `export`, `grep`, `auto-name` | "usage: seshi <command> ..." | 2 |
| Unknown theme | `theme` | "unknown theme '<name>'. Available: ..." | 1 |
| Prune disabled | `prune` | "prune_days = 0 (disabled)." | 0 |
| Doctor checks failed | `doctor` | Per-check `[FAIL]` lines + fix suggestions | 1 |
| Delete without confirmation | `delete` | "use --force to delete without confirmation, or run interactively." | 1 |
| Unknown config key | `config` | "unknown setting '<key>'. Available: <list>" | 1 |
| Invalid config value | `config` | "invalid value '<value>' for <key>. Expected: <constraint>" | 1 |
| Conflicting format flags | `list`, `export` | "cannot combine --json and --tsv" / "cannot combine --json and --md" | 2 |
| Missing required argument | `rename`, `tag`, `delete`, `archive`, `resume` | "usage: seshi <command> ..." | 2 |
| Project not found | `project rename` | "no project_favorites entry for <cwd>" | 1 |

---

## 12. Integration Requirements

### Claude Code Hook System

**Integration point**: `~/.claude/settings.json` → `hooks.SessionStart` and `hooks.Stop`

**Hook registration format**:
```json
{
  "hooks": {
    "SessionStart": [{
      "matcher": ".*",
      "hooks": [{ "type": "command", "command": "<hook_path> start" }]
    }],
    "Stop": [{
      "matcher": ".*",
      "hooks": [{ "type": "command", "command": "<hook_path> stop" }]
    }]
  }
}
```

**Patching behavior**: non-destructive merge — existing keys and other hooks preserved. Idempotent (doesn't double-insert). Unpatch removes only our entries.

### Claude Code Transcripts

**Read-only access** to `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`

**JSONL format** (per line):
```json
{
  "timestamp": "ISO-8601",
  "message": {
    "role": "user|assistant|system",
    "content": "string" | [{"type": "text", "text": "..."}, {"type": "tool_use", "name": "...", "input": {...}}],
    "usage": {"input_tokens": N, "output_tokens": N}
  }
}
```

### Claude CLI (`claude -p`)

Used by `auto-name` to generate session names. Inherits the user's existing Claude authentication — no API key management needed.

---

## 13. Configuration and Environment

### Files

| File | Purpose |
|------|---------|
| `~/.seshi/db.sqlite` | Session registry database |
| `~/.seshi/queue.jsonl` | Append-only event queue (drained on each CLI invocation) |
| `~/.seshi/hook.sh` | Hook script installed into Claude Code |
| `~/.claude/settings.json` | Patched to register the hook |

### Environment Variables Captured by Hook

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_MODEL` | Model name override |
| `ANTHROPIC_BASE_URL` | Custom API endpoint |
| `CLAUDE_CODE_USE_BEDROCK` | AWS Bedrock flag |
| `CLAUDE_CODE_USE_VERTEX` | Google Vertex flag |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | Token limit override |

### Installation Process

1. Create `~/.seshi/` directory
2. Copy hook script, set executable permission (`0o755`)
3. Patch `~/.claude/settings.json` with hook entries
4. Initialize database (create tables, seed default settings)
5. Run initial backfill scan of `~/.claude/projects/`
6. User adds `eval "$(seshi init)"` to their shell rc file (auto-detects shell from `$SHELL`)

---

## 14. Testing Requirements

### Test Coverage

**108 test cases across 15 files** covering:

| Area | Tests | Coverage |
|------|-------|----------|
| Resume line construction | 8 | Shell quoting, argv stripping, edge cases |
| Theme system | 9 | Palette validation, persistence, defaults |
| Queue drain | 9 | Idempotency, malformed data, field preservation |
| End-to-end flow | 1 | Queue → drain → list → resume |
| Shell init | 8 | Bash/zsh/fish wrappers, completion, resume-line detection |
| Tags | 7 | AND filtering, toggle, text+tag combined queries |
| Markdown export | 8 | Format, tool blocks, empty transcripts |
| Path resolution | 7 | Dash ambiguity, dotfiles, existing-path preference |
| Settings patch | 6 | Patch/unpatch, idempotency, missing file handling |
| Hook script | 3 | Start/stop events, missing session_id |
| Registry/search | 8 | DB creation, default settings, BM25+RRF search, favorites sort |
| Pricing | 18 | Cost calculation, formatting, model detection, edge cases |
| Grep | 6 | Case sensitivity, file exclusions, content extraction |
| Scan | 6 | Both patterns, idempotency, skill-injections exclusion |
| Transcript index | 41 | FTS5 indexing, search semantics (stemming, prefix, case, multi-term), operator quoting, schema, graceful degradation |
| Sanity | 1 | Test harness smoke test |

### New Test Areas Required

| Area | Coverage |
|------|----------|
| `list` command | Output formats (JSON, TSV, human-readable), `--limit`, `--tag` filtering, `--here` scoping |
| CRUD commands | `rename` (set/clear), `tag` (add/remove/idempotent), `favorite` (toggle), `delete` (with/without --force) |
| `config` command | Get/set, list all, invalid key, value validation |
| `stats` command | JSON output, `--here` scoping, empty registry |
| `prune --dry-run` | Outputs correct candidates without mutating database |
| Global `--here` flag | Filtering across TUI, `last`, `grep`, `list`, `stats` |
| `doctor --fix` | Auto-repair creates missing files, re-patches settings |
| `init` auto-detect | Shell detection from `$SHELL`, `--completions` flag |
| `resume` command | Exact ID lookup, exact name lookup, not-found error |
| `archive` command | Toggle on/off, hidden from list by default, visible with --archived |
| `project` commands | Favorite toggle, rename, Projects view sorting, default to cwd |
| `grep --json` | Structured output format, match fields |
| Session resolution | custom_name precedence, duplicate name handling, case insensitivity |

### Testing Gaps

> **Gap:** No tests for the TUI components themselves (rendering, keyboard input, view switching). The TUI is only testable via manual interaction or the E2E test.

> **Gap:** No tests for the `confirm` prompt (raw terminal input handling).

> **Gap:** No tests for `init --completions` output format.

---

## 15. Constraints, Assumptions, and Risks

### Technical Limitations

- **Linux + macOS only.** Parent argv capture relies on `/proc/$PPID/cmdline` (Linux) or `ps -o args=` (macOS). Windows has no equivalent.
- **No multi-machine sync.** The `origin_host` field is captured and stored but never used for synchronization.
- **TUI delete shows a confirmation dialog.** The `d` key prompts for confirmation before removing sessions from the registry. The underlying JSONL transcript on disk is not deleted. Use `u` (archive) for reversible hiding.
- **`auto-name` requires `claude` on PATH.** It shells out to `claude -p` rather than calling the API directly.
- **Quoted arguments lost on macOS.** `ps -o args=` gives a flat string; whitespace-split loses quoting context for arguments like `--system-prompt "multi word"`.

### Assumptions

- Single-user, single-machine tool
- User has a controlling terminal (TTY) when running `seshi`
- `~/.claude/` directory structure follows Claude Code's conventions
- Claude Code's hook system delivers `session_id` and `cwd` via stdin JSON
- Sessions are uniquely identified by UUID across all projects

### Risks

> **Risk:** The `d` key deletes sessions without confirmation. Accidental keypresses can cause data loss (from the registry; transcripts on disk are preserved). Mitigation: use `u` (archive) instead of `d` for reversible hiding, or run `seshi scan` to re-discover deleted sessions from disk.

> **Risk:** The hook script uses `python3` for JSON serialization. If `python3` is not on PATH, the hook falls back to `sed` for escaping, which may produce malformed JSON for inputs containing complex characters (newlines, backslashes, unicode).

> **Risk:** The `export` command validates against path traversal (`/` and `..`) but accepts any other string as a session ID. Combined with the JSONL file lookup pattern, this is safe because it only constructs paths within `~/.claude/projects/`.

---

## 16. Rebuild Roadmap

| Phase | What to Build | Spec Sections | Dependencies | Effort |
|-------|---------------|---------------|--------------|--------|
| 1. Foundation | Database schema, path constants, settings module | 6, 13 | None | S |
| 2. Hook | Hook script, settings patch/unpatch | 4.1, 12 | Phase 1 | S |
| 3. Registry | Queue drain, backfill scan, search/filter engine | 4.2, 4.3, 9 | Phase 1 | M |
| 4. Shell integration | Init wrapper, completions, resume line builder | 4.10, 4.9, 9 | Phase 3 | S |
| 5. CLI — Core commands | Doctor, prune, export, grep, auto-name, theme, search, confirm | 4.8, 4.11–4.17 | Phase 3 | M |
| 6. CLI — CRUD & scripting | List, resume, rename, tag, favorite, delete, archive, stats, config | 4.18–4.27 | Phase 3 | M |
| 7. TUI — Core | App shell, session list, search bar, preview pane, key bindings | 4.4, 8 | Phase 3 | L |
| 8. TUI — Views | Overview (stats/sparkline/cost), Projects, Help | 4.5–4.7, 9 | Phase 7 | M |
| 9. TUI — Advanced | Rename, tag input, bulk select, archive, theme switching | 4.4, 4.14 | Phase 7 | M |
| 10. Install & polish | Postinstall script, doctor checks, uninstall | 4.16, 4.17, 13 | All | S |

---

## 17. Appendix

### Glossary

| Term | Definition |
|------|------------|
| **Session** | A single Claude Code chat conversation, identified by UUID |
| **Registry** | The local SQLite database indexing all known sessions |
| **Queue** | The append-only JSONL file where hook events are buffered before draining |
| **Drain** | The process of reading the queue and upserting events into the registry |
| **Backfill** | Discovering sessions from Claude Code's transcript files on disk (as opposed to capturing them live via the hook) |
| **Resume line** | The `cd <cwd> && exec claude --resume <id>` stdout protocol line |
| **Custom name** | A user-assigned short label for a session (enables tab completion and instant resume) |
| **Pattern A** | A session stored as a top-level `<uuid>.jsonl` file in a Claude projects subdirectory |
| **Pattern B** | A session stored as a `<uuid>/` directory with no matching top-level JSONL (still resumable, but without transcript metadata) |
| **Dash encoding** | Claude Code's convention of encoding filesystem paths by replacing `/` with `-` in the projects directory name |
| **Frecency** | A ranking heuristic that combines frequency (how often) and recency (how recently) into a single score. Used as the default session sort mode |
| **Sort mode** | The active ordering strategy for session lists: frecency (default), recency, or frequency |
| **Session resolution** | The standard lookup sequence used by all commands: try `custom_name` match first, then `session_id` (see section 9) |
| **Global flag** | A CLI flag (`--here`, `--no-color`, `--help`, `--version`) available on all commands |
| **Archive** | Reversible soft-delete: hides a session from views without removing data from the registry |

---

## Specification Completeness

- **TUI component rendering details** are described at the layout/behavior level but not at the pixel level. The exact rendering depends on terminal dimensions and the theme system.
- **Hook script internals** are specified at the data-capture level. The exact `python3`/`sed` fallback chain for JSON escaping is implementation detail.
- **CLI CRUD commands** (4.18–4.27) are specified at the behavior level; error handling follows the patterns in section 10.
- **Global flags** (`--here`, `--no-color`) are specified; any future commands should follow the same applicability patterns.
- **Tech stack, libraries, programming language, filenames, and directory structure** are intentionally omitted per user request.
