from textual.widget import Widget
from rich.text import Text


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
  d                  Delete from registry (no confirmation)
  s                  Cycle sort mode (frecency → recency → frequency)
  H                  Toggle hide sessions with missing directories

  Bulk Selection
  ──────────────
  Space              Toggle selection on current row
  a                  Select all visible rows
  Esc                Clear selection (or quit if none selected)

  Search & Filter
  ───────────────
  /                  Focus search bar (type any character freely)
  Type to search     Fuzzy match against name, prompt, and cwd
  #tag               Filter by tag (AND semantics for multiple)
  Backspace          Delete last character
  Esc                Clear search query

  Projects View
  ─────────────
  Enter              Open Sessions view filtered to project
  f                  Toggle project favorite
  r                  Rename project

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

    def render(self) -> Text:
        text = Text()
        for line in HELP_TEXT.strip().split("\n"):
            if line.strip().startswith("──"):
                text.append(line + "\n", style="dim")
            elif line.strip() and not line.startswith("  "):
                text.append(line + "\n", style="bold")
            elif "  " in line.strip() and not line.strip().startswith("seshi"):
                parts = line.split(None, 1)
                if len(parts) == 2:
                    key_part = line[:line.index(parts[1])]
                    text.append(key_part, style="bold #D97757")
                    text.append(parts[1] + "\n", style="dim")
                else:
                    text.append(line + "\n")
            else:
                text.append(line + "\n", style="dim")
        return text
