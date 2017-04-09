import asyncio

from .app import run_until_exit
from .event import EventType

def main():
    run_until_exit(started_cb=started, event_cb=event)

def event(type_, **kwargs):
    print(type_)
    if type_ is EventType.KEY_PRESS:
        print(kwargs.get('key'))

def started(app):
    loop = app.loop
    loop.call_later(2, app.exit)
