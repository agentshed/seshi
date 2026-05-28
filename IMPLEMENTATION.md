# Seshi Implementation Plan

## 1. Project Setup

### Runtime & Tooling

- **Python** 3.12+
- **uv** for project management, dependency resolution, and virtual environments
- Install: `uv tool install .` from the project root
- Run: `uvx seshi` or `seshi` (after tool install)
- Dev: `uv run python -m pytest` for tests

### pyproject.toml

```toml
[project]
name = "seshi"
version = "0.1.0"
description = "Global session manager and resumer for Claude Code"
requires-python = ">=3.12"
license = "MIT"
dependencies = [
    "click>=8.1",
    "textual>=1.0",
    "rich>=13.0",
]

[project.scripts]
seshi = "seshi.cli:main"

[tool.uv]
dev-dependencies = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/seshi"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

---

## 2. Dependencies

### Runtime (3 packages)

| Package | Version | Role | Why this one |
|---------|---------|------|-------------|
| **click** | >=8.1 | CLI framework | Decorator-based subcommands, global flags, shell completion generation (bash/zsh/fish). More control over output streams than typer. Battle-tested in thousands of projects. |
| **textual** | >=1.0 | TUI framework | Multi-view reactive apps, CSS-like theming, keyboard navigation, widget composition. Python equivalent of Ink (used in the original TypeScript version). |
| **rich** | >=13.0 | Terminal output | Truecolor ANSI, `Console(file=)` for /dev/tty rendering, style system for themes. Already a dependency of textual. |

### Stdlib (no extra deps)

| Module | Role |
|--------|------|
| `sqlite3` | Database — WAL mode, foreign keys, parameterized queries |
| `json` | JSONL parsing (queue events, transcripts) |
| `subprocess` | Shell out to `claude -p` for auto-name |
| `shutil.which` | Check `claude` on PATH (doctor command) |
| `importlib.resources` | Locate bundled `hook.sh` at runtime |
| `math` | `log1p()` for sparkline log-scaling in overview |
| `os` / `platform` / `socket` | System info capture (hostname, platform detection) |
| `pathlib` | Path manipulation throughout |

### Dev (2 packages)

| Package | Role |
|---------|------|
| `pytest` >=8.0 | Test framework |
| `pytest-cov` >=5.0 | Coverage reporting |

---

## 3. Directory Structure

```
seshi/
├── pyproject.toml
├── SPEC.md
├── implementation.md
├── src/
│   └── seshi/
│       ├── __init__.py              # __version__ = "0.1.0"
│       ├── __main__.py              # python -m seshi support
│       ├── cli.py                   # Click group, global flags, auto-drain
│       ├── db.py                    # open_db(), init_schema(), context manager
│       ├── models.py                # Session, Tag, ProjectFavorite dataclasses
│       ├── paths.py                 # Constants, unsanitize_path(), resolve_best_cwd()
│       ├── drain.py                 # drain_queue() — JSONL queue → DB upserts
│       ├── search.py                # fuzzy_match(), session_resolve(), rank_sessions()
│       ├── transcript_index.py      # FTS5 full-text indexing of session transcripts
│       ├── prompt_index.py          # Extract and index individual user prompts
│       ├── resume.py                # build_resume_line(), shell_quote()
│       ├── scan.py                  # scan_projects(), fix_prompts(), auto_scan() — backfill + startup scan
│       ├── transcript.py            # parse_transcript(), extract_messages(), extract_user_prompts()
│       ├── hook.py                  # install_hook(), patch_settings(), unpatch_settings()
│       ├── themes.py                # 5 palettes, get_theme(), THEMES dict
│       ├── cost.py                  # Model rate table, estimate_cost(), format_usd()
│       ├── time_utils.py            # relative_time(), time_bucket()
│       ├── lang_detect.py           # detect_language() from manifest files
│       ├── shell_init.py            # Shell wrapper + completion generators
│       ├── hook/
│       │   └── hook.sh              # Bash hook script (bundled as package data)
│       ├── commands/
│       │   ├── __init__.py
│       │   ├── last_cmd.py          # seshi last
│       │   ├── resume_cmd.py        # seshi resume + fuzzy dispatch
│       │   ├── list_cmd.py          # seshi list
│       │   ├── rename_cmd.py        # seshi rename
│       │   ├── tag_cmd.py           # seshi tag
│       │   ├── favorite_cmd.py      # seshi favorite
│       │   ├── delete_cmd.py        # seshi delete
│       │   ├── archive_cmd.py       # seshi archive
│       │   ├── stats_cmd.py         # seshi stats
│       │   ├── config_cmd.py        # seshi config
│       │   ├── project_cmd.py       # seshi project favorite/rename
│       │   ├── scan_cmd.py          # seshi scan
│       │   ├── doctor_cmd.py        # seshi doctor
│       │   ├── prune_cmd.py         # seshi prune
│       │   ├── export_cmd.py        # seshi export
│       │   ├── grep_cmd.py          # seshi grep
│       │   ├── auto_name_cmd.py     # seshi auto-name
│       │   ├── theme_cmd.py         # seshi theme
│       │   ├── init_cmd.py          # seshi init
│       │   └── uninstall_cmd.py     # seshi uninstall
│       └── tui/
│           ├── __init__.py
│           ├── app.py               # SeshiApp (Textual App), /dev/tty driver
│           ├── sessions.py          # Sessions view — list, search, actions
│           ├── overview.py          # Overview view — stats, sparkline, cost
│           ├── projects.py          # Projects view — grouped by cwd
│           ├── help_view.py         # Help view — keymap reference
│           ├── search_bar.py        # Search input with #tag parsing
│           ├── preview.py           # Preview pane — transcript messages
│           ├── header.py            # Logo, counts, version
│           ├── footer.py            # Context-sensitive key hints
│           ├── confirm.py           # Raw-terminal confirmation prompt
│           └── styles.py            # Theme → Textual CSS generation
└── tests/
    ├── conftest.py                  # Fixtures: tmp_db, mock_sessions, mock_queue
    ├── test_db.py
    ├── test_drain.py
    ├── test_search.py
    ├── test_resume.py
    ├── test_paths.py
    ├── test_scan.py
    ├── test_transcript.py
    ├── test_export.py
    ├── test_grep.py
    ├── test_cost.py
    ├── test_themes.py
    ├── test_time_utils.py
    ├── test_shell_init.py
    ├── test_hook.py
    ├── test_lang_detect.py
    ├── test_commands.py
    └── fixtures/
        └── sample.jsonl
```

---

## 4. Critical Architecture: The /dev/tty Protocol

The shell wrapper `seshi()` captures stdout via `$(command seshi "$@")` and evals resume lines. This means:

- **TUI must render to `/dev/tty`**, not stdout
- **Resume lines** (`cd ... && exec ...`) must go to real stdout
- **All other output** (doctor, stats, help) goes to stdout but doesn't match the resume pattern

### Solution

```python
import sys, os

def launch_tui(ctx_obj):
    if not os.isatty(sys.stdout.fileno()):
        # Wrapper mode: stdout is captured by $()
        # Redirect Textual to /dev/tty
        tty = open("/dev/tty", "w+")
        saved_stdout = sys.stdout
        sys.stdout = tty
        sys.stdin = open("/dev/tty", "r")

    app = SeshiApp(ctx_obj)
    app.run()

    if app.chosen_session:
        # Resume line goes to REAL stdout (not /dev/tty)
        line = build_resume_line(app.chosen_session)
        sys.__stdout__.write(line)
        sys.__stdout__.flush()
```

The confirmation prompt (`tui/confirm.py`) for `seshi resume` uses raw terminal I/O directly on `/dev/tty` — it does NOT use Textual.

---

## 5. Implementation Phases

### Phase 1: Foundation (Week 1)

**Files**: `paths.py`, `db.py`, `models.py`, `themes.py`, `cost.py`, `time_utils.py`, `lang_detect.py`

**`paths.py`** — Constants and path resolution:
```python
SESHI_DIR = Path.home() / .seshi"
DB_PATH = SESHI_DIR / "db.sqlite"
QUEUE_PATH = SESHI_DIR / "queue.jsonl"
HOOK_PATH = SESHI_DIR / "hook.sh"
CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"
CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"

def unsanitize_path(name: str) -> list[str]:
    """Power-set enumeration for dash ambiguity resolution.
    Leading dash = /. For ≤6 ambiguous dashes: enumerate 2^N combos.
    For >6: fallback to all-slashes + single-dash-preserved."""

def resolve_best_cwd(name: str) -> str:
    """Return first candidate that exists on disk, else first candidate."""
```

**`db.py`** — Database context manager:
```python
@contextmanager
def open_db(readonly=False):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()

def init_schema(conn):
    """CREATE TABLE IF NOT EXISTS for sessions, tags, settings, project_favorites,
    prompts, prompt_index_meta, transcript_fts (FTS5 virtual table), and
    transcript_index_meta. Seed default settings. Create indexes."""
```

**`models.py`** — Dataclasses with `from_row()`:
```python
@dataclass
class Session:
    session_id: str
    cwd: str
    launch_argv_json: str
    # ... all fields from spec section 6
    @classmethod
    def from_row(cls, row) -> "Session": ...

@dataclass
class Prompt:
    session_id: str
    prompt_index: int
    text: str
    timestamp_epoch: int | None
    @classmethod
    def from_row(cls, row) -> "Prompt": ...
```

**`prompt_index.py`** — Extracts individual user prompts from transcripts:
```python
def index_session_prompts(conn, session_id) -> bool: ...
def index_pending_prompts(conn) -> int: ...
```

**`themes.py`** — 5 palettes (coral, catppuccin, gruvbox, nord, mono) with 12 color fields each.

**`cost.py`** — Model rate table, `estimate_cost(token_count, model)`, `format_usd(amount)`.

**`time_utils.py`** — `relative_time(ts)` → "17m ago", `time_bucket(ts)` → "today"/"this week"/etc.

**`lang_detect.py`** — Check manifest files in cwd, return 2-3 char tag. Memoized per cwd.

### Phase 2: Hook (Week 1)

**Files**: `hook/hook.sh`, `hook.py`

**`hook/hook.sh`** — Pure bash. Reads JSON from stdin, captures parent argv via `/proc/$PPID/cmdline` (Linux) or `ps -o args=` (macOS), captures git branch/sha, captures env vars. Appends JSONL to `~/.seshi/queue.jsonl`. Every operation wrapped in `|| exit 0`.

**`hook.py`**:
```python
def install_hook():
    """Copy bundled hook.sh to ~/.seshi/hook.sh, chmod 755."""
    src = importlib.resources.files("seshi").joinpath("hook/hook.sh")
    ...

def patch_settings():
    """Merge hook entries into ~/.claude/settings.json. Idempotent."""

def unpatch_settings():
    """Remove hook entries. Preserve other hooks."""
```

### Phase 3: Registry (Week 2)

**Files**: `drain.py`, `scan.py`, `search.py`, `transcript.py`

**`drain.py`** — `drain_queue(conn)`:
1. Read `~/.seshi/queue.jsonl` line by line
2. Parse JSON, skip malformed lines
3. Within a single transaction: INSERT OR IGNORE for start events, UPDATE for stop events
4. Truncate queue file

**`transcript.py`**:
```python
def parse_transcript(path) -> TranscriptSummary:
    """Read JSONL, extract first_prompt, message_count, token_count, timestamps."""

def extract_messages(path, limit=None) -> list[Message]:
    """For preview pane and export. Returns (role, text) tuples."""

def find_transcript_path(session_id) -> Path | None:
    """Search ~/.claude/projects/ for the session's JSONL file."""
```

**`scan.py`**:
- `scan_projects(conn, verbose=False)` — Walk `~/.claude/projects/`, Pattern A: `<uuid>.jsonl` files (not `skill-injections.jsonl`), Pattern B: `<uuid>/` directories without matching JSONL. `INSERT OR IGNORE` with `is_backfilled=1`.
- `fix_prompts(conn, verbose=False)` — Re-derive `first_prompt` from transcripts for all sessions. Used to correct stale prompts (e.g. isMeta system messages captured as first_prompt).
- `auto_scan(conn, interval=120)` — Rate-limited wrapper called on every CLI invocation. Runs `scan_projects()`, then `fix_prompts()` once as a one-time migration (tracked by `prompts_fixed` setting).

**`search.py`**:
```python
def fuzzy_match(query: str, string: str) -> int:
    """Sequential char matching with proximity scoring. 0 = no match."""

def session_resolve(conn, identifier: str) -> Session:
    """Standard lookup: custom_name (case-insensitive) → session_id → NOT_FOUND."""

def rank_sessions(conn, query: str, filter_cwd=None) -> list[Session]:
    """Score = max(custom_name×4, first_prompt×2, cwd×1, transcript×1). For fuzzy resume."""

def frecency_score(session, now) -> float:
    """frecency_rank × step_function_multiplier(age_hours). Multiplicative blend."""
```

### Phase 4: Shell Integration (Week 2)

**Files**: `resume.py`, `shell_init.py`

**`resume.py`**:
```python
def build_resume_line(session: Session) -> str:
    """cd <cwd> && exec claude --resume <id>\n
    Strips prior --resume flags, shell-quotes all args."""

def shell_quote(s: str) -> str:
    """Safe chars pass through; others get single-quoted with ' escaped."""
```

**`shell_init.py`**:
```python
def generate_wrapper(shell: str) -> str:
    """Returns the seshi() shell function for bash/zsh/fish.
    The function captures stdout via $(), pattern-matches resume lines, evals them."""

def generate_completions(shell: str) -> str:
    """Returns completion registration for bash/zsh/fish."""

def detect_shell() -> str:
    """Auto-detect from $SHELL. Fallback to bash."""
```

### Phase 5: CLI — Core Commands (Week 3)

**Files**: `cli.py`, `commands/{doctor,scan,init,theme,prune,export,grep,auto_name,last,resume}_cmd.py`

**`cli.py`** — Click group with auto-drain:
```python
class SeshiGroup(click.Group):
    def resolve_command(self, ctx, args):
        """Route unknown subcommands to TUI with pre-populated search."""
        cmd_name = args[0] if args else None
        if cmd_name and cmd_name not in self.commands and not cmd_name.startswith("-"):
            return "_tui_search", self.commands["_tui_search"], args
        return super().resolve_command(ctx, args)

@click.group(cls=SeshiGroup, invoke_without_command=True)
@click.option("--no-color", is_flag=True)
@click.option("--here", is_flag=True)
@click.version_option()
@click.pass_context
def main(ctx, no_color, here):
    ctx.ensure_object(dict)
    ctx.obj["no_color"] = no_color
    ctx.obj["here_cwd"] = os.getcwd() if here else None
    # Startup tasks before any command
    with open_db() as conn:
        drain_queue(conn)
        age_frecency_ranks(conn)  # rate-limited: every 300s
        auto_scan(conn)           # rate-limited: every 120s
    if ctx.invoked_subcommand is None:
        launch_tui(ctx.obj)
```

Each command file registers to the group:
```python
# commands/doctor_cmd.py
@main.command("doctor")
@click.option("--fix", is_flag=True)
def doctor(fix):
    """Health check for Seshi installation."""
    checks = [
        ("Registry directory", SESHI_DIR.exists(), lambda: SESHI_DIR.mkdir(parents=True)),
        ("Hook installed", HOOK_PATH.exists() and os.access(HOOK_PATH, os.X_OK), install_hook),
        ("Registry DB", DB_PATH.exists(), lambda: init_schema(...)),
        ("Settings patched", ..., patch_settings),
        ("Claude on PATH", shutil.which("claude"), None),
    ]
    ...
```

### Phase 6: CLI — CRUD & Scripting (Week 3)

**Files**: `commands/{list,rename,tag,favorite,delete,archive,stats,config,project}_cmd.py`

All CRUD commands follow the same pattern:
1. `session_resolve(conn, identifier)` to find the session
2. Mutate the database
3. Print confirmation to stderr (or stdout for list/stats)

**`list_cmd.py`** — Three output formats:
```python
@main.command("list")
@click.option("--json", "fmt", flag_value="json")
@click.option("--tsv", "fmt", flag_value="tsv")
@click.option("--limit", type=int)
@click.option("--tag", multiple=True)
@click.option("--sort", type=click.Choice(["frecency", "recency", "frequency"]))
@click.option("--archived", is_flag=True)
@click.pass_context
def list_cmd(ctx, fmt, limit, tag, sort, archived):
    ...
```

**`stats_cmd.py`** — Aggregation queries → formatted output or JSON.

**`config_cmd.py`** — Key validation against known settings, value validation per key.

### Phase 7: TUI — Core (Weeks 4–5)

**Files**: `tui/app.py`, `tui/sessions.py`, `tui/search_bar.py`, `tui/preview.py`, `tui/header.py`, `tui/footer.py`, `tui/styles.py`, `tui/confirm.py`

**`tui/app.py`** — Textual App subclass:
```python
class SeshiApp(App):
    BINDINGS = [
        ("tab", "next_view"),
        ("shift+tab", "prev_view"),
        ("1", "view_sessions"),
        ("2", "view_overview"),
        ("3", "view_projects"),
        ("question_mark", "view_help"),
    ]

    chosen_session: Session | None = None

    def compose(self):
        yield Header()
        yield TabBar()
        yield SearchBar()
        yield SessionsList()
        yield Preview()
        yield Footer()

    def resume(self, session):
        self.chosen_session = session
        self.exit()
```

**`tui/sessions.py`** — The main view. Key bindings:
- `j`/`k`/`↑`/`↓`: navigate
- `Enter`: resume selected session
- `r`: inline rename (text input overlay)
- `t`: tag toggle prompt
- `f`: toggle favorite
- `u`: toggle archive
- `d`: delete (with confirmation)
- `s`: cycle sort mode
- `H`: toggle hide missing dirs
- `Space`: toggle bulk selection
- `Ctrl-a`: select all visible
- `g`/`G`: top/bottom
- `Ctrl-u`/`Ctrl-d`: page up/down
- `Esc`: clear selection or quit

**`tui/search_bar.py`** — Text input that:
- Parses `#tag` tokens from the query
- Triggers re-filter on every keystroke
- Shows `{shown} / {total}` count

**`tui/preview.py`** — Lazy-loads transcript on selection change. Shows last N messages with role labels.

**`tui/styles.py`** — Converts a `Palette` to Textual CSS:
```python
def theme_css(palette: Palette) -> str:
    return f"""
    Screen {{ background: $surface; }}
    .session-row {{ color: {palette.fg}; }}
    .session-row.--highlight {{ background: {palette.bg_selected}; }}
    .favorite {{ color: {palette.accent}; }}
    ...
    """
```

**`tui/confirm.py`** — Standalone raw-terminal confirmation for `seshi resume` (NOT Textual):
```python
def confirm_resume(session, query) -> str:
    """Render to /dev/tty. Read single keypress. Return 'yes'/'no'/'tui'."""
    tty = open("/dev/tty", "r+")
    # Show: session name, query, cwd
    # Keys: Enter=resume, t=open TUI, anything else=cancel
```

### Phase 8: TUI — Views (Week 5)

**Files**: `tui/overview.py`, `tui/projects.py`, `tui/help_view.py`

**Overview** — Sparkline (Unicode blocks `▁▂▃▄▅▆▇█`), totals, this-week summary, per-model cost breakdown.

**Projects** — Rows grouped by cwd, horizontal bar chart proportional to session count, language tags.

**Help** — Static keymap reference grouped by category.

### Phase 9: TUI — Advanced (Week 6)

1. Inline rename overlay (text input on selected row)
2. Tag toggle prompt (validates `[\w\-]`)
3. Bulk selection with `[x]` marks, bulk delete/tag
4. Sort mode cycling with persisted setting
5. Archive toggle (`u` key)
6. Theme hot-switching
7. View tab navigation (`Tab`/`Shift-Tab`/`1-3`/`?`)

### Phase 10: Install & Polish (Week 6)

1. First-run detection: `seshi doctor --fix` auto-creates everything
2. `seshi uninstall --purge` removes `~/.seshi/` entirely
3. Postinstall: create dirs → copy hook → patch settings → init DB → scan
4. Actionable error messages (e.g. "Run `seshi scan` to discover existing sessions")
5. `__main__.py` for `python -m seshi` support

---

## 6. Database Patterns

### Context Manager

```python
@contextmanager
def open_db(readonly=False):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()
```

### Transaction Pattern (drain)

```python
def drain_queue(conn):
    if not QUEUE_PATH.exists():
        return
    lines = QUEUE_PATH.read_text().splitlines()
    with conn:  # auto-commit transaction
        for line in lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event") == "start":
                conn.execute("INSERT OR IGNORE INTO sessions (...) VALUES (...)", ...)
            elif event.get("event") == "stop":
                conn.execute("UPDATE sessions SET ... WHERE session_id = ?", ...)
    QUEUE_PATH.write_text("")
```

### Query Pattern (list)

```python
def list_sessions(conn, filter_cwd=None, tags=None, include_archived=False, sort_mode="frecency"):
    sql = "SELECT * FROM sessions WHERE is_archived = 0"
    params = []
    if not include_archived:
        pass  # already filtered
    else:
        sql = "SELECT * FROM sessions WHERE 1=1"
    if filter_cwd:
        sql += " AND cwd = ?"
        params.append(filter_cwd)
    # Tag AND-filter via subquery
    if tags:
        for tag in tags:
            sql += " AND session_id IN (SELECT session_id FROM tags WHERE tag = ?)"
            params.append(tag)
    sql += " ORDER BY is_favorite DESC, last_activity_at DESC"
    rows = conn.execute(sql, params).fetchall()
    return [Session.from_row(r) for r in rows]
```

---

## 7. Testing Strategy

### Fixtures (`conftest.py`)

```python
@pytest.fixture
def tmp_db(tmp_path):
    """Temporary SQLite database with schema initialized."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    init_schema(conn)
    yield conn
    conn.close()

@pytest.fixture
def mock_sessions(tmp_db):
    """Pre-populate with representative sessions."""
    # 5-10 sessions: favorites, archived, tagged, backfilled, named/unnamed
    ...

@pytest.fixture
def mock_queue(tmp_path):
    """Temporary queue file with sample start/stop events."""
    ...

@pytest.fixture
def mock_projects(tmp_path):
    """Directory structure mimicking ~/.claude/projects/ with sample transcripts."""
    ...
```

### Test Coverage

| Module | Test cases | Key scenarios |
|--------|-----------|---------------|
| `db.py` | 6 | Schema creation, WAL mode, foreign keys, default settings, readonly, context cleanup |
| `drain.py` | 9 | Start insert, stop update, idempotent start, malformed skip, missing queue, stop for unknown session, first_prompt COALESCE |
| `search.py` | 10 | fuzzy_match scoring, empty query, no match=0, exact match highest, tag AND filter, session_resolve by name, by id, not found, frecency ordering |
| `paths.py` | 7 | Basic unsanitize, power-set enumeration, dotfile `--` handling, resolve prefers existing, >6 dashes fallback |
| `resume.py` | 8 | Format correctness, shell_quote safe/special chars, strip --resume, ensure argv[0]="claude" |
| `scan.py` | 6 | Pattern A, Pattern B, idempotent, skip skill-injections, no double-insert |
| `transcript.py` | 6 | Parse text content, parse array content blocks, token counting, timestamp extraction, find_transcript_path |
| `export.py` | 8 | Raw passthrough, Markdown format, JSON format, tool-use blocks, empty transcript |
| `grep.py` | 6 | Case-insensitive match, --limit, --role filter, no matches, skip excluded dirs |
| `cost.py` | 8 | Rate lookup per model, fallback rate, cost estimation, format_usd thresholds |
| `themes.py` | 5 | All palettes have 12 keys, load from DB, fallback to coral, valid hex colors |
| `time_utils.py` | 6 | relative_time thresholds, time_bucket categorization |
| `shell_init.py` | 8 | Bash wrapper contains eval, zsh has compdef, fish has complete, auto-detect from $SHELL |
| `hook.py` | 5 | Install creates executable file, patch adds entries, patch is idempotent, unpatch removes entries |
| `lang_detect.py` | 5 | Python/Go/Rust/JS/TS detection from manifests |
| `commands` | 20+ | CLI integration tests via Click's `CliRunner` for list/rename/tag/favorite/delete/archive/stats/config/doctor |

### CLI Integration Tests

```python
from click.testing import CliRunner
from seshi.cli import main

def test_list_json(mock_sessions):
    runner = CliRunner()
    result = runner.invoke(main, ["list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) > 0
```

### TUI Tests

Textual provides `App.run_test()` for headless testing:
```python
async def test_session_list_renders():
    app = SeshiApp(db_path=test_db_path)
    async with app.run_test() as pilot:
        assert app.query_one(SessionsList).row_count > 0
        await pilot.press("j")  # move down
        await pilot.press("enter")  # select
```

---

## 8. Risk Areas

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Textual /dev/tty compatibility | TUI won't render in wrapper mode | Build proof-of-concept first. Fallback: raw Rich Console with `file=open("/dev/tty", "w")` + custom event loop |
| Path unsanitization correctness | Sessions mapped to wrong directories | Port test cases exactly from spec. Test with real `~/.claude/projects/` directory names |
| Hook reliability | Hook failure blocks Claude Code | Copy battle-tested bash script. Every operation wrapped in `|| exit 0`. Never write to stdout/stderr |
| Large transcript performance | Slow grep/scan on hundreds of JSONL files | Line-by-line buffered reading. Limit scan to top-level files. Short-circuit grep on match limit |
| Click + unknown subcommands | `seshi <query>` misrouted | Custom `SeshiGroup.resolve_command()` that routes to TUI with pre-populated search for unrecognized commands |

---

## 9. Spec Section Coverage

Every spec section (4.1–4.27) maps to implementation files:

| Spec | Feature | Implementation |
|------|---------|---------------|
| 4.1 | Session Capture | `hook/hook.sh` |
| 4.2 | Session Registry | `drain.py`, `db.py` |
| 4.3 | Backfill Scanning | `scan.py`, `transcript.py` |
| 4.4 | TUI Sessions View | `tui/sessions.py`, `tui/search_bar.py` |
| 4.5 | TUI Overview View | `tui/overview.py` |
| 4.6 | TUI Projects View | `tui/projects.py` |
| 4.7 | TUI Help View | `tui/help_view.py` |
| 4.8 | Resume / Fuzzy Resume | `commands/resume_cmd.py`, `search.py`, `tui/confirm.py` |
| 4.9 | Tab Completion | `shell_init.py` |
| 4.10 | Shell Wrapper / Init | `shell_init.py`, `commands/init_cmd.py` |
| 4.11 | Transcript Export | `commands/export_cmd.py`, `transcript.py` |
| 4.12 | Transcript Grep | `commands/grep_cmd.py` |
| 4.13 | Auto-Name | `commands/auto_name_cmd.py` |
| 4.14 | Theme System | `themes.py`, `commands/theme_cmd.py`, `tui/styles.py` |
| 4.15 | Prune | `commands/prune_cmd.py` |
| 4.16 | Doctor | `commands/doctor_cmd.py` |
| 4.17 | Uninstall | `commands/uninstall_cmd.py` |
| 4.18 | List | `commands/list_cmd.py` |
| 4.19 | Rename | `commands/rename_cmd.py` |
| 4.20 | Tag | `commands/tag_cmd.py` |
| 4.21 | Favorite | `commands/favorite_cmd.py` |
| 4.22 | Delete | `commands/delete_cmd.py` |
| 4.23 | Stats | `commands/stats_cmd.py` |
| 4.24 | Config | `commands/config_cmd.py` |
| 4.25 | Archive | `commands/archive_cmd.py` |
| 4.26 | Project Favorite | `commands/project_cmd.py` |
| 4.27 | Project View Actions | `tui/projects.py` |

---

## 10. Timeline

| Phase | What | Effort | Week |
|-------|------|--------|------|
| 1 | Foundation (db, models, paths, themes, cost, time, lang) | S | 1 |
| 2 | Hook (hook.sh, patch/unpatch settings) | S | 1 |
| 3 | Registry (drain, scan, search, transcript) | M | 2 |
| 4 | Shell integration (resume builder, shell wrapper) | S | 2 |
| 5 | CLI core commands (doctor, scan, init, theme, prune, export, grep, auto-name, last, resume) | M | 3 |
| 6 | CLI CRUD & scripting (list, rename, tag, favorite, delete, archive, stats, config, project) | M | 3 |
| 7 | TUI core (app shell, sessions list, search, preview, /dev/tty) | L | 4–5 |
| 8 | TUI views (overview, projects, help) | M | 5 |
| 9 | TUI advanced (inline edit, bulk select, sort cycling, themes) | M | 6 |
| 10 | Install & polish (postinstall, doctor --fix, uninstall, error messages) | S | 6 |

After Phase 5, the CLI is fully functional without the TUI. After Phase 7, the complete tool is operational.
