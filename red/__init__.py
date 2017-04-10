import curses
from curses.ascii import ctrl
import enum
import queue
import time

from wcwidth import wcwidth, wcswidth

from .app import Application

def main():
    app = Editor()
    app.add_timer(3.5, app.quit)
    app.run()

class Editor(Application):
    def __init__(self):
        super(Editor, self).__init__()

        # A simple dictionary mapping key-presses to callables.
        self.key_bindings = {
            ctrl('q'): self.quit,
        }

        # The curses screen for the app
        self.screen = None
        self.n_lines, self.n_cols = 0, 0

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

        draw_frame(
            self.screen, 0, 0, self.n_lines - 1, self.n_cols,
            style_attr(Style.WINDOW_BORDER), FrameStyle.DOUBLE)

        self.draw_status()

        self.screen.leaveok(0)
        curses.curs_set(1)
        self.screen.move(1, 1)

        self.screen.refresh()

    def draw_status(self):
        self.screen.move(self.n_lines-1, 0)
        self.screen.bkgdset(' ', style_attr(Style.STATUS_BAR))
        self.screen.clrtoeol()

        self.screen.attrset(style_attr(Style.STATUS_BAR))
        put_regions(self.screen, [
            ' ',
            ('Ctrl-Q', style_attr(Style.STATUS_BAR_HL)),
            ' Quit'
        ])

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

def draw_frame(win, y, x, h, w, attr=0, style=FrameStyle.SINGLE):
    # pylint: disable=too-many-arguments
    if style is FrameStyle.SINGLE:
        tlc, trc, blc, brc, hc, vc = '\u250c\u2510\u2514\u2518\u2500\u2502'
    elif style is FrameStyle.DOUBLE:
        tlc, trc, blc, brc, hc, vc = '\u2554\u2557\u255a\u255d\u2550\u2551'
    else:
        raise TypeError('style is invalid')

    # Cannot draw < 2x2 frames
    if h < 2 or w < 2:
        return

    put_regions(win, y, x, [
        (tlc, attr), (hc * max(0, w-2), attr), (trc, attr)
    ])
    put_regions(win, y+h-1, x, [
        (blc, attr), (hc * max(0, w-2), attr), (brc, attr)
    ])

    for side_y in range(y+1, y+h-1):
        put_regions(win, side_y, x, [(vc, attr)])
        put_regions(win, side_y, x+w-1, [(vc, attr)])

def put_regions(win, *args):
    """Write regions of text to the window at a given position. Each region
    is either a string or a tuple containing a string and curses attribute
    number. Output is clipped to the right-side of the screen.

    Arguments are str, [attr] or y, x, str, [attr] like other curses functions.

    """
    # pylint:disable=too-many-branches

    if len(args) == 1:
        regions = args[0]
        attr = 0
        y, x = win.getyx()
    elif len(args) == 2:
        regions, attr = args
        y, x = win.getyx()
    elif len(args) == 3:
        y, x, regions = args
        attr = 0
    elif len(args) == 4:
        y, x, regions, attr = args
    else:
        raise TypeError('put_regions takes 1 to 4 arguments')

    n_rows, n_cols = win.getmaxyx()

    # Ignore out of range y
    if y >= n_rows or y < 0:
        return

    for region in regions:
        # Immediately abort if x is beyond printable areas
        if x >= n_cols:
            break

        # Determining if this is a string or a string, attribute pair
        if isinstance(region, tuple):
            s, attr = region[:2]
        else:
            s, attr = region, 0

        # What's the width of this region?
        w = wcswidth(s)

        if w != -1 and x + w < n_cols:
            # In the common case, just use addstr
            win.addstr(y, x, s, attr)
        elif w != -1 and x + w == n_cols:
            # See https://bugs.python.org/issue8243. We need to silently
            # swallow the error from addstr.
            try:
                win.addstr(y, x, s, attr)
            except curses.error:
                pass
        else:
            # We're in a complex position. Output character-by-character
            running_x = x
            for ch in s:
                ch_w = wcwidth(ch)
                if ch_w == -1:
                    continue

                # If there's no space left to write this character, we're
                # done
                if n_cols - running_x < ch_w:
                    break

                if running_x + w >= n_cols:
                    # If we're going to insert at the last column we need to
                    # swallow the error from addstr as above.
                    try:
                        win.addstr(y, running_x, ch, attr)
                    except curses.error:
                        pass
                else:
                    # Insert with addstr
                    win.addstr(y, running_x, ch, attr)

                running_x += ch_w

        # Advance x-position by string width
        x += w
