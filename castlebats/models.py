__author__ = 'Leif'

import pymunk
import logging
logger = logging.getLogger('castlebats.model')


class UprightModel(object):
    """
    object model of upright walking models

    must be subclassed
    """
    RIGHT = 1
    LEFT = -1

    def __init__(self):
        self.body = None
        self.feet = None
        self.motor = None
        self.joint = None
        self.alive = True
        self.move_power = 1
        self.jump_power = 1

        # this should match your spritesheet's normal character facing direction
        self.body_direction = self.RIGHT

    def __del__(self):
        logger.info("garbage collecting %s", self)

    def kill(self):
        """
        remove chipmunk stuff here

        make sure to remove any collision handlers as well
        """
        space = self.body.shape.body._space
        space.remove(self.joint, self.motor)
        self.body.kill()
        self.feet.kill()
        del self.body
        del self.feet
        del self.motor
        del self.joint

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
        """ stuff that gets rendered """
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
        self.body.state.remove('idle')
        self.body.change_state('walking')

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
        self.body.state.remove('walking')
        self.body.change_state('idle')
        self.motor.rate = 0
        self.motor.max_force = pymunk.inf

    def jump(self):
        impulse = (0, self.jump_power)
        self.body.shape.body.apply_impulse(impulse)

    def update(self, dt):
        # do not update the sprites!
        pass