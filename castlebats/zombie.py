import itertools
import pygame
import pymunk
from . import config
from .sprite import CastleBatsSprite
import logging

logger = logging.getLogger('castlebats.zombie')


class Model(object):
    """
    ZOMBIE

    generic bad guy will just move left or right until it goes off screen
    """
    RIGHT = 1
    LEFT = -1

    def __init__(self):
        self.body = None
        self.feet = None
        self.motor = None
        self.alive = True
        self.move_power = config.getint('zombie', 'move')
        self.jump_power = config.getint('zombie', 'jump')
        self.body_direction = self.RIGHT

    @property
    def grounded(self):
        return 'jumping' in self.body.state

    @grounded.setter
    def grounded(self, value):
        if value:
            if 'jumping' in self.body.state:
                self.body.state.remove('jumping')
                self.body.change_state()
        else:
            if 'jumping' not in self.body.state:
                self.body.change_state('jumping')

    @property
    def sprites(self):
        return [self.body]

    @property
    def position(self):
        return self.feet.shape.body.position

    @position.setter
    def position(self, value):
        position = pymunk.Vec2d(value)
        self.body.shape.body.position += position
        self.feet.shape.body.position += position

    def on_collision(self, space, arbiter):
        shape0, shape1 = arbiter.shapes
        if shape0.collision_type == 0:
            self.grounded = True
        return 1  # required otherwise ctypes will spam stderr

    def accelerate(self, direction):
        this_direction = None
        if direction > 0:
            this_direction = self.RIGHT
        if direction < 0:
            this_direction = self.LEFT

        if not this_direction == self.body_direction:
            self.body.flip = this_direction == self.LEFT
            self.body_direction = this_direction

        amt = direction * self.move_power
        self.motor.max_force = pymunk.inf
        self.motor.rate = amt

    def brake(self):
        self.motor.rate = 0
        self.motor.max_force = pymunk.inf

    def jump(self):
        impulse = (0, self.jump_power)
        self.body.shape.body.apply_impulse(impulse)

    def update(self, dt):
        # do not update the sprites!
        if self.motor.rate == 0:
            self.accelerate(self.LEFT)
        pass


class Sprite(CastleBatsSprite):
    sprite_sheet = 'zombie-spritesheet'
    name = 'zombie'
    """ animation def:
        (animation name, ((frame duration, (x, y, w, h, x offset, y offset)...)
    """
    image_animations = [
        ('walking', 180, ((27, 0, 28, 48, 0, 2),
                          (55, 0, 28, 48, 0, 2),
                          (82, 0, 28, 48, 0, 2),
                          (108, 0, 28, 48, 0, 2))),
    ]

    def __init__(self, shape):
        super(Sprite, self).__init__(shape)
        self.load_animations()
        self.change_state('walking')

    def change_state(self, state=None):
        if state:
            self.state.append(state)

        if 'walking' in self.state:
            self.set_animation('walking', itertools.cycle)


def build(space):
    logger.info('building zombie model')

    def make_body(rect):
        mass = 10
        #inertia = pymunk.moment_for_box(mass, rect.width, rect.height)
        inertia = pymunk.inf
        body = pymunk.Body(mass, inertia)
        points = [rect.bottomleft, rect.bottomright, rect.midright,
                  rect.midtop, rect.midleft]
        shape = pymunk.Poly(body, points, (-rect.centerx, -rect.centery))
        return body, shape

    def make_feet(rect):
        mass = 2
        radius = rect.width * .45
        inertia = pymunk.moment_for_circle(mass, 0, radius, (0, 0))
        body = pymunk.Body(mass, inertia)
        shape = pymunk.Circle(body, radius, (0, 0))
        return body, shape

    # build body
    layers = 1
    body_rect = pygame.Rect(0, 0, 32, 47)
    body_body, body_shape = make_body(body_rect)
    body_shape.layers = layers
    body_shape.friction = 1
    body_sprite = Sprite(body_shape)
    space.add(body_body, body_shape)

    # build feet
    layers = 2
    feet_body, feet_shape = make_feet(body_rect)
    feet_shape.collision_type = 1
    feet_shape.layers = layers
    feet_shape.friction = pymunk.inf
    feet_sprite = CastleBatsSprite(feet_shape)
    space.add(feet_body, feet_shape)

    # jump/collision sensor
    layers = 2
    size = body_rect.width, body_rect.height * 1.05
    offset = 0, -body_rect.height * .05
    sensor = pymunk.Poly.create_box(body_body, size, offset)
    sensor.sensor = True
    sensor.layers = layers
    sensor.collision_type = 1
    space.add(sensor)

    # attach feet to body
    feet_body.position = (body_body.position.x,
                          body_body.position.y - feet_shape.radius * .7)

    # motor and joint for feet
    motor = pymunk.SimpleMotor(body_body, feet_body, 0.0)
    joint = pymunk.PivotJoint(
        body_body, feet_body, feet_body.position, (0, 0))
    space.add(motor, joint)

    # the model is used to gameplay logic
    model = Model()
    model.body = body_sprite
    model.feet = feet_sprite
    model.motor = motor

    return model