import logging
import threading
import pygame
import pymunk
import pyscroll
from pygame.constants import QUIT, KEYDOWN, K_ESCAPE
from pymunktmx import load_shapes

from castlebats import config, resources, playerinput, sprite, collisions, models, hero
from castlebats.lib2.state import State
from castlebats import state_manager

logger = logging.getLogger(__name__)


def ignore_gravity(body, gravity, damping, dt):
    gravity.x = 0
    gravity.y = 0
    return None


def get_shape_rect(shape):
    shape.cache_bb()
    bb = shape.bb
    rect = pygame.Rect((bb.left, bb.top, bb.right - bb.left, bb.top - bb.bottom))
    rect.normalize()
    return rect


class Level(State):
    def __init__(self):
        self.time = 0
        self.death_reset = 0
        self.running = False
        self.hero = None
        self.keyboard_input = playerinput.KeyboardPlayerInput()

        self.models = set()
        self.models_lock = threading.Lock()
        self._add_queue = set()
        self._remove_queue = set()

        self.tmx_data = resources.maps['level0']
        self.map_data = pyscroll.TiledMapData(self.tmx_data)
        self.map_height = self.map_data.map_size[1] * self.map_data.tile_size[1]

        for layer in self.tmx_data.objectgroups:
            # manually set all objects in the traps layer to trap collision type
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
            elif layer.name == 'Hanging':
                for index, obj in enumerate(layer):
                    obj.name = 'hanging_{}'.format(index)

        # set up the physics simulation
        self.space = pymunk.Space()
        self.space.gravity = (0, config.getfloat('world', 'gravity'))

        # load the vp group and the single vp for level drawing
        self.vpgroup = sprite.ViewPortGroup(self.space, self.map_data)
        self.vp = sprite.ViewPort()
        self.vpgroup.add(self.vp)

        # set collision types for custom objects
        # and add platforms
        shapes = load_shapes(self.tmx_data, self.space, resources.level_xml)
        for name, shape in shapes.items():
            print(name, shape.friction)
            shape.friction = 1
            logger.info("loaded shape: %s", name)
            if name.startswith('trap'):
                shape.collision_type = collisions.trap
            elif name.startswith('boundary'):
                shape.collision_type = collisions.boundary
            # elif name.startswith('moving'):
            #     self.handle_moving_platform(shape)
            elif name.startswith('stairs'):
                self.handle_stairs(shape)
            elif name.startswith('hanging'):
                self.handle_hanging(shape)

        self.new_hero()

    def handle_stairs(self, shape):
        logger.info('loading stairs %s', shape)

        shape.layers = 2
        shape.collision_type = collisions.stairs

    def handle_moving_platform(self, shape):
        logger.info('loading moving platform %s', shape)

        space = self.space

        model = models.BasicModel()

        shape.layers = 3
        shape.collision_type = 0
        shape.body.velocity_func = ignore_gravity
        shape.body.moment = pymunk.inf

        model.attach_thing(shape.body)
        model.attach_thing(shape)

        height = 100
        anchor1 = shape.body.position
        anchor2 = shape.body.position - (0, height)

        joint = pymunk.GrooveJoint(space.static_body, shape.body,
                                   anchor1, anchor2, (0, 0))
        model.connect_bodies(joint, space.static_body, shape.body)

        spring = pymunk.DampedSpring(space.static_body, shape.body,
                                     anchor2, (0, 0), height, 10000, 50)
        model.connect_bodies(spring, space.static_body, shape.body)

        gids = [self.tmx_data.map_gid(i)[0][0] for i in (1, 2, 3)]
        colorkey = (255, 0, 255)
        tile_width = self.tmx_data.tilewidth

        rect = get_shape_rect(shape)

        s = pygame.Surface((rect.width, rect.height))
        s.set_colorkey(colorkey)
        s.fill(colorkey)

        tile = self.tmx_data.get_tile_image_by_gid(gids[0])
        s.blit(tile, (0, 0))
        tile = self.tmx_data.get_tile_image_by_gid(gids[1])
        for x in range(0, rect.width - tile_width, tile_width):
            s.blit(tile, (x, 0))
        tile = self.tmx_data.get_tile_image_by_gid(gids[2])
        s.blit(tile, (rect.width - tile_width, 0))

        spr = sprite.BoxSprite(shape)
        spr.original_surface = s

        return model

    def handle_hanging(self, shape):
        logger.info('loading hanging %s', shape)
        # assert(not shape.body.is_static)

        shape.cache_bb()
        bb = shape.bb
        rect = pygame.Rect((bb.left, bb.top,
                            bb.right - bb.left, bb.top - bb.bottom))
        rect.normalize()

        shape.layers = 3
        shape.collision_type = 0
        # shape.body.velocity_func = ignore_gravity
        shape.body.mass = 1
        shape.body.moment = pymunk.moment_for_box(1, rect.width, rect.height)

        anchor1 = shape.body.position - (0, 0)
        joint = pymunk.PivotJoint(self.space.static_body, shape.body, anchor1,
                                  (0, 0))

        self.space.add(joint)

        s = pygame.Surface((rect.width, rect.height))
        s.fill((255, 255, 255))

        spr = sprite.BoxSprite(shape)
        spr.original_surface = resources.images['hanging']
        m = models.BasicModel()
        m.sprite = spr

    def new_hero(self):
        typed_objects = [obj for obj in self.tmx_data.objects
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
        resources.sounds['hero-spawn'].play()

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

    def translate(self, coords):
        return pymunk.Vec2d(coords[0], self.map_height - coords[1])

    def resume(self):
        self.running = True
        resources.play_music('dungeon')

    def shutdown(self):
        self.running = False
        pygame.mixer.music.stop()

    def draw(self, surface, rect):
        self.vpgroup.draw(surface, rect)

    def handle_input(self):
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

    def update(self, seconds):
        self.handle_input()

        self.time += seconds

        step_amt = seconds / 3.
        step = self.space.step
        step(step_amt)
        step(step_amt)
        step(step_amt)

        if self.time - self.death_reset >= 5 and not self.hero:
            self.new_hero()

        with self.models_lock:
            for model in self.models:
                model.physics_hook()

                if not model.alive:
                    self.remove_model(model)

        for model in self._remove_queue:
            self.remove_model(model)

        for model in self._add_queue:
            self.add_model(model)

        self._remove_queue.clear()
        self._add_queue.clear()

        if not self.running:
            state_manager.pop_state()


# add this level to the global state manager
state_manager.register_state(Level)
