__author__ = 'Leif'

import pymunk
import logging
import time

logger = logging.getLogger('castlebats.model')


class Basic(object):
    """
    basic model with one shape
    """
    def __init__(self):
        self.sprite = None
        self.alive = True
        
    def __del__(self):
        logger.info("garbage collecting %s", self)

    @property
    def sprites(self):
        """ stuff that gets rendered """
        return [self.sprite]

    @property
    def position(self):
        return self.sprite.shape.body.position
    
    def kill(self):
        self.sprite.kill()
        del self.sprite

    def update(self, dt):
        pass


class UprightModel(Basic):
    """
    object model of upright walking models

    must be subclassed
    """
    RIGHT = 1
    LEFT = -1

    def __init__(self):
        super(UprightModel, self).__init__()
        self.feet = None
        self.motor = None
        self.joint = None
        self.move_power = 1
        self.jump_power = 1

        # prevent super quick animation changes
        self._debounce_time = 0
        self._grounded = False

        # this should match your spritesheet's normal character facing direction
        self.sprite_direction = self.RIGHT

    def kill(self):
        """
        remove chipmunk stuff here

        make sure to remove any collision handlers as well
        """
        space = self.sprite.shape.body._space
        space.remove(self.joint, self.motor)
        self.feet.kill()
        del self._next_animation
        del self.feet
        del self.motor
        del self.joint
        super(UprightModel, self).kill()

    def update(self, dt):
        now = time.time()
        if now - self._debounce_time > .05:
            self._debounce_time = now
            if self._grounded:
                if 'jumping' in self.sprite.state:
                    self.sprite.state.remove('jumping')
                    self.sprite.change_state()
                    self._debounce_time = time.time()
            else:
                if 'jumping' not in self.sprite.state:
                    self.sprite.change_state('jumping')

    @property
    def grounded(self):
        return self._grounded

    @grounded.setter
    def grounded(self, value):
        value = bool(value)
        self._grounded = value

    @property
    def position(self):
        return self.sprite.shape.body.position

    @position.setter
    def position(self, value):
        position = pymunk.Vec2d(value)
        self.sprite.shape.body.position += position
        self.feet.shape.body.position += position

    def accelerate(self, direction):
        this_direction = None
        if direction > 0:
            this_direction = self.RIGHT
        if direction < 0:
            this_direction = self.LEFT

        if not this_direction == self.sprite_direction:
            self.sprite.flip = this_direction == self.LEFT
            self.sprite_direction = this_direction

        amt = direction * self.move_power
        self.motor.max_force = pymunk.inf
        self.motor.rate = amt

    def brake(self):
        self.motor.rate = 0
        self.motor.max_force = pymunk.inf

    def jump(self, mod=1.0):
        impulse = (0, self.jump_power * mod)
        self.sprite.shape.body.apply_impulse(impulse)
