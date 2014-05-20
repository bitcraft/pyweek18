from castlebats import config
import os

# load configuration
filename = os.path.join('config', 'castlebats.ini')
config.read(filename)

import logging
logger = logging.getLogger('castlebats.run')
logging.basicConfig(
    level=getattr(logging, config.get('general', 'debug-level')),
    format="%(name)s:%(filename)s:%(lineno)d:%(levelname)s: %(message)s")

from castlebats import resources
from castlebats import Game
import pygame

#import pymunkoptions
#pymunkoptions.options["debug"] = False


def check_libs():
    import pytmx
    import pymunktmx
    import pyscroll
    logger.info('pygame version:\t%s', pygame.__version__)
    logger.info('pytmx version:\t%s', pytmx.__version__)
    logger.info('pymunktmx version:\t%s', pymunktmx.__version__)
    logger.info('pyscroll version:\t%s', pyscroll.__version__)

    import pymunk
    logger.info('pymunk version:\t%s', pymunk.__version__)


if __name__ == '__main__':
    # simple wrapper to keep the screen resizeable
    def init_screen(width, height):
        if fullscreen:
            return pygame.display.set_mode((width, height), pygame.FULLSCREEN)
        else:
            return pygame.display.set_mode((width, height), pygame.RESIZABLE)

    check_libs()
    screen_width = config.getint('display', 'width')
    screen_height = config.getint('display', 'height')
    fullscreen = config.getboolean('display', 'fullscreen')
    window_caption = config.get('display', 'window-caption')
    sound_buffer_size = config.getint('sound', 'buffer')
    sound_frequency = config.getint('sound', 'frequency')

    pygame.mixer.init(frequency=sound_frequency, buffer=sound_buffer_size)
    screen = init_screen(screen_width, screen_height)
    pygame.display.set_caption(window_caption)

    pygame.init()

    pygame.font.init()

    screen.fill((0, 0, 0))
    for thing in resources.load():
        pygame.event.get()
        pygame.display.flip()

    game = Game()
    try:
        game.run()
    except:
        pygame.quit()
        raise
