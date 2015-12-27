import itertools
import logging
from collections import OrderedDict
from math import degrees

import pygame
import pymunk
import pyscroll
from pygame.transform import rotozoom, rotate, flip
from pymunk.vec2d import Vec2d

from . import resources
from castlebats import scheduler
from castlebats import config

logger = logging.getLogger(__name__)


class ShapeSprite(pygame.sprite.Sprite):
    """
    sprite tracks one pymunk shape and can draw it to a viewport
    """
    animations = {}
    loaded = False

    def __init__(self, shape):
        super().__init__()
        self.shape = shape            # pymunk shape
        self.rect = None              # for screen updates
        self.axis = None              # where sprites are positioned
        self.image = None             # transformed image for drawing
        self.flip = False             # flip left or right
        self.dirty = False            # flag if sprite has changed or not
        self.original_surface = None  # unmodified surface for sprite
        self.state = []
        self.old_state = []
        self.current_animation = []
        self._old_angle = None        # used to check if object needs to be rotated

    def __del__(self):
        logger.info('garbage collecting %s' % self)

    def kill(self):
        """
        remove all the physics stuff from the space
        """
        space = self.shape.body._space
        space.remove(self.shape)
        del self.shape
        del self.original_surface
        del self.state
        del self.old_state
        del self.current_animation
        scheduler.unschedule(self.advance_frame)
        super().kill()

    @classmethod
    def load_animations(cls):
        if not cls.loaded:
            logger.info("loading %s animations", cls)
            cls.animations = dict()
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

    @position.setter
    def position(self, value):
        position = pymunk.Vec2d(value)
        self.shape.body.position += position

    def update_image(self):
        """
        call this before drawing
        rotates the image
        sets the rect to the body position
        """
        angle = degrees(self.shape.body.angle)
        if not angle == self._old_angle or self.dirty:
            image = rotate(self.original_surface, angle)
            self.image = image.convert()
            self.rect = image.get_rect()
            self._old_angle = angle
            self.dirty = False
        self.rect.center = self.shape.body.position

    def set_frame(self, frame):
        animation_timer, frame = frame
        animation_timer /= 1000
        new_surf, axis = frame
        self.axis = pymunk.Vec2d(axis)
        if self.flip:
            w, h = new_surf.get_size()
            new_surf = flip(new_surf, 1, 0)
            self.axis.x = -self.axis.x
        self.original_surface = new_surf
        self.dirty = True
        scheduler.schedule(self.advance_frame, animation_timer)

    def set_animation(self, name, func=None):
        animation_timer, animation = self.animations[name]

        logger.info("%s set animation %s", self, name)

        if func:
            if len(animation) == 1:
                animation = func(animation[0])
            else:
                animation = func(animation)

        scheduler.unschedule(self.advance_frame)
        self.current_animation = zip(itertools.repeat(animation_timer), animation)
        self.advance_frame(None)

    def advance_frame(self, dt):
        try:
            self.set_frame(next(self.current_animation))
        except StopIteration:
            try:
                # remove the old animation
                self.state.pop()
                animation = self.state.pop()
            except IndexError:
                animation = 'idle'
            self.change_state(animation)


class BoxSprite(ShapeSprite):
    """
    im really confused why, but box type object need special translations
    """

    def update_image(self):
        """
        call this before drawing
        rotates the image
        sets the rect to the body position
        """
        angle = degrees(self.shape.body.angle)
        if not angle == self._old_angle or self.dirty:
            self.image = rotozoom(self.original_surface, angle, 1)
            self.rect = self.image.get_rect()
            self._old_angle = angle
            self.dirty = False

        self.shape.cache_bb()
        bb = self.shape.bb
        self.rect.topleft = bb.left, bb.bottom


class ViewPortGroup(pygame.sprite.Group):
    """ viewports can be attached
    """

    def __init__(self, space, map_data):
        super().__init__()
        self.space = space
        self.map_data = map_data
        self.viewports = OrderedDict()
        self.rect = None

    def set_rect(self, rect):
        self.rect = rect
        self.resize()

    def resize(self):
        logger.info("resizing the viewports")
        if len(self.viewports) == 1:
            x, y, w, h = self.rect
            rects = [(x, y, w, h)]

        elif len(self.viewports) == 2:
            x, y, w, h = self.rect
            rects = [(x, y, w, h / 2),
                     (x, h / 2 + y, w, h / 2 + y)]

        else:
            logger.error("too many viewports in the manager. only 2 are allowed.")
            raise ValueError

        for k in self.viewports.keys():
            rect = pygame.Rect(rects.pop())
            k.set_rect(rect)
            self.viewports[k] = rect

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
            super().add_internal(sprite)

    def remove_internal(self, sprite):
        if sprite in self.viewports:
            del self.viewports[sprite]
            if self.rect is not None:
                self.resize()
        else:
            # handle in case the vp is following this sprite
            for vp in self.viewports.keys():
                if vp.following is sprite:
                    vp.follow(None)
            super().remove_internal(sprite)

    def clear(self):
        """ will not handle this
        """
        raise NotImplementedError


class ViewPort(pygame.sprite.Sprite):
    """ Draws a simulation
    """

    def __init__(self):
        super().__init__()
        self.parent = None           # castlebats.Level
        self.rect = None
        self.camera_vector = None
        self.map_layer = None        # pyscroll renderer
        self.map_height = None
        self.following = None

        self.draw_background = config.getboolean('display', 'draw-background')
        self.draw_sprites = config.getboolean('display', 'draw-sprites')
        self.draw_map = config.getboolean('display', 'draw-map')
        self.draw_overlay = config.getboolean('display', 'draw-physics-overlay')
        self.overlay_surface = None

    def set_rect(self, rect):
        logger.info('setting rect')
        md = self.parent.map_data
        self.rect = pygame.Rect(rect)
        self.map_layer = pyscroll.BufferedRenderer(md, self.rect.size, alpha=True)
        self.map_height = md.map_size[1] * md.tile_size[1]
        self.center()

        if self.draw_overlay:
            md = self.parent.map_data
            height = md.map_size[1] * md.tile_size[1]
            width = md.map_size[0] * md.tile_size[0]
            self.overlay_surface = pygame.Surface((width, height))
            self.overlay_surface.set_colorkey((0, 0, 0))
            alpha = config.getint('display', 'physics-overlay-alpha')
            self.overlay_surface.set_alpha(alpha)

    def add_internal(self, group):
        try:
            assert (isinstance(group, ViewPortGroup))
        except AssertionError:
            raise

        super().add_internal(group)
        self.parent = group

    def follow(self, sprite):
        """
        only follow a sprite, not a pymunk shape
        """
        if sprite is None:
            self.following = None
        else:
            assert (isinstance(sprite, ShapeSprite))
            self.following = sprite

    def center(self):
        if self.rect is None:
            return

        if self.following:
            v = Vec2d(self.following.position)
            v.y = self.map_height - v.y
            self.camera_vector = v

        if self.camera_vector:
            self.map_layer.center(self.camera_vector)

    def draw(self, surface, surface_rect):
        if not surface_rect == self.rect:
            self.set_rect(surface_rect)

        self.center()

        camera = self.rect.copy()
        camera.center = self.camera_vector

        xx, yy = -self.camera_vector + surface_rect.center - surface_rect.topleft + (0, 18)

        xx += self.rect.left
        yy += self.rect.top

        to_draw = list()
        if self.draw_sprites:
            to_draw_append = to_draw.append
            camera_collide = camera.colliderect
            map_height = self.map_height

            for sprite in self.parent.sprites():
                if isinstance(sprite, ShapeSprite):
                    sprite.update_image()

                    # ox, oy = self.map_layer.get_center_offset()
                    # new_rect = sprite.rect.move(ox, oy)
                    # new_rect.y = map_height - new_rect.y - new_rect.height
                    #
                    # print(new_rect)
                    #
                    # to_draw_append((sprite.image, new_rect, 1))

                    new_rect = sprite.rect.copy()
                    new_rect.y = map_height - new_rect.y - new_rect.height
                    # if sprite.axis:
                    #     new_rect.move_ip(*sprite.axis)
                    if camera_collide(new_rect):
                        new_rect = new_rect.move(xx, yy)
                        to_draw_append((sprite.image, new_rect, 1))

        if self.draw_map and self.draw_sprites:
            self.map_layer.draw(surface, self.rect, surfaces=to_draw)

        elif self.draw_map:
            self.map_layer.draw(surface, self.rect)

        if self.draw_overlay:
            from pymunk.pygame_util import draw
            overlay = self.overlay_surface
            overlay.set_clip(camera)
            overlay.fill((0, 0, 0))
            draw(overlay, self.parent.space)
            surface.blit(overlay, (xx, yy))


def make_rect(i):
    return i.x, i.y, i.width, i.height


def make_hitbox(body, rect):
    """ Special polygon shape that allows a wheel foot
    """
    points = [rect.bottomleft, rect.bottomright, rect.midright,
              rect.midtop, rect.midleft]
    return pymunk.Poly(body, points, (-rect.centerx, -rect.centery))


def make_body(rect):
    mass = 10
    body = pymunk.Body(mass, pymunk.inf)
    shape = make_hitbox(body, rect)
    return body, shape


def make_feet(rect):
    mass = 2
    radius = rect.width * .45
    inertia = pymunk.moment_for_circle(mass, 0, radius, (0, 0))
    body = pymunk.Body(mass, inertia)
    shape = pymunk.Circle(body, radius, (0, 0))
    return body, shape
