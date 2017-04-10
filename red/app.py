import curses
import queue
import time

class Application:
    def __init__(self):
        # The current curses screen and its size
        self.screen = None
        self.n_lines, self.n_cols = 0, 0

        # A flag indicating if the application should exit
        self._should_exit = False

        # A queue of timers in for form of (deadline, callable) tuples
        self._timer_queue = queue.PriorityQueue()

    def run(self):
        curses.wrapper(self._curses_main)

    def _curses_main(self, screen):
        """Wrapped function after terminal is set up and the alternate screen
        switched to.

        """
        # Ensure the terminal is in "raw" mode and set up the colour palette
        curses.raw()

        # Record the current curses screen and synthesize a redraw event
        self.screen = screen
        self.n_lines, self.n_cols = self.screen.getmaxyx()

        # Delegate events
        self.start()
        self.resize()

        # Start event loop
        while not self._should_exit:
            # When is the next timer deadline?
            try:
                deadline, timer_cb = self._timer_queue.get(False)
                now = time.monotonic()
                self.screen.timeout(max(0, int(1e3 * (deadline-now))))
            except queue.Empty:
                deadline, timer_cb = -1, None
                self.screen.timeout(-1)

            # Get next keypress
            try:
                ch = screen.get_wch()
            except curses.error:
                # timeout
                ch = None

            # Call timer if we timed out
            if ch is None and timer_cb is not None:
                timer_cb()
            elif timer_cb is not None:
                # otherwise, put back on queue for next time
                self._timer_queue.put((deadline, timer_cb))

            # Process input
            if ch == curses.KEY_RESIZE:
                self.n_lines, self.n_cols = self.screen.getmaxyx()
                self.resize()
            elif ch is not None:
                self.key_press(ch)

    def add_timer(self, delay, cb):
        assert delay >= 0
        self._timer_queue.put((time.monotonic() + delay, cb))

    def quit(self):
        """Signal that the application should exit."""
        self._should_exit = True

    def start(self):
        """Called at application start."""
        pass

    def resize(self):
        """Called when the screen has re-sized."""
        pass

    def key_press(self, ch):
        """Called when a string or integer key press is available."""
        pass
