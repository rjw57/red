import curses
from curses.ascii import ctrl
import enum
import queue
import time
import sys

from wcwidth import wcwidth, wcswidth

from .app import Application

def main():
    app = Editor()

    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            app.document.read_from_file(f)

    #app.add_timer(3.5, app.quit)
    app.run()

class Editor(Application):
    def __init__(self):
        super(Editor, self).__init__()

        # A simple dictionary mapping key-presses to callables.
        self.key_bindings = {
            ctrl('q'): self.quit,
            curses.KEY_DOWN: self.move_down,
            curses.KEY_NPAGE: self.move_page_down,
            curses.KEY_UP: self.move_up,
            curses.KEY_PPAGE: self.move_page_up,
        }

        self.document = TextDocument()
        self.cursor_x, self.cursor_y = 0, 0
        self.scroll_y = 0

    def start(self):
        setup_curses_colour_pairs()

    def resize(self):
        self.redraw()

    def key_press(self, ch):
        handler = self.key_bindings.get(ch)
        if handler is not None:
            handler()
        self.redraw()

    def move_down(self):
        if self.cursor_y < len(self.document.rows):
            self.cursor_y += 1

    def move_page_down(self):
        for _ in range(max(1, self.n_lines-3)):
            self.move_down()
        self.scroll_y = len(self.document.rows) + 1 # force scroll

    def move_up(self):
        if self.cursor_y > 0:
            self.cursor_y -= 1

    def move_page_up(self):
        for _ in range(max(1, self.n_lines-3)):
            self.move_up()

    def redraw(self):
        """Redraw the screen."""
        # Move cursor to be within text document bounds
        self.cursor_y = max(0, min(self.cursor_y, len(self.document.rows)))
        if self.cursor_y < len(self.document.rows):
            self.cursor_x = min(
                len(self.document.rows[self.cursor_y].text), self.cursor_x)
        else:
            self.cursor_x = 0

        curses.curs_set(0)
        self.screen.leaveok(1)

        self.screen.bkgdset(' ', style_attr(Style.WINDOW_BACKGROUND))
        self.screen.erase()

        draw_window_frame(
            self.screen, 0, 0, self.n_lines - 1, self.n_cols,
            title='Untitled',
            frame_style=FrameStyle.DOUBLE)

        if self.n_cols > 2:
            n_visible = self.n_lines - 3

            # Scroll the document so that the cursor is visible.
            if self.cursor_y < self.scroll_y:
                self.scroll_y = self.cursor_y
            elif self.cursor_y >= self.scroll_y + n_visible:
                self.scroll_y = max(0, self.cursor_y - n_visible + 1)

            for doc_y, doc_row_idx in enumerate(range(self.scroll_y, self.scroll_y+n_visible)):
                y = doc_y + 1
                if doc_row_idx >= len(self.document.rows):
                    draw_regions(
                        self.screen, [('~', Style.WINDOW_BACKGROUND)], y, 1,
                        self.n_cols-2)
                else:
                    draw_regions(
                        self.screen, self.document.rows[doc_row_idx].rendered,
                        y, 1, self.n_cols-2)

        self.draw_status()

        self.screen.leaveok(0)
        curses.curs_set(1)
        if self.n_lines > 3 and self.n_cols > 2:
            self.screen.move(
                1 + self.cursor_y - self.scroll_y,
                1 + self.cursor_x)

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

class TextRow:
    # pylint: disable=too-few-public-methods
    def __init__(self, s=''):
        self._text = s
        self._rendered = None
        self._render()

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, value):
        self._text = value
        self._render()

    @property
    def rendered(self):
        return self._rendered

    def _render(self):
        self._rendered = [(self._text, Style.WINDOW_BACKGROUND)]

class TextDocument:
    def __init__(self):
        self.rows = []

    def read_from_file(self, file_object):
        self.clear()

        for line in file_object:
            line = line.rstrip('\n\r')
            self.append_row(line)

    def append_row(self, s):
        self.rows.append(TextRow(s))

    def clear(self):
        self.rows = []

def wctrim(s, max_w):
    """Return pair s, w which is a string and the cell width of that string. The
    string is trimmed so that w <= max_w. Characters which wcwidth() reports as
    having negative width are removed.

    """
    assert max_w >= 0

    # Common case: string needs no trimming
    w = wcswidth(s)
    if w >= 0 and w <= max_w:
        return s, w

    # Otherwise, walk character by character
    w, chs = 0, []
    for ch in s:
        ch_w = wcwidth(ch)
        if ch_w < 0:
            continue

        if w + ch_w > max_w:
            return ''.join(chs), w

        chs.append(ch)
        w += ch_w
    return ''.join(chs), w

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

def draw_window_frame(
        win, top, left, height, width,
        title=None, frame_style=FrameStyle.SINGLE):
    # pylint: disable=too-many-arguments

    draw_frame(win, top, left, height, width, Style.WINDOW_BORDER, frame_style)

    # Compute region left for window title
    title_x, title_w = left + 2, width - 4

    if title_w > 2:
        title_text, title_text_w = wctrim(title, title_w-2)
        title_right_pad = (title_w - title_text_w - 2) >> 1
        title_left_pad = title_w - title_text_w - 2 - title_right_pad
        draw_regions(win, [
            (' ', Style.WINDOW_BORDER),
            (title_text, Style.WINDOW_BORDER),
            (' ', Style.WINDOW_BORDER),
        ], y=top, x=title_x+title_left_pad, max_w=title_w)


def draw_frame(win, y, x, h, w, style, frame_style=FrameStyle.SINGLE):
    # pylint: disable=too-many-arguments
    if frame_style is FrameStyle.SINGLE:
        tlc, trc, blc, brc, hc, vc = '\u250c\u2510\u2514\u2518\u2500\u2502'
    elif frame_style is FrameStyle.DOUBLE:
        tlc, trc, blc, brc, hc, vc = '\u2554\u2557\u255a\u255d\u2550\u2551'
    else:
        raise TypeError('style is invalid')

    # Cannot draw < 2x3 frames
    if h < 2 or w < 3:
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
