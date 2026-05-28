from textual.timer import Timer


class BlinkCursorMixin:
    _cursor_visible: bool = True
    _blink_timer: Timer | None = None

    def _start_blink(self) -> None:
        self._cursor_visible = True
        try:
            self._blink_timer = self.set_interval(0.5, self._toggle_cursor)
        except RuntimeError:
            pass

    def _stop_blink(self) -> None:
        if self._blink_timer:
            self._blink_timer.stop()
            self._blink_timer = None
        self._cursor_visible = True

    def _toggle_cursor(self) -> None:
        self._cursor_visible = not self._cursor_visible
        self.refresh()
