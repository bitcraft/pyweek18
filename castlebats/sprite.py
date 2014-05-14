from math import degrees
import itertools

from six.moves import zip
from pymunk.vec2d import Vec2d
from collections import OrderedDict
from pygame.transform import rotate, flip
from pymunk.pygame_util import draw as pymunk_draw
import pygame
import pymunk
import pyscroll
import logging

logger = logging.getLogger("castlebats.sprite")

from . import resources


class CastleBatsSprite(pygame.sprite.Sprite):
    animations = {}
    sounds = {}
    loaded = False

    def __init__(self, shape):
        super(CastleBatsSprite, self).__init__()
        self.shape = shape
        self.rect = None
        self.axis = None
        self.image = None
        self.flip = False
        self.state = []
        self.animation_timer = 0
        self.original_surface = None
        self.current_animation = []

    @classmethod
    def load_animations(cls):
        if not cls.loaded:
            cls.loaded = True
            s = resources.images[cls.sprite_sheet]

            for name, ttl, tiles in cls.image_animations:
                frames = []
                for x1, y1, w, h, ax, ay in tiles:
                    axis = pymunk.Vec2d(ax, ay)
                    image = pygame.Surface((w, h))
                    image.blit(s, (0, 0), (x1, y1, w, h))
                    image.set_colorkey(image.get_at((0, 0)))
                    frames.append((image, axis))
                cls.animations[name] = ttl, frames

    @property
    def position(self):
        return self.shape.body.position

    def update_image(self):
        """
        call this before drawing
        """
        image = rotate(self.original_surface, degrees(self.shape.body.angle))
        self.image = image.convert()
        self.rect = image.get_rect()
        self.rect.center = self.shape.body.position

    def update(self, dt):
        if self.animation_timer > 0:
            self.animation_timer -= dt
            if self.animation_timer <= 0:
                try:
                    self.set_frame(next(self.current_animation))
                except StopIteration:
                    self.set_animation('idle')

    def set_frame(self, frame):
        self.animation_timer, frame = frame
        new_surf, axis = frame
        self.axis = pymunk.Vec2d(axis)
        if self.flip:
            w, h = new_surf.get_size()
            new_surf = pygame.transform.flip(new_surf, 1, 0)
            self.axis.y = w - self.axis.y
        self.original_surface = new_surf

    def set_animation(self, name, func=None):
        self.animation_timer, animation = self.animations[name]

        if func:
            if len(animation) == 1:
                animation = func(animation[0])
            else:
                animation = func(animation)

        # on python2 this will cause an infinite loop!
        # unless the six module is used.  :D
        self.current_animation = zip(itertools.repeat(self.animation_timer),
                                     animation)

        self.set_frame(next(self.current_animation))


class ViewPortGroup(pygame.sprite.Group):
    """ viewports can be attached
    """

    def __init__(self, space, map_data):
        super(ViewPortGroup, self).__init__()
        self.space = space
        self.map_data = map_data
        self.viewports = OrderedDict()
        self.rect = None

    def set_rect(self, rect):
        self.rect = rect
        self.resize()

    def resize(self):
        rects = list()
        if len(self.viewports) == 1:
            w, h = self.rect.size
            rects = [
                (0, 0, w, h),
            ]

        elif len(self.viewports) == 2:
            w, h = self.rect.size
            rects = [
                (0, 0, w, h / 2),
                (0, h / 2, w, h / 2),
            ]

        elif len(self.viewports) == 3:
            w, h = self.rect.size
            rects = [
                (0, 0, w, h / 2),
                (0, h / 2, w / 2, h / 2),
                (w / 2, h / 2, w / 2, h / 2),
            ]

        elif len(self.viewports) == 4:
            w = self.rect.width / 2
            h = self.rect.height / 2
            rects = [
                (0, 0, w, h),
                (w, 0, w, h),
                (0, h, w, h),
                (w, h, w, h),
            ]
        else:
            logger.error(
                "too many viewports in the manager. only 4 are allowed.")
            raise ValueError

        for k in self.viewports.keys():
            rect = pygame.Rect(rects.pop())
            k.set_rect(rect)
            self.viewports[k] = rect

    def update(self, delta):
        super(ViewPortGroup, self).update(delta)
        for vp in self.viewports:
            vp.update(delta)

    def draw(self, surface, rect):
        if rect is not self.rect:
            self.set_rect(rect)
        return [vp.draw(surface, r) for vp, r in self.viewports.items()]

    def add_internal(self, sprite):
        if isinstance(sprite, ViewPort):
            self.viewports[sprite] = None
            if self.rect is not None:
                self.resize()
        else:
            super(ViewPortGroup, self).add_internal(sprite)

    def remove_internal(self, sprite):
        if sprite in self.viewports:
            del self.viewports[sprite]
            if self.rect is not None:
                self.resize()
        else:
            super(ViewPortGroup, self).remove_internal(sprite)

    def clear(self):
        """ will not handle this
        """
        raise NotImplementedError


class ViewPort(pygame.sprite.Sprite):
    """ Draws a simulation
    """

    def __init__(self):
        super(ViewPort, self).__init__()
        self.parent = None
        self.rect = None
        self.camera_vector = None
        self.map_layer = None
        self.map_height = None
        self.following = None

        # 0 = normal
        # 1 = wireframe
        # 2 = normal + wireframe overlay
        self.draw_mode = 2
        self.wireframe_surface = None

    def set_rect(self, rect):
        self.rect = rect
        md = self.parent.map_data
        colorkey = (128, 64, 128)
        self.map_layer = pyscroll.BufferedRenderer(
            md, rect.size, colorkey, 2, True)
        self.map_height = md.height * md.tileheight
        self.center()

        if self.draw_mode > 0:
            md = self.parent.map_data
            height = md.height * md.tileheight
            width = md.width * md.width
            self.wireframe_surface = pygame.Surface((width, height))
            self.wireframe_surface.set_colorkey((0, 0, 0))
            self.wireframe_surface.set_alpha(128)

    def add_internal(self, group):
        try:
            assert(isinstance(group, ViewPortGroup))
        except AssertionError:
            raise

        super(ViewPort, self).add_internal(group)
        self.parent = group

    def follow(self, body):
        self.following = body

    def center(self):
        if self.rect is None:
            return

        if self.following:
            v = Vec2d(self.following.position)
            v.y = self.map_height - v.y
            self.camera_vector = v

        if self.camera_vector:
            self.map_layer.center(self.camera_vector)

    def update(self, delta):
        self.center()

    def draw(self, surface, rect):
        if rect is not self.rect:
            self.set_rect(rect)

        dirty = list()

        camera = self.rect.copy()
        camera.center = self.camera_vector
        self.camera_vector.x = camera.centerx
        self.camera_vector.y = camera.centery

        ox, oy = self.rect.topleft
        self.map_layer.draw(surface, self.rect)
        xx = -self.camera_vector.x + self.map_layer.half_width + ox
        yy = -self.camera_vector.y + self.map_layer.half_height + oy

        print self.camera_vector, camera.center

        # deref for speed
        surface_blit = surface.blit
        dirty_append = dirty.append
        camera_collide = camera.colliderect
        map_height = self.map_height
        wf_surface = self.wireframe_surface

        for sprite in self.parent.sprites():

            # handle translation based on sprite sub-class
            if isinstance(sprite, CastleBatsSprite):
                sprite.update_image()
                new_rect = sprite.rect.copy()
                new_rect.y = map_height - new_rect.y - new_rect.height
                if camera_collide(new_rect):
                    new_rect = new_rect.move(xx, yy)
                    dirty_rect = surface_blit(sprite.image, new_rect)
                    dirty_append(dirty_rect)

        if self.draw_mode > 0:
            self.wireframe_surface.set_clip(camera)
            self.wireframe_surface.fill((0, 0, 0))
            pymunk_draw(wf_surface, self.parent.space)
            surface.blit(self.wireframe_surface, (xx, yy))

        # TODO: dirty updates
        return self.rect
