import itertools
import pygame
import pymunk
from . import config
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
                elif button == P1_ACTION1:
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


class Sprite(CastleBatsSprite):
    sprite_sheet = 'hero-spritesheet'
    name = 'hero'
    image_animations = [
        ('idle', 100, ((10, 10, 34, 44, 15, 42), )),
        ('attacking', 250, ((34, 254, 52, 52, 15, 48), )),
        ('walking', 300, ((304, 132, 36, 40, 15, 38),
                          (190, 130, 28, 44, 14, 40),
                          (74, 132, 32, 40, 15, 38),
                          (190, 130, 28, 44, 14, 40))),
    ]

    def __init__(self, shape):
        super(Sprite, self).__init__(shape)
        self.load_animations()
        self.change_state('idle')

    def change_state(self, state):
        self.state.append(state)

        if 'attacking' in self.state:
            self.sounds['sword'].stop()
            self.sounds['sword'].play()
            self.set_animation('attacking')
            self.state.remove('attacking')

        elif 'walking' in self.state:
            self.set_animation('walking', itertools.cycle)

        elif 'idle' in self.state:
            self.set_animation('idle', itertools.repeat)


def build(space):
    logger.info('building hero model')
    def make_body(rect):
        mass = 100
        #inertia = pymunk.moment_for_box(mass, rect.width, rect.height)
        inertia = pymunk.inf
        body = pymunk.Body(mass, inertia)
        shape = pymunk.Poly.create_box(body, (rect.width, rect.height))
        return body, shape

    def make_feet(rect):
        mass = 20
        radius = rect.width / 2
        inertia = pymunk.moment_for_circle(mass, 0, radius, (0, 0))
        body = pymunk.Body(mass, inertia)
        shape = pymunk.Circle(body, radius, (0, 0))
        shape.friction = 1
        return body, shape

    # build body
    layers = 0
    body_rect = pygame.Rect(0, 0, 32, 64)
    body_body, body_shape = make_body(body_rect)
    body_shape.layers = layers
    body_sprite = Sprite(body_shape)
    space.add(body_body, body_shape)

    # build feet
    feet_body, feet_shape = make_feet(body_rect)
    feet_shape.layers = layers
    feet_sprite = CastleBatsSprite(feet_shape)
    space.add(feet_body, feet_shape)

    # attach feet to body
    feet_body.position = (body_body.position.x + feet_shape.radius,
                          body_body.position.y - (feet_shape.radius * 1.5))

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