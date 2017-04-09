"""Full-screen ncurses application support."""
import asyncio
from concurrent.futures import CancelledError
import curses
import enum

import janus

def run_until_exit(*args, **kwargs):
    app = Application()
    app.run_until_exit(*args, **kwargs)

class EventType(enum.Enum):
    KEY_PRESS = 1
    APP_EXIT = 2 # Takes no payload

class Application:
    def __init__(self, loop=None):
        # Initialise event loop
        if loop is None:
            loop = asyncio.get_event_loop()
        self.loop = loop

        # A future which is satisfied when the app should exit
        self._exit_future = loop.create_future()

        # A thread-safe queue whereby events of interest are passed to the app
        self._event_queue = janus.Queue(loop=loop)

    def exit(self):
        """Schedule application exit."""
        self._exit_future.set_result(True)

    def _curses_event_loop(self, screen):
        # Keep reading characters from the keyboard until we exit. Passed
        # the curses screen.

        # Raw mode & allow 100 millisecond timeout
        curses.raw()
        screen.timeout(100)

        while not self._exit_future.done():
            try:
                ch = screen.get_wch()
            except:
                # No input
                continue

            event = curses_key_to_event(ch)
            if event is not None:
                self._event_queue.sync_q.put_nowait(event)

    @asyncio.coroutine
    def _event_loop(self, event_cb):
        """Keep reading events from queue and passing them to event_cb."""
        while True:
            try:
                type_, kwargs = yield from self._event_queue.async_q.get()
            except CancelledError:
                return
            event_cb(self, type_, **kwargs)

    def run_until_exit(self, started_cb=None, event_cb=None):
        """Run the application to completion."""

        # Function wrapped with curses.wrapper.
        def f(screen):
            # Schedule curses event loop
            self.loop.run_in_executor(None, self._curses_event_loop, screen)

            # Schedule start callback if present
            if started_cb:
                self.loop.call_soon(lambda: started_cb(self))

            # Schedule event loop
            if event_cb is not None:
                event_loop_task = self.loop.create_task(
                    self._event_loop(event_cb))
            else:
                event_loop_task = None

            # Wait until exit is signalled
            self.loop.run_until_complete(self._exit_future)
            if event_loop_task is not None:
                event_loop_task.cancel()
                self.loop.run_until_complete(event_loop_task)

        curses.wrapper(f)

def curses_key_to_event(key):
    if isinstance(key, int):
        return None
    return EventType.KEY_PRESS, { 'key': key }
