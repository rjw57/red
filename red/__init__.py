import asyncio

from .app import run_until_exit, EventType

class Editor:
    def __init__(self):
        self.app, self.screen = None, None

    def app_started(self, app):
        app.loop.call_later(3, app.exit)

    def app_event(self, app, type_, **kwargs):
        if type_ is EventType.NEW_SCREEN:
            self.screen = kwargs['screen']
            self.redraw()
        elif type_ is EventType.KEY_PRESS:
            print(kwargs.get('key'), ord(kwargs.get('key')))

    def redraw(self):
        if self.screen is None:
            return

        win = self.screen.win

        win.clear()
        win.box()
        win.addstr(1,1,'%s, rows: %s, cols: %s' % (
            self.screen, self.screen.line_count,
            self.screen.column_count))
        win.refresh()

def main():
    editor = Editor()
    run_until_exit(
        started_cb=editor.app_started, event_cb=editor.app_event)
