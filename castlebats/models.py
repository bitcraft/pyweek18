import logging
import pymunk

logger = logging.getLogger(__name__)


class BasicModel:
    """
    * Models can track body and may have multiple sprites.
    * Models are not drawn, but can be thought of as
      containers for ShapeSprites and manage pymunk object references.
    * Models should implement high-level functions for groups
      of related shapes/bodies/joints
    """
    def __init__(self):
        self.space = None
        self.alive = True
        self._pymunk_objects = set()
        self._named_references = set()
        self.sprites = set()
        # connections are joints and motors, or
        # anything else that connects bodies/shapes
        self.connections = set()

    def __del__(self):
        logger.info("garbage collecting %s", self)

    def gather_pymunk_objects(self):
        for pymunk_object, others in self.connections:
            yield pymunk_object
            for other in others:
                yield other

        for thing in self._pymunk_objects:
            yield thing

    def connect_to_space(self, space):
        self.space = space
        for thing in self.gather_pymunk_objects():
            try:
                space.add(thing)
            except AssertionError:
                pass

    def remove_from_space(self):
        for sprite in self.sprites:
            sprite.kill()

        for thing in set(self.gather_pymunk_objects()):
            try:
                self.space.remove(thing)
            except KeyError:
                pass

    def attach_sprite(self, sprite, name=None):
        self.sprites.add(sprite)
        self.attach_thing(sprite.shape)
        self.attach_thing(sprite.shape.body)
        if name:
            self._named_references.add(name)
            setattr(self, name, sprite)

    def attach_thing(self, body, name=None):
        self._pymunk_objects.add(body)
        if name:
            self._named_references.add(name)
            setattr(self, name, body)

    def connect_bodies(self, pymunk_object, *others, name=None):
        self.connections.add((pymunk_object, others))
        if name:
            self._named_references.add(name)
            setattr(self, name, pymunk_object)

    def kill(self):
        """
        remove chipmunk stuff here
        make sure to remove any collision handlers as well

        kinda overkill right now
        """
        self.remove_from_space()

        for name in self._named_references:
            delattr(self, name)

        del self._named_references
        del self._pymunk_objects
        del self.sprites

    @property
    def position(self):
        return self.sprite.shape.body.position


import time

class UprightModel(BasicModel):
    """
    object model of upright walking models

    must be subclassed
    """
    RIGHT = 1
    LEFT = -1

    def __init__(self):
        super().__init__()
        self.move_power = 1
        self.jump_power = 1

        # prevent super quick animation changes
        self._debounce_time = 0
        self._grounded = False

        # this should match your spritesheet's normal character facing direction
        self.sprite_direction = self.RIGHT

    def physics_hook(self):
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
        self.feet.position += position

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
