# Seshi TUI Exploratory Testing Prompt

## Purpose

You are performing exhaustive exploratory testing of the Seshi TUI (Terminal User Interface), a Textual-based session manager for Claude Code. Your goal is to verify every interactive feature, uncover bugs in edge cases, and evaluate the user experience against TUI best practices. You will use **tmux** to control terminal size, send keystrokes programmatically, and capture screenshots for evidence.

## Setup

### Environment

```sh
# 1. Ensure seshi is installed and runnable
uv run seshi --version

# 2. Create a tmux session dedicated to testing
tmux new-session -d -s seshi-test -x 120 -y 40

# 3. Seed test data (run inside tmux or beforehand)
# Ensure the SQLite DB at ~/.seshi/seshi.db has a variety of sessions:
#   - Sessions with custom_name set and unset
#   - Sessions with first_prompt set and unset (will show "(untitled)")
#   - Sessions with is_favorite = 1 and 0
#   - Sessions with is_archived = 1 (should be hidden by default)
#   - Sessions with tags
#   - Sessions whose cwd no longer exists on disk
#   - Sessions across multiple cwds (projects)
#   - Sessions with varying token_count, message_count
#   - Sessions with very long custom_name (>38 chars — tests truncation)
#   - Sessions with very long cwd paths (>30 chars — tests truncation with ellipsis)
#   - Sessions with Unicode characters in custom_name and first_prompt
#   - Sessions spanning different time_bucket ranges (today, yesterday, this week, this month, older)
#   - At least 50+ sessions to test scrolling behavior

# 4. Launch the TUI inside tmux
tmux send-keys -t seshi-test 'uv run seshi' Enter
```

### tmux Cheat Sheet for Testers

```sh
# Send a single key
tmux send-keys -t seshi-test 'j'            # press j
tmux send-keys -t seshi-test Enter           # press Enter
tmux send-keys -t seshi-test Escape          # press Escape
tmux send-keys -t seshi-test Tab             # press Tab
tmux send-keys -t seshi-test BTab            # press Shift+Tab (BTab in tmux)
tmux send-keys -t seshi-test Space           # press Space
tmux send-keys -t seshi-test C-u             # press Ctrl+u
tmux send-keys -t seshi-test C-d             # press Ctrl+d
tmux send-keys -t seshi-test '/'             # press /
tmux send-keys -t seshi-test '?'             # press ?
tmux send-keys -t seshi-test BSpace          # press Backspace

# Send a string (each char as a keystroke)
tmux send-keys -t seshi-test 'hello'

# Capture current screen content
tmux capture-pane -t seshi-test -p           # print to stdout
tmux capture-pane -t seshi-test -p > /tmp/seshi-screen.txt  # save to file

# Resize the pane (simulates terminal resize)
tmux resize-window -t seshi-test -x 80 -y 24
tmux resize-window -t seshi-test -x 40 -y 12
tmux resize-window -t seshi-test -x 200 -y 60

# Kill and restart
tmux send-keys -t seshi-test C-c
tmux send-keys -t seshi-test 'uv run seshi' Enter
```

---

## Testing Matrix

### SECTION 1: Launch and Initial Render

#### 1.1 Cold Start (Positive)
- Launch `uv run seshi` in a standard 120x40 terminal
- **Verify:** Header renders with ASCII art logo, accent color, version number
- **Verify:** Tab bar shows `1 sessions  2 overview  3 projects  ? help`
- **Verify:** Search bar shows `>` prompt with cursor, sort mode label (default: "frecency"), and count `N / N`
- **Verify:** Session list populates with sessions sorted by frecency (favorites first, then by score)
- **Verify:** Preview pane shows transcript of the cursor-highlighted session
- **Verify:** Footer shows contextual keys: `Enter resume  r rename  f favorite  t tag  u archive  d delete  s sort  Space select  Tab view`
- **Verify:** Cursor (reverse-video highlight) is on the first session
- **Verify:** Project path headers appear (e.g., "── ★ favorites ──", "── ~/seshi (py) 1h ago ──")

#### 1.2 Cold Start with --here Flag
- `uv run seshi --here` from a directory that has sessions
- **Verify:** Only sessions matching the current cwd are shown
- **Verify:** Header count reflects filtered total
- Press Escape to clear the cwd filter
- **Verify:** All sessions appear again

#### 1.3 Cold Start with --here from Dir with No Sessions
- `uv run seshi --here` from a directory that has zero sessions
- **Verify:** "no sessions found" message displays gracefully
- **Verify:** No crash, no blank screen

#### 1.4 Empty Database
- Test with a database containing zero sessions
- **Verify:** "no sessions found" renders
- **Verify:** All view keys (1, 2, 3, ?) still work
- **Verify:** Overview shows zeros, no crash on sparkline with zero data
- **Verify:** Projects shows "no projects found"
- **Verify:** Escape quits cleanly

#### 1.5 Single Session
- Database with exactly one session
- **Verify:** Cursor is on it, preview shows its transcript
- **Verify:** All operations (rename, tag, favorite, delete) work on it
- **Verify:** After deleting the only session, list shows "no sessions found"

---

### SECTION 2: Navigation (Sessions View)

#### 2.1 Cursor Movement (Positive)
- Press `j` or `Down` — cursor moves down one row
- Press `k` or `Up` — cursor moves up one row
- Press `g` — cursor jumps to the first session
- Press `G` (Shift+G) — cursor jumps to the last session
- Press `Ctrl+u` — cursor jumps up 10 rows
- Press `Ctrl+d` — cursor jumps down 10 rows
- **Verify:** Preview pane updates on every cursor move to show the newly highlighted session

#### 2.2 Cursor Bounds (Edge Cases)
- Press `k`/`Up` when cursor is on the first session — cursor stays at 0, no crash
- Press `j`/`Down` when cursor is on the last session — cursor stays at last, no crash
- Press `g` when already at top — no change, no crash
- Press `G` when already at bottom — no change, no crash
- Press `Ctrl+u` when cursor is at position 3 — cursor goes to 0 (not negative)
- Press `Ctrl+d` when cursor is 5 from the end — cursor goes to last (not beyond)

#### 2.3 Scrolling (Large List)
- With 50+ sessions, navigate past the visible viewport
- **Verify:** Scrolling is smooth, cursor stays visible
- **Verify:** Time bucket headers scroll correctly and don't create visual artifacts
- **Verify:** The viewport centers around the cursor (uses `visible_height // 2` centering logic)
- Jump `g` then `G` rapidly — no flicker or rendering glitch
- Use `Ctrl+d` repeatedly to page through — no gaps or duplicate rows

#### 2.4 Vim-style vs Arrow Key Consistency
- Perform the same navigation sequence with vim keys (j/k/g/G) and arrow keys (Up/Down)
- **Verify:** Behavior is identical
- **Verify:** Both key styles update the preview pane

---

### SECTION 3: Search and Filtering

#### 3.1 Activating Search (Positive)
- Press `/` — search bar activates (blinking cursor appears, accent-colored)
- **Verify:** Focus moves to search bar
- **Verify:** Cursor blinks at ~0.5s interval
- **Verify:** Footer does not change (still shows session keys? or should it show search hints?)

#### 3.2 Typing a Search Query
- Type a query that matches session names — e.g., type part of a known custom_name
- **Verify:** Session list filters in real-time as each character is typed
- **Verify:** Count updates in search bar (e.g., "3 / 50")
- **Verify:** Fuzzy matching works: partial strings match, order doesn't matter
- **Verify:** Matching prioritizes name (4x), then prompt (2x), then cwd (1x)
- **Verify:** Favorites still sort to the top within results

#### 3.3 Implicit Search Activation
- Without pressing `/` first, just start typing a printable character from the sessions list
- **Verify:** Search bar activates automatically and the typed character appears as the query
- **Verify:** Filtering begins immediately

#### 3.4 Navigating During Search
- While search bar is active and has a query:
  - Press `Up` — cursor moves up in filtered results
  - Press `Down` — cursor moves down in filtered results
  - Press `Enter` — resumes the highlighted session (exits TUI)
- **Verify:** These keys are handled by search bar's `on_key`, forwarded to SessionsList

#### 3.5 Tag-Based Search
- Type `#tagname` in search
- **Verify:** Filters to sessions with that tag only
- Type `#tag1 #tag2`
- **Verify:** AND semantics — only sessions with both tags appear
- Type `sometext #tag`
- **Verify:** Combines fuzzy text match with tag filter

#### 3.6 Search with No Results
- Type a query that matches nothing
- **Verify:** "no sessions found" message appears
- **Verify:** Preview shows "no session selected"
- **Verify:** Pressing Enter does nothing (no crash)
- **Verify:** Pressing j/k does nothing (no crash, no index error)

#### 3.7 Search Escape Behavior (Multi-Layer)
- Type a query, then press Escape once
- **Verify:** Query clears but filtered results may remain visible (first Escape clears query)
- Press Escape again
- **Verify:** Search bar deactivates, focus returns to sessions list
- **Verify:** Full session list restored

#### 3.8 Backspace in Search
- Type "hello", then press Backspace 3 times
- **Verify:** Query becomes "he", results update accordingly
- Press Backspace 2 more times
- **Verify:** Query becomes empty, all sessions shown
- Press Backspace on empty query — no crash, no-op

#### 3.9 Search with Special Characters
- Type Unicode characters (emoji, CJK, accented letters) in search
- **Verify:** No crash, rendering is correct
- Type very long query (100+ chars)
- **Verify:** Search bar handles overflow gracefully (truncation or horizontal scroll)

---

### SECTION 4: Session Actions

#### 4.1 Resume (Enter)
- Highlight a session, press Enter
- **Verify:** TUI exits, Claude Code launches with `--resume <session_id>`
- **Verify:** Working directory changes to the session's cwd
- **Verify:** After Claude exits, TUI relaunches (the while loop in launch_tui)

#### 4.2 Resume from Search
- Search for a session, use Up/Down to navigate filtered results, press Enter
- **Verify:** Correct session is resumed (the one under cursor, not the first result)

#### 4.3 Rename (r) — Positive
- Press `r` on a session
- **Verify:** Inline input appears with label "rename: " and a blinking cursor (block char)
- **Verify:** If session already has a custom_name, it pre-fills the buffer
- **Verify:** Footer changes to "Enter save  Esc cancel"
- Type a new name, press Enter
- **Verify:** Name updates in the list immediately
- **Verify:** Footer reverts to normal mode

#### 4.4 Rename — Edge Cases
- Rename to an empty string (clear existing name, press Enter)
- **Verify:** custom_name is set to NULL, session shows first_prompt or "(untitled)"
- Rename to a very long string (100+ chars)
- **Verify:** Display truncates at 38 chars, but full name is stored in DB
- Rename with Unicode characters
- **Verify:** Stored and displayed correctly
- Press `r` then immediately press Escape
- **Verify:** Rename cancelled, original name preserved
- Press `r` when no sessions exist — **Verify:** no crash, no-op

#### 4.5 Rename — Input Isolation
- While in rename mode, press view-switching keys (1, 2, 3, Tab)
- **Verify:** Keys are captured as input text, NOT as view switches
- While in rename mode, press `j`, `k`, `/`
- **Verify:** These appear as text in the rename buffer, not as navigation

#### 4.6 Tag (t) — Positive
- Press `t` on a session
- **Verify:** Inline input appears with label "tag: " and cursor
- **Verify:** Footer changes to "Enter apply  Esc cancel"
- Type a tag name (alphanumeric + hyphens + underscores), press Enter
- **Verify:** Tag appears next to the session as `#tagname`
- Press `t` again, type the same tag
- **Verify:** Tag is toggled OFF (removed) — tag disappears

#### 4.7 Tag — Edge Cases
- Type a tag with invalid characters (spaces, `@`, `!`, `.`)
- **Verify:** Tag is rejected silently (regex `^[\w\-]+$` check), no crash
- Type an empty tag and press Enter
- **Verify:** No tag applied, no crash
- Apply tag to bulk selection (select multiple with Space, then press `t`)
- **Verify:** Tag is applied/toggled on ALL selected sessions

#### 4.8 Favorite (f) — Positive
- Press `f` on a non-favorite session
- **Verify:** Session moves to the "favorites" section at the top
- **Verify:** Star marker `*` appears
- Press `f` again
- **Verify:** Session unfavorited, moves back to time-bucketed position

#### 4.9 Favorite — Bulk
- Select 3 sessions with Space, then press `f`
- **Verify:** All 3 are favorited/unfavorited
- **Verify:** Cursor position adjusts if list reorders

#### 4.10 Archive (u) — Positive
- Press `u` on a session
- **Verify:** Session disappears from the list (archived sessions are hidden by default)
- **Verify:** Selection is cleared after archive
- **Verify:** Counts update in header and search bar

#### 4.11 Archive — Edge Cases
- Archive the last remaining session
- **Verify:** List shows "no sessions found", no crash
- Archive with bulk selection
- **Verify:** All selected sessions archived, selection cleared

#### 4.12 Delete (d) — DANGER: No Confirmation
- Press `d` on a session
- **Verify:** Session is PERMANENTLY deleted (no undo, no confirmation dialog)
- **Verify:** This is a UX concern — document whether a confirmation should exist
- **Verify:** Cursor adjusts to valid position after deletion

#### 4.13 Delete — Edge Cases
- Delete the only session — **Verify:** "no sessions found", no crash
- Delete with bulk selection — **Verify:** all selected sessions deleted
- Delete the last session in the list when cursor is at the end — **Verify:** cursor moves up, no index error
- Delete when "no sessions found" already shows — **Verify:** no crash

#### 4.14 Sort Cycling (s)
- Press `s` once: sort changes from "frecency" to "recency"
- **Verify:** Search bar shows updated sort mode label
- **Verify:** Session order changes (now pure recency — most recent first)
- Press `s` again: changes to "frequency"
- **Verify:** Sessions sorted by resume count (most-resumed sessions first)
- Press `s` again: cycles back to "frecency"
- **Verify:** Setting persists in DB (re-launch TUI, sort mode is remembered)

#### 4.15 Hide Missing Dirs (H)
- Press `H` (Shift+H)
- **Verify:** Sessions whose cwd directory no longer exists on disk are hidden
- **Verify:** Count updates
- Press `H` again
- **Verify:** Hidden sessions reappear
- **Verify:** Setting persists in DB

---

### SECTION 5: Bulk Selection

#### 5.1 Select/Deselect Individual (Space)
- Press Space on a session
- **Verify:** `[x]` marker appears in the selection column
- Press Space again on the same session
- **Verify:** `[x]` is removed (selection column disappears when no sessions are selected)

#### 5.2 Select All (a)
- Press `a`
- **Verify:** ALL visible sessions get `[x]` markers
- **Verify:** If search is active, only filtered sessions are selected

#### 5.3 Clear Selection (Escape)
- Select some sessions, then press Escape
- **Verify:** Selection clears (all `[x]` removed)
- **Verify:** If there is also an active search, Escape priority is: input_mode > search active > search query > filter_cwd > selection > quit

#### 5.4 Bulk Operations
- Select 5 sessions, press `f` — all 5 favorited
- Select 3 sessions, press `t`, type a tag, Enter — tag applied to all 3
- Select 4 sessions, press `u` — all 4 archived
- Select 2 sessions, press `d` — all 2 deleted
- **Verify:** Each bulk operation works correctly on every selected session

#### 5.5 Selection Persistence During Navigation
- Select sessions scattered throughout the list
- Navigate with j/k/g/G
- **Verify:** Selection marks persist through navigation
- **Verify:** Selection persists through sort mode changes

---

### SECTION 6: View Switching

#### 6.1 Tab Cycling
- Press Tab: Sessions -> Overview -> Projects -> Help -> Sessions
- Press Shift+Tab: reverse order
- **Verify:** Each view renders correctly when switched to
- **Verify:** Footer updates context keys for each view

#### 6.2 Number Key Switching
- Press `1`: always goes to Sessions
- Press `2`: always goes to Overview
- Press `3`: always goes to Projects
- Press `?`: always goes to Help
- **Verify:** Pressing the key for the current view is a no-op (no re-mount flicker)

#### 6.3 View Switching During Active State
- Start a search query, then press Tab to switch views
- **Verify:** Behavior is well-defined (search may persist or clear — document actual behavior)
- Start rename mode, then press `2` (this should type "2" into rename buffer, NOT switch views)
- **Verify:** Input mode intercepts all keys

#### 6.4 Escape from Non-Sessions Views
- Go to Overview, press Escape
- **Verify:** Returns to Sessions view (not quit)
- Go to Help, press Escape
- **Verify:** Returns to Sessions view
- From Sessions with no special state, press Escape
- **Verify:** TUI quits

---

### SECTION 7: Overview View

#### 7.1 Statistics Display
- Switch to Overview (press `2`)
- **Verify:** "Totals" section shows: sessions count, favorites count, messages total, tokens total, estimated cost
- **Verify:** Cost format: `<$0.01` for tiny amounts, `$X.XX` for <$100, `$X,XXX` for large
- **Verify:** "Last 30 days" sparkline renders with block characters
- **Verify:** "This week" section shows sessions, tokens, cost for last 7 days
- **Verify:** "By model" section groups by model from env_json
- **Verify:** "Span" shows oldest to newest session relative times

#### 7.2 Overview with No Data
- Empty DB: switch to Overview
- **Verify:** Shows zeros, no crash on sparkline, no division by zero

#### 7.3 Overview with Extreme Data
- Sessions with very large token counts (millions)
- **Verify:** Numbers render with comma separators, cost displays correctly

---

### SECTION 8: Projects View

#### 8.1 Project List (Positive)
- Switch to Projects (press `3`)
- **Verify:** Projects listed by cwd, sorted by last activity (favorites first)
- **Verify:** Each row shows: favorite star, language tag, cwd path, bar chart, session count, relative time
- **Verify:** Bar chart scales relative to the project with most sessions
- **Verify:** Cursor navigation works (j/k/Up/Down)

#### 8.2 Project Favorite (f)
- Press `f` on a project
- **Verify:** Star appears, project moves to favorites section at top
- Press `f` again
- **Verify:** Unfavorited, moves back

#### 8.3 Project Drill-Down (Enter)
- Press Enter on a project
- **Verify:** Switches to Sessions view filtered to that project's cwd
- **Verify:** Only sessions from that project appear
- Press Escape to clear the project filter
- **Verify:** All sessions appear again

#### 8.4 Project View — No Projects
- Empty DB: switch to Projects
- **Verify:** "no projects found" displays

#### 8.5 Project Path Display
- Project with cwd under `$HOME`
- **Verify:** Path shows `~/...` (tilde substitution)
- Project with very long path
- **Verify:** Handled gracefully (may not truncate like sessions view — verify)

---

### SECTION 9: Help View

#### 9.1 Help Content
- Press `?` to enter Help view
- **Verify:** All documented keybindings are listed and accurate
- **Verify:** Sections: Navigation, Actions, Bulk Selection, Search & Filter, Projects View, Shell Commands
- **Verify:** Key labels are styled in accent color
- **Verify:** Descriptions are styled dim

#### 9.2 Help Accuracy Audit
- Cross-reference every keybinding in the help text against actual code behavior:
  - `r` in Projects view says "Rename project" — **Verify:** is this actually implemented? (check ProjectsView.on_key for 'r' handler)
  - Help says `#tag` uses "AND semantics for multiple" — **Verify:** correct per `_parse_search` and `list_sessions`
  - Help mentions `Esc` to "Clear selection (or quit if none selected)" — **Verify:** actual Escape layering is more complex (input_mode > search active > search query > filter_cwd > selection > quit)

---

### SECTION 10: Preview Pane

#### 10.1 Transcript Preview (Positive)
- Highlight a session with a known transcript
- **Verify:** Preview shows cwd, message count, token count
- **Verify:** Last 6 messages displayed with role labels (you/asst/sys/tool)
- **Verify:** User messages styled in accent color, assistant in blue

#### 10.2 No Transcript
- Highlight a session with no transcript file on disk
- **Verify:** Shows "(no transcript on disk)"

#### 10.3 No Session Selected
- Clear all sessions via search with no results
- **Verify:** Preview shows "no session selected"

#### 10.4 Preview Updates on Cursor Move
- Navigate up and down through sessions
- **Verify:** Preview updates for each session (no stale data, no lag)

---

### SECTION 11: Terminal Resize / Responsive Behavior

#### 11.1 Standard Sizes
- Test at 120x40 (standard), 80x24 (classic), 132x43 (wide)
- **Verify:** Layout adapts, no overlapping elements, no truncation of critical info

#### 11.2 Minimum Size
- Resize to 40x12 (very small)
- **Verify:** No crash, graceful degradation
- **Verify:** Session rows may be truncated but remain readable
- **Verify:** Scrolling still works

#### 11.3 Very Wide Terminal
- Resize to 200x60
- **Verify:** No excessive whitespace or misalignment
- **Verify:** Content doesn't stretch absurdly

#### 11.4 Live Resize
- While TUI is running, resize the terminal dynamically
- **Verify:** Textual re-renders, no artifacts, cursor position preserved
- Resize during search input — no crash
- Resize during rename input — no crash

#### 11.5 Single Column Width
- Resize width to minimum (e.g., 20 columns)
- **Verify:** No crash, rendering may be ugly but should not panic

---

### SECTION 12: Escape Key Layering (Priority Testing)

The Escape key has a complex, layered behavior defined in `action_back_or_quit`. Test each layer in isolation and in combination:

#### 12.1 Layer 1: Input Mode Active
- Enter rename mode (`r`), press Escape
- **Verify:** Rename cancelled, stays in Sessions view
- Enter tag mode (`t`), press Escape
- **Verify:** Tag cancelled, stays in Sessions view

#### 12.2 Layer 2: Search Bar Active
- Press `/` to activate search, press Escape
- **Verify:** Search bar deactivates, focus returns to session list

#### 12.3 Layer 3: Search Query Present
- Type a search query, deactivate search (Escape from Layer 2), then press Escape again
- **Verify:** Query clears, all sessions shown

#### 12.4 Layer 4: CWD Filter Active
- Enter from Projects view (sets filter_cwd), press Escape
- **Verify:** CWD filter clears, all sessions shown

#### 12.5 Layer 5: Selection Active
- Select some sessions with Space, press Escape
- **Verify:** Selection clears

#### 12.6 Layer 6: Quit
- No special state, press Escape
- **Verify:** TUI exits cleanly

#### 12.7 Combined Layers
- Activate search, type a query, select some sessions, press Escape multiple times
- **Verify:** Each press clears one layer in correct priority order
- Count the number of Escape presses needed to fully quit from maximum state

---

### SECTION 13: Focus and Input Priority

#### 13.1 Key Capture in Input Mode
- Enter rename/tag mode
- Press every key: letters, numbers, symbols, Tab, Shift+Tab, 1/2/3, `?`, `/`, `j`, `k`, Space
- **Verify:** All printable keys add to the input buffer, NOT trigger navigation or view switching
- Only Enter (submit) and Escape (cancel) should escape input mode

#### 13.2 Key Capture in Search Mode
- Activate search bar
- Press `1`, `2`, `3`, `?`, `s`, `r`, `f`, `d`, `t`, `u`
- **Verify:** Each character is added to the search query (they are printable characters)
- **Verify:** These do NOT trigger session actions or view switches

#### 13.3 Focus After View Switch
- Switch to Overview (press 2), then back to Sessions (press 1)
- **Verify:** SessionsList has focus, cursor is preserved
- **Verify:** Keyboard navigation works immediately without clicking

---

### SECTION 14: Data Integrity

#### 14.1 Rename Persistence
- Rename a session, quit TUI, relaunch
- **Verify:** Renamed session retains its custom name

#### 14.2 Tag Persistence
- Add a tag, quit, relaunch
- **Verify:** Tag is still attached

#### 14.3 Favorite Persistence
- Toggle favorite, quit, relaunch
- **Verify:** Favorite state persisted

#### 14.4 Sort Mode Persistence
- Change sort mode with `s`, quit, relaunch
- **Verify:** Same sort mode is active on next launch

#### 14.5 Hide Missing Dirs Persistence
- Toggle `H`, quit, relaunch
- **Verify:** Setting persisted

#### 14.6 Concurrent Access
- Open two tmux panes, both running `uv run seshi`
- Make changes in one (rename, tag, favorite)
- **Verify:** No SQLite locking errors (WAL mode should handle this)
- **Verify:** Second instance doesn't crash, though it may show stale data until reload

---

### SECTION 15: Theme and Visual Presentation

#### 15.1 Default Theme (Coral)
- **Verify:** Accent color is `#E08A5E` (warm coral/orange)
- **Verify:** Background is dark (`#1a1a2e`)
- **Verify:** Borders, selected text, and dimmed text are visually distinct

#### 15.2 Theme Switching
- Change theme via `uv run seshi config set theme catppuccin` (CLI command), then relaunch TUI
- **Verify:** All accent colors update: header, footer, search bar, session highlights, preview roles
- Repeat for several themes: gruvbox, nord, dracula, tokyo-night, rose-pine, mono
- **Verify:** Each theme is visually coherent and readable

#### 15.3 Color Contrast
- For each theme, verify:
  - Cursor row (reverse video) is clearly distinguishable from non-cursor rows
  - Favorite star is visible
  - Tags are readable
  - Time bucket headers are visible but not dominant
  - Footer keys are distinguishable from labels
  - Preview role labels (user vs assistant) use different colors

#### 15.4 Mono Theme Special Case
- Switch to "mono" theme (all white/gray)
- **Verify:** Still usable, no invisible elements due to same fg/bg colors

---

### SECTION 16: UX Best Practices Audit

Rate each of these on a 1-5 scale and document observations:

#### 16.1 Discoverability
- Can a new user figure out available actions without reading help?
- Is the footer sufficient for key discovery?
- Are there hidden features with no hint (e.g., `H` for hide missing, `a` for select all)?

#### 16.2 Feedback and Responsiveness
- Does every keypress produce visible feedback?
- Are there any actions that take >100ms with no loading indicator?
- Does the cursor blink at a comfortable rate?

#### 16.3 Error Prevention
- `d` (delete) has NO confirmation dialog — this is destructive and irreversible
- **Evaluate:** Should there be a confirmation step? At minimum for bulk deletion?
- Are there any actions that could lose data without warning?

#### 16.4 Consistency
- Do vim keys (j/k) and arrow keys work identically everywhere?
- Is Escape behavior consistent (always "go back one level")?
- Do the same keys work the same way in Sessions vs Projects view?

#### 16.5 Information Density
- Is the session row layout appropriate? In narrow mode (width < 60, e.g. the left panel of horizontal split), the compact format shows selection + favorite + title + time. In wide mode (width >= 60), the full format shows selection + favorite + lang + title + cwd + time + tags.
- Can users scan the list quickly?
- Is truncation appropriate for both narrow and wide rendering modes?

#### 16.6 Accessibility
- Does the TUI work with screen readers (basic terminal accessibility)?
- Are colors the ONLY differentiator, or is there also text/shape distinction?
- The `*` for favorites and `[x]` for selection provide non-color indicators — good

#### 16.7 Forgiveness / Undo
- Which actions are reversible? (favorite toggle, archive toggle, rename)
- Which are NOT reversible? (delete — no undo, no trash)
- Is this clear to the user before they act?

#### 16.8 Navigation Depth
- Maximum depth: Sessions -> Search -> Input Mode (3 levels)
- Can the user always get back to the top with repeated Escape? Yes, verify this

#### 16.9 Empty States
- Every empty state should have a helpful message, not a blank screen
- "no sessions found" — present but could suggest running `seshi scan`
- "no projects found" — present but could suggest how to create sessions
- "(no transcript on disk)" — present, informative

#### 16.10 Performance
- With 100+ sessions, is rendering instant?
- Does search filtering lag with many sessions?
- Does the sparkline in Overview compute quickly?

---

### SECTION 17: Negative / Adversarial Testing

#### 17.1 Rapid Key Mashing
- Mash random keys as fast as possible for 10 seconds
- **Verify:** No crash, no corrupted state, no orphaned input modes

#### 17.2 Ctrl+C During Operation
- Press Ctrl+C during rename input
- Press Ctrl+C during search
- Press Ctrl+C from any view
- **Verify:** TUI exits cleanly or handles the interrupt gracefully

#### 17.3 Suspend/Resume (Ctrl+Z)
- Press Ctrl+Z to suspend the TUI
- Run `fg` to resume
- **Verify:** TUI renders correctly after resume

#### 17.4 Pipe/Redirect Edge Cases
- Run `uv run seshi | cat` — should detect non-TTY and redirect to /dev/tty or fail gracefully
- Run `echo "" | uv run seshi` — should handle stdin redirect

#### 17.5 Database Corruption
- Corrupt the SQLite DB file (truncate it), then launch seshi
- **Verify:** Graceful error message, no Python traceback shown to user

#### 17.6 Missing Database
- Delete `~/.seshi/seshi.db`, then launch seshi
- **Verify:** DB is recreated with empty schema, TUI shows "no sessions found"

#### 17.7 Concurrent Modification
- While TUI is running, use CLI to modify the same session (`uv run seshi rename <id> "new name"`)
- **Verify:** TUI may show stale data but doesn't crash

#### 17.8 Unicode Bomb
- Rename a session to a string with combining characters, RTL marks, zero-width joiners
- **Verify:** Display doesn't break layout (columns may misalign — document if so)

#### 17.9 Very Long Tag
- Apply a tag that is 200+ characters long
- **Verify:** Accepted (matches regex), display handles overflow

---

### SECTION 18: Session Resume Flow

#### 18.1 Normal Resume
- Press Enter on a session
- **Verify:** TUI exits, `claude --resume <session_id>` launches
- **Verify:** CWD changes to session's cwd
- **Verify:** After Claude exits, TUI relaunches (while loop)

#### 18.2 Resume Session with Missing CWD
- Resume a session whose cwd no longer exists
- **Verify:** `os.chdir` fails silently (OSError caught), Claude still launches
- **Verify:** No crash

#### 18.3 Resume Session with Malformed launch_argv_json
- Session with invalid JSON in launch_argv_json
- **Verify:** Falls back to empty argv list, still launches `claude --resume <id>`

#### 18.4 Resume from Projects Drill-Down
- Go to Projects, press Enter on a project, then in the filtered Sessions view press Enter on a session
- **Verify:** Correct session resumes

---

### SECTION 19: Search Bar Display Details

#### 19.1 Sort Mode Display
- **Verify:** Current sort mode (frecency/recency/frequency) shown in search bar
- Change sort mode with `s`
- **Verify:** Search bar label updates immediately

#### 19.2 Count Display
- **Verify:** Format is `{shown} / {total}` at the right edge of the search bar
- Apply a search filter
- **Verify:** `shown` decreases, `total` stays the same
- Clear filter
- **Verify:** `shown` equals `total` again

#### 19.3 Cursor Blink
- Activate search bar
- **Verify:** Cursor (block character `▮`) blinks on/off at ~500ms
- Deactivate search bar
- **Verify:** Cursor shows as dim (non-blinking) block

---

### SECTION 20: Projects View Rename

The help text mentions `r` to "Rename project" in Projects view, but the code (ProjectsView.on_key) only handles `up/k`, `down/j`, `f`, and `enter`. 

- Press `r` in Projects view
- **Verify:** Is this a no-op? Or does it crash?
- **Document:** This appears to be a missing feature (help text promises it but code doesn't implement it)

---

## Reporting Template

For each test case, record:

```
Test ID: [Section.Number]
Status: PASS / FAIL / PARTIAL / SKIP
Observation: [What actually happened]
Expected: [What should have happened]
Screenshot: [tmux capture-pane output or file path]
Severity: Critical / High / Medium / Low / Info
UX Note: [Any UX improvement suggestion]
```

## Summary Checklist

After completing all tests, answer these questions:

1. Did any test cause a crash or unhandled exception?
2. Did any test result in data loss without warning?
3. Are there any keybindings documented in Help that don't work?
4. Are there any keybindings that work but aren't documented in Help?
5. Is the Escape key layering intuitive and predictable?
6. Does the TUI render correctly at all tested terminal sizes?
7. Are all themes visually coherent and accessible?
8. Does the `d` (delete) action need a confirmation dialog?
9. Is the search experience smooth and responsive?
10. Can a first-time user navigate the TUI without reading documentation?
