import curses
from curses.ascii import ctrl
import enum
import queue
import time

from wcwidth import wcwidth, wcswidth

from .app import Application

def main():
    app = Editor()
    #app.add_timer(3.5, app.quit)
    app.run()

class Editor(Application):
    def __init__(self):
        super(Editor, self).__init__()

        # A simple dictionary mapping key-presses to callables.
        self.key_bindings = {
            ctrl('q'): self.quit,
        }

    def start(self):
        setup_curses_colour_pairs()

    def resize(self):
        self.redraw()

    def key_press(self, ch):
        handler = self.key_bindings.get(ch)
        if handler is not None:
            handler()
        self.redraw()

    def redraw(self):
        """Redraw the screen."""
        curses.curs_set(0)
        self.screen.leaveok(1)

        self.screen.bkgdset(' ', style_attr(Style.WINDOW_BACKGROUND))
        self.screen.erase()

        if self.n_lines > 3 and self.n_cols >= 3:
            draw_frame(
                self.screen, 0, 0, self.n_lines - 1, self.n_cols,
                style=Style.WINDOW_BORDER, frame_style=FrameStyle.DOUBLE)

        self.draw_status()

        self.screen.leaveok(0)
        curses.curs_set(1)
        if self.n_lines > 1 and self.n_cols > 1:
            self.screen.move(1, 1)

        self.screen.refresh()

    def draw_status(self):
        if self.n_lines < 1:
            return

        # Clear status bar
        self.screen.move(self.n_lines-1, 0)
        self.screen.bkgdset(' ', style_attr(Style.STATUS_BAR))
        self.screen.clrtoeol()

        # Draw status bar line
        draw_regions(self.screen, [
            (' ', Style.STATUS_BAR),
            ('Ctrl-Q', Style.STATUS_BAR_HL),
            (' Quit', Style.STATUS_BAR),
        ], y=self.n_lines-1, x=0)

def draw_regions(win, regions, y=None, x=None, max_w=None):
    # pylint: disable=too-many-locals,too-many-branches
    # Get cursor position and window size
    cy, cx = win.getyx()
    nl, nc = win.getmaxyx()

    # Set default values
    if y is None:
        y = cy
    if x is None:
        x = cx
    if max_w is None:
        max_w = max(0, nc - x)

    # Use max_w to set nc
    nc = min(nc, x + max_w)

    # Abort if x or y outside of window
    if x < 0 or x >= nc or y < 0 or y >= nl:
        return

    # Otherwise, let's go
    for region in regions:
        text, style = region
        attr = style_attr(style)

        # Get width of region in cells and remaining space
        region_w = wcswidth(text)
        w_remaining = nc - x
        assert w_remaining >= 0

        if region_w != -1 and w_remaining >= region_w:
            # If this text fits in the remaining space, just use addstr. Note
            # that we need to silently ignore any errors from addstr as per
            # https://bugs.python.org/issue8243
            try:
                win.addstr(y, x, text, attr)
            except curses.error:
                pass
            x += region_w
        else:
            # The remaining space is too small, add character-by-character
            for c in text:
                c_w = wcwidth(c)
                if c_w == -1:
                    continue
                if w_remaining >= c_w:
                    try:
                        win.addstr(y, x, c, attr)
                    except curses.error:
                        pass
                x += c_w
                w_remaining -= c_w

        # We're done if we're past the end of the line
        if x >= nc:
            break

def setup_curses_colour_pairs():
    """Associate sensible colour pairs for the values in Style."""
    if curses.COLORS == 256:
        p = TerminalPalette256
    else:
        raise RuntimeError('Only 256 colour terminals supported')

    curses.init_pair(Style.WINDOW_BORDER, p.BRIGHT_WHITE, p.BLUE)
    curses.init_pair(Style.WINDOW_BACKGROUND, p.LIGHT_GREY, p.BLUE)
    curses.init_pair(Style.STATUS_BAR, p.BLACK, p.LIGHT_GREY)
    curses.init_pair(Style.STATUS_BAR_HL, p.RED, p.LIGHT_GREY)

class Style(enum.IntEnum):
    """Styles for character cells."""
    WINDOW_BORDER = 1
    WINDOW_BACKGROUND = 2
    STATUS_BAR = 3
    STATUS_BAR_HL = 4

def style_attr(style):
    """Convert a style to a curses attribute value."""
    return curses.color_pair(style)

class TerminalPalette256(enum.IntEnum):
    """A terminal palette suitable for 256 colour displays."""

    BLACK = 16
    BLUE = 19
    GREEN = 34
    CYAN = 37
    RED = 124
    MAGENTA = 127
    BROWN = 130
    LIGHT_GREY = 248
    DARK_GREY = 240

    BRIGHT_BLUE = 63
    BRIGHT_GREEN = 83
    BRIGHT_CYAN = 87
    BRIGHT_RED = 203
    BRIGHT_MAGENTA = 207
    BRIGHT_YELLOW = 227
    BRIGHT_WHITE = 231

class FrameStyle(enum.Enum):
    SINGLE = 1
    DOUBLE = 2

def draw_frame(win, y, x, h, w, style, frame_style=FrameStyle.SINGLE):
    # pylint: disable=too-many-arguments
    if frame_style is FrameStyle.SINGLE:
        tlc, trc, blc, brc, hc, vc = '\u250c\u2510\u2514\u2518\u2500\u2502'
    elif frame_style is FrameStyle.DOUBLE:
        tlc, trc, blc, brc, hc, vc = '\u2554\u2557\u255a\u255d\u2550\u2551'
    else:
        raise TypeError('style is invalid')

    # Cannot draw < 3x3 frames
    if h < 3 or w < 3:
        return

    draw_regions(win, [
        (tlc, style), (hc * max(0, w-2), style), (trc, style)
    ], y=y, x=x)
    draw_regions(win, [
        (blc, style), (hc * max(0, w-2), style), (brc, style)
    ], y=y+h-1, x=x)

    for side_y in range(y+1, y+h-1):
        draw_regions(win, [(vc, style)], y=side_y, x=x)
        draw_regions(win, [(vc, style)], y=side_y, x=x+w-1)
