import curses

def main():
    editor = Editor()
    curses.wrapper(editor.curses_main)

def ctrl_key(key):
    """Return string corresponding to Ctrl-<key>. Key should be a lower-case
    alphabetic character or '@'.

    """
    return chr(ord(key) & 0x1f)

class Editor:
    def __init__(self):
        self.screen = False
        self.should_exit = False

    def curses_main(self, screen):
        """Wrapped function after terminal is set up and the alternate screen
        switched to.

        """
        # Ensure the terminal is in "raw" mode
        curses.raw()

        # Record the current curses screen
        self.screen = screen

        # Start event loop
        while not self.should_exit:
            self.handle_key(screen.get_wch())

    def handle_key(self, key):
        if key == ctrl_key('q'):
            self.should_exit = True
