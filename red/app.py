"""Full-screen ncurses application support."""
import asyncio
import curses

class Application:
    def __init__(self, loop=None):
        if loop is None:
            loop = asyncio.get_event_loop()
        self.loop = loop

        # A future which is satisfied when the app should exit
        self.exit_future = loop.create_future()

    def exit(self):
        """Schedule application exit."""
        self.exit_future.set_result(True)

    def run(self):
        """Run the application to completion."""
        def wait_exit(screen):
            self.screen = screen
            self.loop.run_until_complete(self.exit_future)
        curses.wrapper(wait_exit)
        self.loop.close()
