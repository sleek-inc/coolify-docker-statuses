from enum import Enum, auto


class ContainerStatus(Enum):
    """Enum representing possible container statuses"""

    UNKNOWN = auto()
    CREATED = auto()
    RUNNING = auto()
    RESTARTING = auto()
    EXITED = auto()
    PAUSED = auto()
    DEAD = auto()
    REMOVING = auto()
