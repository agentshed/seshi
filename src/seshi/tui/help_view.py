from textual.widget import Widget
from textual.reactive import reactive
from textual import events
from rich.text import Text


_ASCII_ART = [
    "  █▀▀ █▀▀ █▀▀ █ █ ▀█▀",
    "  ▀▀█ █▀▀ ▀▀█ █▀█  █ ",
    "  ▀▀▀ ▀▀▀ ▀▀▀ ▀ ▀ ▀▀▀",
]

HELP_TEXT = """
  Navigation
  ──────────
  ↑/↓  j/k        Move cursor
  Ctrl-u / Ctrl-d  Page up / down
  g / G            Jump to top / bottom
  Tab / Shift-Tab  Cycle views
  1 2 3 ?          Jump to Sessions / Overview / Projects / Help

  Actions (Sessions view)
  ───────────────────────
  Enter              Resume selected session
  r                  Rename session (inline edit)
  t                  Toggle tag on session
  f                  Toggle favorite
  u                  Toggle archive (reversible hide)
  d                  Delete from registry (with confirmation)
  z                  Undo last action (up to 10 deep)
  s                  Cycle sort mode (frecency → recency → frequency)
  p                  Toggle preview pane
  H                  Toggle hide sessions with missing directories
  S                  Toggle hide stale sessions (no longer in Claude Code)
  Ctrl-p             Open command palette

  Bulk Selection
  ──────────────
  Space              Toggle selection on current row
  Ctrl-a             Select all visible rows
  Esc                Clear selection (or quit if none selected)

  Search & Filter
  ───────────────
  /                  Focus search bar (type any character freely)
  Type to search     Fuzzy match against name, prompt, and cwd
  #tag               Filter by tag (AND semantics for multiple)
  Backspace          Delete last character
  Esc                Clear search and deactivate

  Projects View
  ─────────────
  Enter              Open Sessions view filtered to project
  f                  Toggle project favorite
  r                  Rename project
  g / G              Jump to top / bottom

  Shell Commands
  ──────────────
  seshi                Open TUI
  seshi last           Resume most recent session
  seshi <query>        Fuzzy resume
  seshi list --json    List sessions as JSON
  seshi scan           Discover sessions from disk
  seshi doctor --fix   Auto-repair installation
"""


class HelpView(Widget):
    DEFAULT_CSS = """
    HelpView {
        padding: 1 2;
    }
    """

    can_focus = True

    accent: reactive[str] = reactive("#D97757")

    def render(self) -> Text:
        text = Text()
        text.append(_ASCII_ART[0], style=f"bold {self.accent}")
        text.append("\n")
        text.append(_ASCII_ART[1], style=f"bold {self.accent}")
        text.append("   global session resumer", style="dim")
        text.append("\n")
        text.append(_ASCII_ART[2], style=f"bold {self.accent}")
        text.append("\n\n")
        for line in HELP_TEXT.strip().split("\n"):
            if line.strip().startswith("──"):
                text.append(line + "\n", style="dim")
            elif line.strip() and not line.startswith("  "):
                text.append(line + "\n", style="bold")
            elif "  " in line.strip() and not line.strip().startswith("seshi"):
                parts = line.split(None, 1)
                if len(parts) == 2:
                    key_part = line[:line.index(parts[1])]
                    text.append(key_part, style=f"bold {self.accent}")
                    text.append(parts[1] + "\n", style="dim")
                else:
                    text.append(line + "\n")
            else:
                text.append(line + "\n", style="dim")
        return text

    def on_key(self, event: events.Key) -> None:
        if event.key in ("down", "j"):
            self.scroll_relative(y=1)
            event.stop()
        elif event.key in ("up", "k"):
            self.scroll_relative(y=-1)
            event.stop()
