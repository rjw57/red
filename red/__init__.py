import curses
from curses.ascii import ctrl
import enum

from wcwidth import wcwidth, wcswidth

def main():
    editor = Editor()
    curses.wrapper(editor.curses_main)

class Editor:
    def __init__(self):
        self.win = None
        self.should_exit = False
        self.n_lines, self.n_cols = 0, 0

        # A simple dictionary mapping key-presses to callables.
        self.key_bindings = {
            ctrl('q'): self.quit,

            curses.KEY_RESIZE: self.win_resized,
        }

    def curses_main(self, screen):
        """Wrapped function after terminal is set up and the alternate screen
        switched to.

        """
        # Ensure the terminal is in "raw" mode and set up the colour palette
        curses.raw()
        setup_curses_colour_pairs()

        # Record the current curses screen and cache size
        self.set_win(screen)

        # Start event loop
        while not self.should_exit:
            # Get next keypress
            ch = screen.get_wch()

            # Look up keypress in key bindings dict
            handler = self.key_bindings.get(ch)
            if handler is not None:
                handler()

            self.redraw()

    def set_win(self, win):
        """Update the curses window for the app. Causes a redraw."""
        self.win = win
        self.win_resized()

    def win_resized(self):
        self.n_lines, self.n_cols = self.win.getmaxyx()
        self.redraw()

    def redraw(self):
        """Redraw the screen."""
        curses.curs_set(0)
        self.win.leaveok(1)

        self.win.bkgdset(' ', style_attr(Style.WINDOW_BACKGROUND))
        self.win.erase()

        draw_frame(
            self.win, 0, 0, self.n_lines - 1, self.n_cols,
            style_attr(Style.WINDOW_BORDER), FrameStyle.DOUBLE)

        self.draw_status()

        self.win.leaveok(0)
        curses.curs_set(1)
        self.win.move(1, 1)

        self.win.refresh()

    def draw_status(self):
        self.win.move(self.n_lines-1, 0)
        self.win.bkgdset(' ', style_attr(Style.STATUS_BAR))
        self.win.clrtoeol()

        self.win.attrset(style_attr(Style.STATUS_BAR))
        put_regions(self.win, [
            ' ',
            ('Ctrl-Q', style_attr(Style.STATUS_BAR_HL)),
            ' Quit'
        ])

    def quit(self):
        """Signal that the application should exit."""
        self.should_exit = True

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
