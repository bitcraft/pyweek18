__version__ = (0, 0, 1)

from six.moves import configparser
config = configparser.ConfigParser()
from .game import Game
from . import sprite