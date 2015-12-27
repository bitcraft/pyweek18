import configparser

# this must be imported before other imports
config = configparser.ConfigParser()


__version__ = (0, 0, 1)


# Singletons
from .lib2.clock import Scheduler
from .lib2.state import StateManager

scheduler = Scheduler()
state_manager = StateManager()
