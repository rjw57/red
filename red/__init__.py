import asyncio

from .app import run_until_exit, EventType

class Editor:
    def __init__(self):
        pass

    def app_started(self, app):
        app.loop.call_later(3, app.exit)

    def app_event(self, app, type_, **kwargs):
        print(type_)
        if type_ is EventType.KEY_PRESS:
            print(kwargs.get('key'), ord(kwargs.get('key')))

def main():
    editor = Editor()
    run_until_exit(
        started_cb=editor.app_started, event_cb=editor.app_event)
