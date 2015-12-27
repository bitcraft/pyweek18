import logging

import pygame
from castlebats import scheduler
from castlebats import state_manager
from . import ui

logger = logging.getLogger(__name__)


class Game:
    def __init__(self):
        self.score = 0
        self.lives = 0
        self.health = 0
        self.magic = 0
        self.time = 0
        self.item = None

    def run(self):
        screen = pygame.display.get_surface()
        screen_size = screen.get_size()
        surface = pygame.Surface([int(i / 2) for i in screen_size])
        scale = pygame.transform.scale
        flip = pygame.display.flip

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

        # do not remove!
        import castlebats.level_state
        import castlebats.pause_state

        state_manager.push_state("Level")
        # state_manager.push_state("Pause")

        running = True
        try:
            while running:
                dt = scheduler.tick()

                state = state_manager.current_state

                if state is None:
                    running = False
                    break

                state.update(dt)
                state.draw(surface, level_rect)

                hud_group.draw(surface)
                scale(surface, screen_size, screen)

                flip()

        except KeyboardInterrupt:
            running = False
