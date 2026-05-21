import os
import sys
import termios
import tty

from seshi.models import Session
from seshi.prompt_text import strip_markup_tags


def confirm_resume(session: Session, query: str) -> str:
    try:
        tty_fd = os.open("/dev/tty", os.O_RDWR)
    except OSError:
        return "no"

    tty_in = os.fdopen(tty_fd, "r", closefd=False)
    tty_out = os.fdopen(tty_fd, "w", closefd=False)

    raw_name = session.custom_name or session.first_prompt or ""
    name = strip_markup_tags(raw_name) or session.session_id[:8]
    home = os.path.expanduser("~")
    cwd = session.cwd
    if cwd.startswith(home):
        cwd = "~" + cwd[len(home):]

    tty_out.write(f"\n  match: \033[1m{name}\033[0m\n")
    tty_out.write(f"  query: {query}\n")
    tty_out.write(f"    cwd: {cwd}\n\n")
    tty_out.write("  \033[38;2;217;119;87mEnter\033[0m resume  "
                   "\033[38;2;217;119;87mt\033[0m open TUI  "
                   "any other key: cancel\n")
    tty_out.flush()

    old_settings = termios.tcgetattr(tty_fd)
    try:
        tty.setraw(tty_fd)
        ch = tty_in.read(1)
    finally:
        termios.tcsetattr(tty_fd, termios.TCSADRAIN, old_settings)
        tty_out.write("\n")
        tty_out.flush()

    os.close(tty_fd)

    if ch in ("\r", "\n"):
        return "yes"
    if ch == "t":
        return "tui"
    return "no"
