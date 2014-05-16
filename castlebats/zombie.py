import itertools
import pygame
import pymunk
from . import models
from . import collisions
from . import config
from .sprite import CastleBatsSprite, make_body, make_feet
import logging

logger = logging.getLogger('castlebats.zombie')


class Model(models.UprightModel):
    """
    ZOMBIE

    generic bad guy will just move left or right until it goes off screen
    """
    RIGHT = 1
    LEFT = -1

    def __init__(self):
        super(Model, self).__init__()
        self.sensor = None
        self.move_power = config.getint('zombie', 'move')
        self.jump_power = config.getint('zombie', 'jump')
        self.body_direction = self.LEFT

    def kill(self):
        space = self.body.shape.body._space
        space.remove(self.sensor)
        super(Model, self).kill()

    # def on_collision(self, space, arbiter):
    #     shape0, shape1 = arbiter.shapes
    #     if shape0.collision_type == collisions.geometry:
    #         self.grounded = True
    #     return 1  # required otherwise ctypes will spam stderr

    def update(self, dt):
        if self.motor.rate == 0:
            self.accelerate(self.body_direction)


class Sprite(CastleBatsSprite):
    sprite_sheet = 'zombie-spritesheet'
    name = 'zombie'
    """ animation def:
        (animation name, ((frame duration, (x, y, w, h, x offset, y offset)...)
    """
    image_animations = [
        ('idle',    100, ((27,  0, 28, 48, 0, 2), )),
        ('walking', 180, ((27,  0, 28, 48, 0, 2),
                          (55,  0, 28, 48, 0, 2),
                          (82,  0, 28, 48, 0, 2),
                          (108, 0, 28, 48, 0, 2))),
    ]

    def __init__(self, shape):
        super(Sprite, self).__init__(shape)
        self.load_animations()
        self.change_state('idle')

    def change_state(self, state=None):
        if state:
            self.state.append(state)

        if 'walking' in self.state:
            self.set_animation('walking', itertools.cycle)


def build(space):
    logger.info('building zombie model')

    model = Model()

    # build body
    layers = 1
    body_rect = pygame.Rect(0, 0, 32, 47)
    body_body, body_shape = make_body(body_rect)
    body_shape.elasticity = 0
    body_shape.layers = layers
    body_shape.friction = 1
    body_sprite = Sprite(body_shape)
    space.add(body_body, body_shape)

    # build feet
    layers = 2
    feet_body, feet_shape = make_feet(body_rect)
    feet_shape.elasticity = 0
    feet_shape.layers = layers
    feet_shape.friction = pymunk.inf
    feet_sprite = CastleBatsSprite(feet_shape)
    space.add(feet_body, feet_shape)

    # jump/collision sensor
    size = body_rect.width, body_rect.height * 1.05
    offset = 0, -body_rect.height * .05
    sensor = pymunk.Poly.create_box(body_body, size, offset)
    sensor.collision_type = collisions.enemy
    sensor.sensor = True
    sensor.actor = model
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
    model.body = body_sprite
    model.feet = feet_sprite
    model.motor = motor
    model.joint = joint
    model.sensor = sensor

    return model