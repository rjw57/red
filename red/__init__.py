import curses
from curses.ascii import ctrl
import enum

def main():
    editor = Editor()
    curses.wrapper(editor.curses_main)

class Editor:
    def __init__(self):
        self.screen = None
        self.should_exit = False

        # A simple dictionary mapping key-presses to callables.
        self.key_bindings = {
            ctrl('q'): self.quit,
        }

    def curses_main(self, screen):
        """Wrapped function after terminal is set up and the alternate screen
        switched to.

        """
        # Ensure the terminal is in "raw" mode and set up the colour palette
        curses.raw()
        setup_curses_colour_pairs()

        # Record the current curses screen
        self.screen = screen

        # Paint the initial screen
        self.redraw()

        # Start event loop
        while not self.should_exit:
            # Get next keypress
            ch = screen.get_wch()

            # Look up keypress in key bindings dict
            handler = self.key_bindings.get(ch)
            if handler is not None:
                handler()

            self.redraw()

    def redraw(self):
        """Redraw the screen."""
        s = self.screen

        s.bkgdset(' ', attr(Style.WINDOW_BACKGROUND))
        s.erase()

        s.attrset(attr(Style.WINDOW_BORDER))
        s.border()

        s.refresh()

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

class Style(enum.IntEnum):
    """Styles for character cells."""
    WINDOW_BORDER = 1
    WINDOW_BACKGROUND = 2

def attr(style):
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
