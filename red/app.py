"""Full-screen ncurses application support."""
import asyncio
import curses

import janus

class Application:
    def __init__(self, loop=None):
        self._screen = None

        # Initialise event loop
        if loop is None:
            loop = asyncio.get_event_loop()
        self.loop = loop

        # A future which is satisfied when the app should exit
        self._exit_future = loop.create_future()

        # A thread-safe queue whereby events of interest are passed to the app
        self.event_queue = janus.Queue(loop=loop)

    def exit(self):
        """Schedule application exit."""
        self._exit_future.set_result(True)

    def run(self, running_cb):
        """Run the application to completion."""
        # Curses read loop
        def curses_init(screen):
            self._screen = screen

            def read_loop():
                self._screen.timeout(100)
                while not self._exit_future.done():
                    ch = self._screen.getch()
                    if ch == -1:
                        continue
                    print(ch)

            curses_loop = self.loop.run_in_executor(None, read_loop)
            curses.raw()

            if running_cb is not None:
                self.loop.call_soon(lambda: running_cb(self))

            self.loop.run_until_complete(self._exit_future)
            self.loop.run_until_complete(curses_loop)
        curses.wrapper(curses_init)
        self.loop.close()

    def _curses_read_loop(self):
        pass

def start(running_cb):
    app = Application()
    app.run(running_cb)
