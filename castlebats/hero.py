import itertools
import pygame
import pymunk
from . import config
from . import resources
from .sprite import CastleBatsSprite
import logging

logger = logging.getLogger('castlebats.sprite')

from pygame.locals import *
from .buttons import *

###   CONFIGURE YOUR KEYS HERE   ###
KEY_MAP = {
    K_LEFT: P1_LEFT,
    K_RIGHT: P1_RIGHT,
    K_UP: P1_UP,
    K_DOWN: P1_DOWN,
    K_q: P1_ACTION1,
    K_w: P1_ACTION2,
}
#####################################


class Model(object):
    RIGHT = 1
    LEFT = -1

    def __init__(self):
        self.body = None
        self.feet = None
        self.motor = None
        self.alive = True
        self.move_power = config.getint('hero', 'move')
        self.jump_power = config.getint('hero', 'jump')
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
        pass

    def handle_input(self, event):
        # big ugly bunch of if statements... poor man's state machine
        try:
            button = KEY_MAP[event.key]
        except (KeyError, AttributeError):
            return

        body = self.body

        if 'idle' in body.state:
            if event.type == KEYDOWN:
                if button == P1_LEFT:
                    body.state.remove('idle')
                    body.change_state('walking')
                    self.accelerate(self.LEFT)
                elif button == P1_RIGHT:
                    body.state.remove('idle')
                    body.change_state('walking')
                    self.accelerate(self.RIGHT)
                elif button == P1_UP and 'jumping' not in body.state:
                    body.change_state('jumping')
                    self.jump()
                elif button == P1_DOWN and 'jumping' not in body.state:
                    body.change_state('ducking')
                elif button == P1_ACTION1 and 'attacking' not in body.state:
                    body.change_state('attacking')

        elif 'walking' in body.state:
            if event.type == KEYUP:
                if button == P1_LEFT:
                    body.state.remove('walking')
                    body.change_state('idle')
                    self.brake()
                elif button == P1_RIGHT:
                    body.state.remove('walking')
                    body.change_state('idle')
                    self.brake()
                elif button == P1_UP and 'jumping' not in body.state:
                    body.change_state('jumping')

            elif event.type == KEYDOWN:
                if button == P1_UP and 'jumping' not in body.state:
                    body.change_state('jumping')
                    self.jump()

        if 'ducking' in body.state:
            if event.type == KEYUP:
                if button == P1_DOWN:
                    body.state.remove('ducking')
                    body.change_state()

        logger.info("hero state %s", body.state)


class Sprite(CastleBatsSprite):
    sprite_sheet = 'hero-spritesheet'
    name = 'hero'
    """ animation def:
        (animation name, ((frame duration, (x, y, w, h, x offset, y offset)...)
    """
    image_animations = [
        ('idle', 100, ((10, 6, 34, 48, 0, 0), )),
        ('ducking', 100, ((248, 22, 23, 34, 0, 0), )),
        ('jumping', 100, ((128, 62, 47, 49, 0, 0), )),
        ('attacking', 40, ((16, 188, 49, 50, 3, 0),
                           (207, 190, 42, 48, 6, 0),
                           (34, 250, 52, 54, 15, 0),
                           (194, 256, 50, 46, -6, 0))),
        ('walking', 120, ((304, 128, 36, 40, 0, -1),
                          (190, 126, 28, 44, -1, 0),
                          (74, 128, 32, 40, 0, -1),
                          (190, 126, 28, 44, -1, 0))),
    ]

    def __init__(self, shape):
        super(Sprite, self).__init__(shape)
        self.load_animations()
        self.change_state('idle')

    def change_state(self, state=None):

        if state:
            self.state.append(state)

        if 'attacking' in self.state:
            resources.sounds['sword'].stop()
            resources.sounds['sword'].play()
            self.set_animation('attacking')
            self.state.remove('attacking')

        elif 'jumping' in self.state:
            self.set_animation('jumping', itertools.repeat)

        elif 'ducking' in self.state:
            self.set_animation('ducking', itertools.repeat)

        elif 'walking' in self.state:
            self.set_animation('walking', itertools.cycle)

        elif 'idle' in self.state:
            self.set_animation('idle', itertools.repeat)


def build(space):
    logger.info('building hero model')

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
    body_rect = pygame.Rect(0, 0, 32, 44)
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

    space.add_collision_handler(0, 1, model.on_collision)

    return model