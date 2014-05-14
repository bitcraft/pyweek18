import threading

import pyscroll
import pygame
import pymunk
from pymunktmx.shapeloader import load_shapes
from pygame.locals import *

from . import ui
from . import resources
from . import hero
from . import sprite
from . import config

COLLISION_LAYERS = [2**i for i in range(32)]


class Game(object):
    def __init__(self):
        self.states = []
        self.states.append(Level())

        self.score = 0
        self.lives = 0
        self.health = 0
        self.magic = 0
        self.item = None
        self.time = 0
        self.hud_group = None

    def run(self):
        clock = pygame.time.Clock()
        screen = pygame.display.get_surface()
        flip = pygame.display.flip
        hud_group = self.hud_group
        running = True
        self.states[0].enter()

        self.hud_group = pygame.sprite.RenderUpdates()

        c = (255, 255, 255)
        bg = (0, 0, 0)
        s = ui.TextSprite(self.score, c, bg)

        try:
            while running:
                td = clock.tick(60)
                state = self.states[0]
                state.handle_input()
                state.update(td)
                state.update(td)
                state.update(td)
                hud_group.update()
                state.draw(screen)
                hud_group.draw(screen)
                running = state.running
                flip()

        except KeyboardInterrupt:
            running = False

        state.exit()


class Level(object):
    def __init__(self):
        self.time = 0
        self.buffer_rect = None
        self.buffer_surface = None
        self.running = False
        self.actors = set()
        self.hero = None
        self.actors_lock = threading.Lock()
        self.hud_group = pygame.sprite.Group()
        self._add_queue = set()
        self._remove_queue = set()

        screen = pygame.display.get_surface()
        sw, sh = screen.get_size()
        self.init_buffer((sw / 2, sh / 2))

        self.tmx_data = resources.maps['level0']
        self.map_data = pyscroll.TiledMapData(self.tmx_data)
        self.bg = resources.images['default-bg']

        self.map_height = self.map_data.height * self.map_data.tileheight

        self.space = pymunk.Space()
        self.space.gravity = (0, config.getfloat('world', 'gravity'))
        shapes = load_shapes(self.tmx_data, self.space, resources.level_xml)

        # load the vp group and the single vp for level drawing
        self.vpgroup = sprite.ViewPortGroup(self.space, self.map_data)
        self.vp = sprite.ViewPort()
        self.vpgroup.add(self.vp)

        typed_objects = [obj for obj in self.tmx_data.getObjects()
                         if obj.type is not None]

        hero_coords = None
        for obj in typed_objects:
            if obj.type.lower() == "hero":
                hero_coords = self.translate((obj.x, obj.y))

        self.hero = hero.build(self.space)
        self.hero.position = hero_coords
        self.add_actor(self.hero)
        self.vp.follow(self.hero.feet)

    def translate(self, coords):
        return pymunk.Vec2d(coords[0], self.map_height - coords[1])

    def enter(self):
        self.running = True
        resources.play_music('dungeon')

    def exit(self):
        self.running = False
        pygame.mixer.music.stop()

    def add_actor(self, actor):
        if self.actors_lock.acquire(False):
            self.actors.add(actor)
            for spr in actor.sprites:
                self.vpgroup.add(spr)
            self.actors_lock.release()
        else:
            self._add_queue.add(actor)

    def remove_actor(self, actor):
        if self.actors_lock.acquire(False):
            self.actors.remove(actor)
            for spr in actor.sprites:
                self.vpgroup.remove(spr)
            self.actors_lock.release()
        else:
            self._remove_queue.add(actor)

    def init_buffer(self, size):
        self.buffer_surface = pygame.Surface(size)
        self.buffer_rect = self.buffer_surface.get_rect()

    def draw(self, surface):
        buffer_surface = self.buffer_surface

        # draw the background
        buffer_surface.blit(self.bg, (0, 0))
        buffer_surface.blit(self.bg, (self.bg.get_width(), 0))

        # draw the world and hud
        self.vpgroup.draw(buffer_surface, self.buffer_rect)
        self.hud_group.draw(buffer_surface)

        # scale everything up for a nice pixelated look
        pygame.transform.scale(buffer_surface, surface.get_size(), surface)

        return surface.get_rect()

    def handle_input(self):
        for event in pygame.event.get():
            if event.type == QUIT:
                self.running = False
                break

            elif event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    self.running = False
                    break

            self.hero.handle_input(event)

    def update(self, dt):
        self.time += dt

        step_amt = dt / 3000.
        step = self.space.step
        step(step_amt)
        step(step_amt)
        step(step_amt)
        step(step_amt)
        step(step_amt)
        step(step_amt)
        step(step_amt)
        step(step_amt)
        step(step_amt)
        step(step_amt)

        self.vpgroup.update(dt)

        with self.actors_lock:
            for actor in self.actors:
                if actor.alive:
                    actor.update(dt)

                #if actor.body.bbox.bottom > 1800:
                #    actor.alive = False

                # do not add else here
                if not actor.alive:
                    self.remove_actor(actor)
                    #if actor is self.hero:
                    #    self.new_hero()

        for actor in self._remove_queue:
            self.remove_actor(actor)

        for actor in self._add_queue:
            self.add_actor(actor)

        self._remove_queue = set()
        self._add_queue = set()


