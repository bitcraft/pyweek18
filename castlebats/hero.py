import itertools
import pygame
import pymunk
from . import collisions
from . import config
from . import resources
from . import models
from . import playerinput
from .sprite import CastleBatsSprite
from .sprite import make_body
from .sprite import make_feet
from .sprite import make_hitbox
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

INV_KEY_MAP = {v: k for k, v in KEY_MAP.items()}
#####################################


class Model(models.UprightModel):
    """
    CBS contain animations, a simple state machine, and references to the pymunk
    objects that they represent.
    """
    def __init__(self):
        super(Model, self).__init__()
        self.sword_sensor = None

        self.air_move = 0
        self.air_move_speed = config.getfloat('hero', 'air-move')

        self.on_stairs = False

        # this is the normal hitbox
        self.normal_rect = pygame.Rect(0, 0, 32, 40)
        self.normal_feet_offset = (0, .7)

        # this is the hitbox for the crouched state
        self.crouched_rect = pygame.Rect(0, 0, 24, 32)
        self.crouched_feet_offset = (0, 0)

        # position the sword sensor in fron of the model
        self.sword_offset = pymunk.Vec2d(self.normal_rect.width * .80, 0)

        # detect if player wants to use stairs
        self.wants_stairs = False

        # input fluidity
        self.ignore_buttons = list()

        self.move_power = config.getint('hero', 'move')
        self.jump_power = config.getint('hero', 'jump')
        self.jump_mod = 1.0
        self.sprite_direction = self.RIGHT

    def process(self, cmd):
        # big ugly bunch of if statements... poor man's state machine

        input_class, button, state = cmd
        ignore = self.ignore_buttons.append
        body = self.sprite

        if state == BUTTONUP:
            try:
                self.ignore_buttons.remove(button)
            except ValueError:
                pass
        else:
            if button in self.ignore_buttons:
                return

        if button == P1_UP:
            if state == BUTTONDOWN:
                self.wants_stairs = True
            elif state == BUTTONUP:
                self.wants_stairs = False

        if body.state[-1] == 'idle':
            if state == BUTTONDOWN or state == BUTTONHELD:
                if button == P1_LEFT:
                    body.state.remove('idle')
                    body.change_state('walking')
                    self.accelerate(self.LEFT)
                elif button == P1_RIGHT:
                    body.state.remove('idle')
                    body.change_state('walking')
                    self.accelerate(self.RIGHT)
                elif button == P1_ACTION1:
                    ignore(P1_ACTION1)
                    body.change_state('attacking')

                if self.grounded:
                    if button == P1_ACTION2:
                        ignore(P1_ACTION2)
                        self.jump(self.jump_mod)
                        self.jump_mod = 1.0

                    elif button == P1_DOWN:
                        ignore(P1_DOWN)
                        body.state.remove('idle')
                        body.change_state('crouching')
                        self.crouch()

        elif 'walking' in body.state:
            if self.grounded:
                if state == BUTTONDOWN:
                    if button == P1_ACTION2:
                        ignore(P1_ACTION2)
                        self.jump(self.jump_mod)
                        self.jump_mod = 1.0

            if state == BUTTONUP:
                if button == P1_LEFT or button == P1_RIGHT:
                    body.state.remove('walking')
                    body.change_state('idle')
                    self.brake()

        elif 'crouching' in body.state:
            if state == BUTTONHELD:
                if button == P1_ACTION2:
                    self.jump_mod = 1.6

            elif state == BUTTONUP:
                if button == P1_DOWN:
                    body.state.remove('crouching')
                    body.change_state('standup')
                    self.uncrouch()

                elif button == P1_ACTION2:
                    self.jump_mod = 1.0

        elif not self.grounded:
            if state == BUTTONDOWN:
                if button == P1_ACTION1:
                    ignore(P1_DOWN)
                    body.change_state('attacking')

            self.air_move = 0
            if state == BUTTONDOWN or state == BUTTONHELD:
                if button == P1_LEFT:
                    self.air_move = self.LEFT
                elif button == P1_RIGHT:
                    self.air_move = self.RIGHT

        logger.info("hero state %s", body.state)

    def kill(self):
        space = self.sprite.shape.body._space
        space.remove(self.sword_sensor)
        for i in (collisions.geometry, collisions.boundary,
                  collisions.trap, collisions.enemy,
                  collisions.stairs):
            space.remove_collision_handler(collisions.hero, i)
        space.remove_collision_handler(collisions.hero_sword, collisions.enemy)
        del self.sword_sensor

        super(Model, self).kill()

    def on_collision(self, space, arbiter):
        shape0, shape1 = arbiter.shapes

        logger.info('hero collision %s, %s, %s, %s, %s, %s',
                    shape0.collision_type,
                    shape1.collision_type,
                    arbiter.elasticity,
                    arbiter.friction,
                    arbiter.is_first_contact,
                    arbiter.total_impulse)

        if shape1.collision_type == collisions.trap:
            self.alive = False
            self.sprite.change_state('die')
            return False

        elif shape1.collision_type == collisions.enemy:
            self.alive = False
            self.sprite.change_state('die')
            return False

        elif shape1.collision_type == collisions.boundary:
            self.alive = False
            return False

        else:
            return True

    def on_stairs_begin(self, space, arbiter):
        shape0, shape1 = arbiter.shapes

        logger.info('stairs begin %s, %s, %s, %s, %s, %s',
                    shape0.collision_type,
                    shape1.collision_type,
                    arbiter.elasticity,
                    arbiter.friction,
                    arbiter.is_first_contact,
                    arbiter.total_impulse)

        if self.wants_stairs:
            c = arbiter.contacts
            shape1.collision_type = collisions.geometry
            self.on_stairs = shape1
            return True
        else:
            return False

    def on_stairs_separate(self, space, arbiter):
        shape0, shape1 = arbiter.shapes

        logger.info('stairs seperate %s, %s, %s, %s, %s, %s',
                    shape0.collision_type,
                    shape1.collision_type,
                    arbiter.elasticity,
                    arbiter.friction,
                    arbiter.is_first_contact,
                    arbiter.total_impulse)

        return False

    def drop_from_stairs(self):
        self.on_stairs.collision_type = collisions.stairs
        self.on_stairs = None

    def on_grounded(self, space, arbiter):
        self.air_move = 0
        self.grounded = True
        return True

    def on_ungrounded(self, space, arbiter):
        self.air_move = 0
        self.grounded = False
        if self.on_stairs:
            self.drop_from_stairs()
        return True

    def on_sword_collision(self, space, arbiter):
        shape0, shape1 = arbiter.shapes

        logger.info('sword collision %s, %s, %s, %s, %s, %s',
                    shape0.collision_type,
                    shape1.collision_type,
                    arbiter.elasticity,
                    arbiter.friction,
                    arbiter.is_first_contact,
                    arbiter.total_impulse)

        if shape1.collision_type == collisions.enemy:
            if 'attacking' in self.sprite.state:
                shape1.model.alive = False
            return 0

    @staticmethod
    def normal_feet_position(position, feet_shape):
        return (position.x,
                position.y - feet_shape.radius * .7)

    @staticmethod
    def crouched_feet_position(position, feet_shape):
        return (position.x,
                position.y + feet_shape.radius * 1.5)

    def crouch(self):
        pymunk_body = self.sprite.shape.body
        pymunk_feet = self.sprite.shape.body
        space = pymunk_body._space

        # force the velocity to 0 to prevent them from sliding
        pymunk_body.reset_forces()
        pymunk_body.velocity = 0, 0
        pymunk_feet.reset_forces()
        pymunk_feet.velocity = 0, 0

        # copy the old body shape
        old_shape = self.sprite.shape
        new_shape = make_hitbox(pymunk_body, self.crouched_rect)
        new_shape.friction = old_shape.friction
        new_shape.elasticity = old_shape.elasticity
        new_shape.layers = old_shape.layers
        new_shape.collision_type = old_shape.collision_type
        self.sprite.shape = new_shape

        space.remove(self.joint)
        space.remove(old_shape)
        space.add(new_shape)

        self.joint = None

        if self.on_stairs:
            self.drop_from_stairs()

    def uncrouch(self):
        pymunk_body = self.sprite.shape.body
        pymunk_feet = self.feet.shape.body
        space = pymunk_body._space

        # copy the old body shape
        old_shape = self.sprite.shape
        new_shape = make_hitbox(pymunk_body, self.normal_rect)
        new_shape.friction = old_shape.friction
        new_shape.elasticity = old_shape.elasticity
        new_shape.layers = old_shape.layers
        new_shape.collision_type = old_shape.collision_type

        # move bodies to unused part of map
        # rebuild the shape
        # place back in the same place
        old_position = pymunk.Vec2d(pymunk_feet.position)
        pymunk_body.position = 0, 0

        # set the feet to the right spot
        pymunk_feet.position = self.normal_feet_position(
            pymunk_body.position,
            self.feet.shape
        )

        diff = pymunk.Vec2d(pymunk_feet.position)

        # pin them together again
        joint = pymunk.PivotJoint(
            pymunk_body, pymunk_feet, pymunk_feet.position, (0, 0))

        # put back in old position
        pymunk_feet.position = old_position
        pymunk_body.position = pymunk_feet.position - diff

        space.remove(old_shape)
        space.add(new_shape)
        space.add(joint)

        self.sprite.shape = new_shape
        self.joint = joint

    def update(self, dt):
        super(Model, self).update(dt)
        if not self.air_move == 0:
            vel_x = self.air_move * self.air_move_speed
            if abs(self.sprite.shape.body.velocity.x) < abs(vel_x):
                self.sprite.shape.body.velocity.x = vel_x

    def accelerate(self, direction):
        super(Model, self).accelerate(direction)
        if direction > 0:
            self.sword_sensor.offset = self.sword_offset
        if direction < 0:
            self.sword_sensor.offset = -self.sword_offset

    def attack(self):
        pass


class Sprite(CastleBatsSprite):
    sprite_sheet = 'hero-spritesheet'
    name = 'hero'
    """ animation def:
        (animation name, ((frame duration, (x, y, w, h, x offset, y offset)...)
    """
    image_animations = [
        ('idle',      100, ((10,    6, 34, 48,  0,  0), )),
        ('crouching', 100, ((247,  22, 34, 35,  0,  0), )),
        ('standup',    50, ((189,  19, 35, 37,  0,  0), )),
        ('jumping',   100, ((128,  62, 47, 49,  0,  0), )),
        ('attacking',  40, ((16,  188, 49, 50,  3,  0),
                           (207,  190, 42, 48,  6,  0),
                           (34,   250, 52, 54, 15,  0),
                           (194,  256, 50, 46, -6,  0))),
        ('walking',   100, ((304, 128, 36, 40,  0, -1),
                            (190, 126, 28, 44, -1,  0),
                            (74,  128, 32, 40,  0, -1),
                            (190, 126, 28, 44, -1,  0))),
        ('hurt',       50, ((307,   4, 50, 50,  0,  0),
                            (365,   4, 50, 50,  0,  0))),
    ]

    def __init__(self, shape):
        super(Sprite, self).__init__(shape)
        self.load_animations()
        self.change_state('idle')

    def change_state(self, state=None):
        if state:
            self.old_state = self.state[:]
            if self.state == ['idle']:
                self.state = [state]
            else:
                self.state.append(state)

        if not self.state:
            self.state = ['idle']

        if 'hurt' in self.state:
            resources.sounds['hurt'].stop()
            resources.sounds['hurt'].play()
            self.set_animation('hurt')
            self.state.remove('hurt')

        elif 'die' in self.state:
            #resources.sounds['hero-death'].play()
            self.set_animation('hurt')
            self.state.remove('die')

        elif 'standup' in self.state:
            self.set_animation('standup')

        elif 'attacking' in self.state:
            resources.sounds['sword'].stop()
            resources.sounds['sword'].play()
            self.set_animation('attacking')

        elif 'jumping' in self.state:
            self.set_animation('jumping', itertools.repeat)

        elif 'crouching' in self.state:
            self.set_animation('crouching', itertools.repeat)

        elif 'walking' in self.state:
            self.set_animation('walking', itertools.cycle)

        elif 'idle' in self.state:
            self.set_animation('idle', itertools.repeat)


def build(space):
    logger.info('building hero model')

    model = Model()

    # build body
    layers = 1
    body_body, body_shape = make_body(model.normal_rect)
    body_body.collision_type = collisions.hero
    body_shape.elasticity = 0
    body_shape.layers = layers
    body_shape.friction = pymunk.inf
    body_sprite = Sprite(body_shape)
    space.add(body_body, body_shape)

    # build feet
    layers = 2
    feet_body, feet_shape = make_feet(model.normal_rect)
    feet_shape.collision_type = collisions.hero
    feet_shape.elasticity = 0
    feet_shape.layers = layers
    feet_shape.friction = pymunk.inf
    feet_sprite = CastleBatsSprite(feet_shape)
    space.add(feet_body, feet_shape)

    # jump/collision sensor
    #layers = 2
    #size = body_rect.width, body_rect.height * 1.05
    #offset = 0, -body_rect.height * .05
    #sensor = pymunk.Poly.create_box(body_body, size, offset)
    #sensor.sensor = True
    #sensor.layers = layers
    #sensor.collision_type = collisions.hero
    #space.add(sensor)

    # attack sensor
    size = model.normal_rect.width, model.normal_rect.height * .60
    sensor = pymunk.Poly.create_box(body_body, size, model.sword_offset)
    sensor.sensor = True
    sensor.collision_type = collisions.hero_sword
    space.add(sensor)

    # attach feet to body
    feet_body.position = model.normal_feet_position(
        body_body.position,
        feet_shape)

    # motor and joint for feet
    motor = pymunk.SimpleMotor(body_body, feet_body, 0.0)
    joint = pymunk.PivotJoint(
        body_body, feet_body, feet_body.position, (0, 0))
    space.add(motor, joint)

    # the model is used to gameplay logic
    model.sprite = body_sprite
    model.feet = feet_sprite
    model.joint = joint
    model.motor = motor
    model.sword_sensor = sensor

    for i in (collisions.boundary, collisions.trap, collisions.enemy):
        space.add_collision_handler(collisions.hero, i, model.on_collision)

    space.add_collision_handler(collisions.hero, collisions.geometry,
                                post_solve=model.on_grounded,
                                separate=model.on_ungrounded)

    space.add_collision_handler(collisions.hero_sword, collisions.enemy,
                                model.on_sword_collision)

    space.add_collision_handler(collisions.hero, collisions.stairs,
                                begin=model.on_stairs_begin,
                                separate=model.on_stairs_separate)
    return model