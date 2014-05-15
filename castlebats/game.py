import threading

import pyscroll
import pygame
import pymunk
from pymunktmx.shapeloader import load_shapes
from pygame.locals import *

import logging
logger = logging.getLogger('castlebats.game')

from . import collisions
from . import ui
from . import resources
from . import hero
from . import zombie
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
        s.rect.topleft = (0,0)
        hud_group.add(s)

        state = self.states[0]
        state.enter()

        try:
            while running:
                dt = clock.tick(target_fps)
                dt /= 3.0
                state = self.states[0]
                state.handle_input()
                state.update(dt)
                state.update(dt)
                state.update(dt)
                hud_group.update()
                state.draw(surface, level_rect)
                hud_group.draw(surface)
                scale(surface, screen_size, screen)
                running = state.running
                flip()
                self.score += 1

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
        self.draw_background = config.getboolean('display', 'draw-background')
        self.bg = resources.images['default-bg']

        self.tmx_data = resources.maps['level0']
        self.map_data = pyscroll.TiledMapData(self.tmx_data)
        self.map_height = self.map_data.height * self.map_data.tileheight

        # manually set all objects in the traps layer to trap collision type
        for layer in self.tmx_data.objectgroups:
            if layer.name == 'Traps':
                for index, obj in enumerate(layer):
                    obj.name = 'trap_{}'.format(index)

        # set up the physics simulation
        self.space = pymunk.Space()
        self.space.gravity = (0, config.getfloat('world', 'gravity'))
        shapes = load_shapes(self.tmx_data, self.space, resources.level_xml)

        for name, shape in shapes.items():
            logger.info("loaded shape: %s", name)
            if name.startswith('trap'):
                shape.collision_type = collisions.trap

        # load the vp group and the single vp for level drawing
        self.vpgroup = sprite.ViewPortGroup(self.space, self.map_data)
        self.vp = sprite.ViewPort()
        self.vpgroup.add(self.vp)

        typed_objects = [obj for obj in self.tmx_data.getObjects()
                         if obj.type is not None]

        # find the hero and position her
        hero_coords = None
        for obj in typed_objects:
            if obj.type.lower() == 'hero':
                hero_coords = self.translate((obj.x, obj.y))

        self.hero = hero.build(self.space)
        self.hero.position = hero_coords
        self.add_actor(self.hero)
        self.vp.follow(self.hero.feet)

        #zomb = zombie.build(self.space)
        #zomb.position = hero_coords + (200, 0)
        #self.add_actor(zomb)

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

    def draw(self, surface, rect):
        # draw the background
        if self.draw_background:
            surface.blit(self.bg, rect.topleft)
            surface.blit(self.bg, (self.bg.get_width(), rect.top))
        else:
            surface.fill((0, 0, 0))

        # draw the world
        self.vpgroup.draw(surface, rect)

        return rect

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
        seconds = dt / 1000.
        self.time += seconds

        step_amt = seconds / 3.
        step = self.space.step
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


