import itertools
import pygame
import pymunk
from . import collisions
from . import config
from . import resources
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
#####################################


class Model(object):
    """
    contains the castlebatssprites (CBS) and responds to controls
    
    CBS contain animations, a simple state machine, and references to the pymunk
    objects that they represent.
    """
    RIGHT = 1
    LEFT = -1

    def __init__(self):
        self.body = None
        self.feet = None
        self.motor = None
        self.joint = None
        self.sword_sensor = None
        self.alive = True

        # this is the normal hitbox
        self.normal_rect = pygame.Rect(0, 0, 32, 40)
        self.normal_feet_offset = (0, .7)

        # this is the hitbox for the crouched state
        self.crouched_rect = pygame.Rect(0, 0, 24, 32)
        self.crouched_feet_offset = (0, 0)

        # position the sword sensor in fron of the model
        self.sword_offset = pymunk.Vec2d(self.normal_rect.width * .80, 0)

        self.move_power = config.getint('hero', 'move')
        self.jump_power = config.getint('hero', 'jump')
        self.body_direction = self.RIGHT

    def __del__(self):
        logger.info("garbage collecting %s", self)

    def kill(self):
        space = self.body.shape.body._space
        self.body.kill()
        self.feet.kill()
        space.remove(self.joint, self.motor, self.sword_sensor)
        for i in (collisions.geometry, collisions.boundary,
                  collisions.trap, collisions.enemy):
            space.remove_collision_handler(collisions.hero, i)

        space.remove_collision_handler(collisions.hero_sword, collisions.enemy)

        del self.body
        del self.feet
        del self.motor
        del self.joint
        del self.sword_sensor

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

        logger.info('hero collision %s, %s, %s, %s, %s, %s',
                    shape0.collision_type,
                    shape1.collision_type,
                    arbiter.elasticity,
                    arbiter.friction,
                    arbiter.is_first_contact,
                    arbiter.total_impulse)

        if shape1.collision_type == collisions.geometry:
            self.grounded = True
            return 1

        elif shape1.collision_type == collisions.trap:
            self.alive = False
            self.body.change_state('die')
            return 0

        elif shape1.collision_type == collisions.enemy:
            self.alive = False
            self.body.change_state('die')
            return 0

        elif shape1.collision_type == collisions.boundary:
            self.alive = False
            return 1

        else:
            return 1

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
            if 'attacking' in self.body.state:
                shape1.actor.alive = False
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
        self.body.state.remove('idle')
        self.body.change_state('crouching')

        pymunk_body = self.body.shape.body
        pymunk_feet = self.body.shape.body
        space = pymunk_body._space

        # force the velocity to 0 to prevent them from sliding
        pymunk_body.reset_forces()
        pymunk_body.velocity = 0, 0
        pymunk_feet.reset_forces()
        pymunk_feet.velocity = 0, 0

        # copy the old body shape
        old_shape = self.body.shape
        new_shape = make_hitbox(pymunk_body, self.crouched_rect)
        new_shape.friction = old_shape.friction
        new_shape.elasticity = old_shape.elasticity
        new_shape.layers = old_shape.layers
        new_shape.collision_type = old_shape.collision_type
        self.body.shape = new_shape

        space.remove(self.joint)
        space.remove(old_shape)
        space.add(new_shape)

        self.joint = None

    def uncrouch(self):
        self.body.state.remove('crouching')
        self.body.change_state('standup')

        pymunk_body = self.body.shape.body
        pymunk_feet = self.feet.shape.body
        space = pymunk_body._space

        # copy the old body shape
        old_shape = self.body.shape
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

        self.body.shape = new_shape
        self.joint = joint

    def accelerate(self, direction):
        self.body.state.remove('idle')
        self.body.change_state('walking')

        this_direction = None
        if direction > 0:
            this_direction = self.RIGHT
            self.sword_sensor.offset = self.sword_offset
        if direction < 0:
            this_direction = self.LEFT
            self.sword_sensor.offset = -self.sword_offset

        if not this_direction == self.body_direction:
            self.body.flip = this_direction == self.LEFT
            self.body_direction = this_direction

        amt = direction * self.move_power
        self.motor.max_force = pymunk.inf
        self.motor.rate = amt

    def brake(self):
        self.body.state.remove('walking')
        self.body.change_state('idle')
        self.motor.rate = 0
        self.motor.max_force = pymunk.inf

    def jump(self):
        impulse = (0, self.jump_power)
        self.body.shape.body.apply_impulse(impulse)

    def attack(self):
        if 'attacking' not in self.body.state:
            self.body.change_state('attacking')

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
                    self.accelerate(self.LEFT)
                elif button == P1_RIGHT:
                    self.accelerate(self.RIGHT)
                elif button == P1_UP and 'jumping' not in body.state:
                    body.change_state('jumping')
                    self.jump()
                elif button == P1_DOWN and 'jumping' not in body.state:
                    self.crouch()
                elif button == P1_ACTION1:
                    self.attack()

        elif 'walking' in body.state:
            if event.type == KEYUP:
                if button == P1_LEFT:
                    self.brake()
                elif button == P1_RIGHT:
                    self.brake()
                elif button == P1_UP and 'jumping' not in body.state:
                    body.change_state('jumping')

            elif event.type == KEYDOWN:
                if button == P1_UP and 'jumping' not in body.state:
                    body.change_state('jumping')
                    self.jump()

        if 'crouching' in body.state:
            if event.type == KEYUP:
                if button == P1_DOWN:
                    self.uncrouch()

        if 'jumping' in body.state:
            if event.type == KEYDOWN:
                if button == P1_ACTION1:
                    self.attack()

        logger.info("hero state %s", body.state)


class Sprite(CastleBatsSprite):
    sprite_sheet = 'hero-spritesheet'
    name = 'hero'
    """ animation def:
        (animation name, ((frame duration, (x, y, w, h, x offset, y offset)...)
    """
    image_animations = [
        ('idle', 100, ((10, 6, 34, 48, 0, 0), )),
        ('crouching', 100, ((247, 22, 34, 35, 0, 0), )),
        ('standup', 50, ((189, 19, 35, 37, 0, 0), )),
        ('jumping', 100, ((128, 62, 47, 49, 0, 0), )),
        ('attacking', 40, ((16, 188, 49, 50, 3, 0),
                           (207, 190, 42, 48, 6, 0),
                           (34, 250, 52, 54, 15, 0),
                           (194, 256, 50, 46, -6, 0))),
        ('walking', 100, ((304, 128, 36, 40, 0, -1),
                          (190, 126, 28, 44, -1, 0),
                          (74, 128, 32, 40, 0, -1),
                          (190, 126, 28, 44, -1, 0))),
        ('hurt', 50, ((307, 4, 50, 50, 0, 0),
                      (365, 4, 50, 50, 0, 0))),
    ]

    def __init__(self, shape):
        super(Sprite, self).__init__(shape)
        self.load_animations()
        self.change_state('idle')

    def change_state(self, state=None):
        if state:
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
    model.body = body_sprite
    model.feet = feet_sprite
    model.joint = joint
    model.motor = motor
    model.sword_sensor = sensor

    for i in (collisions.geometry, collisions.boundary,
              collisions.trap, collisions.enemy):
        space.add_collision_handler(collisions.hero, i, model.on_collision)

    space.add_collision_handler(collisions.hero_sword, collisions.enemy,
                                model.on_sword_collision)

    return model