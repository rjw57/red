"""UI events."""
import collections
import enum

class EventType(enum.Enum):
    KEY_PRESS = 1
    APP_EXIT = 2 # Takes no payload

Event = collections.namedtuple('Event', 'type kwargs')

