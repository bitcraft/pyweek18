import threading
import logging
import pyscroll
import pygame
import pymunk
from pymunktmx.shapeloader import load_shapes
from six.moves import range
from pygame.locals import *

from . import playerinput
from . import collisions
from . import ui
from . import resources
from . import hero
from . import zombie
from . import sprite
from . import config
from . import models

logger = logging.getLogger('castlebats.game')


def ignore_gravity(body, gravity, damping, dt):
    gravity.x = 0
    gravity.y = 0
    return None


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
        self.death_reset = 0
        self.running = False
        self.models = set()
        self.hero = None
        self.spawn_zombie = 0
        self.models_lock = threading.Lock()
        self.hud_group = pygame.sprite.Group()
        self._add_queue = set()
        self._remove_queue = set()
        self.draw_background = config.getboolean('display', 'draw-background')
        self.bg = resources.images['default-bg']

        self.keyboard_input = playerinput.KeyboardPlayerInput()

        self.tmx_data = resources.maps['level0']
        self.map_data = pyscroll.TiledMapData(self.tmx_data)
        self.map_height = self.map_data.height * self.map_data.tileheight

        # manually set all objects in the traps layer to trap collision type
        for layer in self.tmx_data.objectgroups:
            if layer.name == 'Traps':
                for index, obj in enumerate(layer):
                    obj.name = 'trap_{}'.format(index)
            elif layer.name == 'Boundaries':
                for index, obj in enumerate(layer):
                    obj.name = 'boundary_{}'.format(index)
            elif layer.name == 'Physics':
                for index, obj in enumerate(layer):
                    pass
            elif layer.name == 'Stairs':
                for index, obj in enumerate(layer):
                    obj.name = 'stairs_{}'.format(index)

        # set up the physics simulation
        self.space = pymunk.Space()
        self.space.gravity = (0, config.getfloat('world', 'gravity'))
        shapes = load_shapes(self.tmx_data, self.space, resources.level_xml)

        # load the vp group and the single vp for level drawing
        self.vpgroup = sprite.ViewPortGroup(self.space, self.map_data)
        self.vp = sprite.ViewPort()
        self.vpgroup.add(self.vp)

        # set collision types for custom objects
        # and add platforms
        for name, shape in shapes.items():
            logger.info("loaded shape: %s", name)
            if name.startswith('trap'):
                shape.collision_type = collisions.trap
            elif name.startswith('boundary'):
                shape.collision_type = collisions.boundary
            elif name.startswith('moving'):
                self.handle_moving_platform(shape)
            elif name.startswith('stairs'):
                self.handle_stairs(shape)

        self.new_hero()

    def handle_stairs(self, shape):
        logger.info('loading stairs %s', shape)

        shape.layers = 2
        shape.collision_type = collisions.stairs

    def handle_moving_platform(self, shape):
        logger.info('loading moving platform %s', shape)

        assert(not shape.body.is_static)

        shape.layers = 3
        shape.collision_type = 0
        shape.body.velocity_func = ignore_gravity
        shape.body.moment = pymunk.inf

        shape.cache_bb()
        bb = shape.bb
        rect = pygame.Rect((bb.left, bb.top,
                            bb.right - bb.left, bb.top - bb.bottom))
        rect.normalize()

        height = 100
        anchor1 = shape.body.position
        anchor2 = shape.body.position - (0, height)

        joint = pymunk.GrooveJoint(self.space.static_body, shape.body,
                                   anchor1, anchor2, (0, 0))

        spring = pymunk.DampedSpring(self.space.static_body, shape.body,
                                     anchor2, (0, 0), height, 10000, 50)

        self.space.add(joint, spring)

        gids = [self.tmx_data.map_gid(i)[0][0] for i in (1, 2, 3)]
        colorkey = (255, 0, 255)
        tile_width = self.tmx_data.tilewidth

        s = pygame.Surface((rect.width, rect.height))
        s.set_colorkey(colorkey)
        s.fill(colorkey)

        tile = self.tmx_data.getTileImageByGid(gids[0])
        s.blit(tile, (0, 0))
        tile = self.tmx_data.getTileImageByGid(gids[1])
        for x in range(0, rect.width - tile_width, tile_width):
            s.blit(tile, (x, 0))
        tile = self.tmx_data.getTileImageByGid(gids[2])
        s.blit(tile, (rect.width - tile_width, 0))

        spr = sprite.BoxSprite(shape)
        spr.original_surface = s
        m = models.Basic()
        m.sprite = spr

        self.add_model(m)

    def new_hero(self):
        typed_objects = [obj for obj in self.tmx_data.getObjects()
                         if obj.type is not None]

        # find the hero and position her
        hero_coords = None
        for obj in typed_objects:
            if obj.type.lower() == 'hero':
                hero_coords = self.translate((obj.x, obj.y))

        self.keyboard_input.reset()
        self.hero = hero.build(self.space)
        self.hero.position = hero_coords
        self.add_model(self.hero)
        self.vp.follow(self.hero.sprite)
        self.spawn_zombie = False
        resources.sounds['hero-spawn'].play()

    def spawn_enemy(self, name):
        if not self.hero:
            return

        hero_position = self.hero.position

        if name == 'zombie':
            zomb = zombie.build(self.space)
            zomb.position = hero_position + (300, 0)
            self.add_model(zomb)

    def translate(self, coords):
        return pymunk.Vec2d(coords[0], self.map_height - coords[1])

    def enter(self):
        self.running = True
        resources.play_music('dungeon')

    def exit(self):
        self.running = False
        pygame.mixer.music.stop()

    def add_model(self, model):
        if self.models_lock.acquire(False):
            self.models.add(model)
            for spr in model.sprites:
                self.vpgroup.add(spr)
            self.models_lock.release()
        else:
            self._add_queue.add(model)

    def remove_model(self, model):
        if self.models_lock.acquire(False):
            self.models.remove(model)
            for spr in model.sprites:
                self.vpgroup.remove(spr)
            if model is self.hero:
                self.hero = None
                self.death_reset = self.time
            model.kill()
            self.models_lock.release()
        else:
            self._remove_queue.add(model)

    def draw(self, surface, rect):
        # draw the background
        surface.set_clip(rect)
        if self.draw_background:
            left, top = rect.topleft
            top -= 60
            surface.blit(self.bg, (left, top))
            surface.blit(self.bg, (self.bg.get_width(), top))
        else:
            surface.fill((0, 0, 0))
        surface.set_clip(None)

        # draw the world
        self.vpgroup.draw(surface, rect)

        return rect

    def handle_input(self):
        pressed = pygame.key.get_pressed()

        for event in pygame.event.get():
            if event.type == QUIT:
                self.running = False
                break

            elif event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    self.running = False
                    break

            if self.hero:
                cmd = self.keyboard_input.get_command(event)
                if cmd is not None:
                    self.hero.process(cmd)

        if self.hero:
            for cmd in self.keyboard_input.get_held():
                self.hero.process(cmd)

    def update(self, dt):
        seconds = dt / 1000.
        self.time += seconds

        step_amt = seconds / 3.
        step = self.space.step
        step(step_amt)
        step(step_amt)
        step(step_amt)

        if self.time - self.death_reset >= 5 and not self.hero:
            self.new_hero()

        int_time = int(self.time)
        if int_time % 3 == 0 and self.spawn_zombie == 0:
            self.spawn_zombie = 1
        elif int_time % 3 == 1:
            self.spawn_zombie = 0

        if self.spawn_zombie == 1:
            self.spawn_enemy('zombie')
            self.spawn_zombie = 2

        self.vpgroup.update(dt)

        with self.models_lock:
            for model in self.models:
                if model.alive:
                    model.update(dt)

                # do not add else here
                if not model.alive:
                    self.remove_model(model)

        for model in self._remove_queue:
            self.remove_model(model)

        for model in self._add_queue:
            self.add_model(model)

        self._remove_queue = set()
        self._add_queue = set()
