import logging

import pygame
import threading

from . import ui
from . import config
from castlebats.level import Level

logger = logging.getLogger('castlebats.game')


class Game(object):
    def __init__(self):
        self.states = []
        self.states.append(Level())
        self.score = 0
        self.lives = 0
        self.health = 0
        self.magic = 0
        self.time = 0
        self.item = None

    def run(self):
        clock = pygame.time.Clock()
        screen = pygame.display.get_surface()
        screen_size = screen.get_size()
        surface = pygame.Surface([int(i / 2) for i in screen_size])
        scale = pygame.transform.scale
        flip = pygame.display.flip
        target_fps = config.getint('display', 'target-fps')
        running = True

        level_rect = surface.get_rect()
        level_rect.inflate_ip(0, -level_rect.height * .20)
        level_rect.bottom = surface.get_rect().bottom

        hud_group = pygame.sprite.RenderUpdates()

        # add stuff to the hud
        c = (255, 255, 255)
        bg = (0, 0, 0)
        s = ui.TextSprite(self.score, c, bg)
        s.rect.topleft = (0, 0)
        hud_group.add(s)

        state = self.states[0]
        state.enter()

        flip_event = threading.Event()
        update_lock = threading.Lock()

        def flip_in_thread():
            while 1:
                flip_event.wait()
                flip()
                flip_event.clear()

        # draw_thread = threading.Thread(None, flip_in_thread)
        # draw_thread.setDaemon(True)
        # draw_thread.start()
        #
        # import gc
        # gc.disable()

        try:
            while running:
                dt = clock.tick(120)
                # dt = clock.tick()
                state = self.states[0]
                state.handle_input()

                with update_lock:
                    state.update(dt)
                    hud_group.update()
                    state.draw(surface, level_rect)
                    hud_group.draw(surface)
                    scale(surface, screen_size, screen)

                # flip_event.set()
                flip()

                running = state.running
                self.score += 1

        except KeyboardInterrupt:
            running = False

        state.exit()
