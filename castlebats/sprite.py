from math import degrees
import itertools
from collections import OrderedDict
import logging

from pymunk.vec2d import Vec2d
from PIL import Image, ImageDraw, ImageFilter, ImageChops

from pygame.transform import rotate, flip, scale
import pygame
import pymunk

from six.moves import zip
import renderer
import random
logger = logging.getLogger("castlebats.sprite")

from . import resources
from . import config


class CastleBatsSprite(pygame.sprite.Sprite):
    """
    sprite tracks one pymunk shape and can draw it to a viewport
    not quiet dirty sprite compatible
    """
    animations = {}
    loaded = False

    def __init__(self, shape):
        super(CastleBatsSprite, self).__init__()
        self.shape = shape
        self.rect = None
        self.axis = None
        self.image = None
        self.flip = False
        self._old_angle = None
        self.dirty = False
        self.state = []
        self.old_state = []
        self.animation_timer = 0
        self.original_surface = None
        self.current_animation = []

    def __del__(self):
        logger.info("garbage collecting %s", self)

    def kill(self):
        """
        remove all the physics stuff from the space
        """
        space = self.shape.body._space
        if self.shape.body in space.bodies:
            space.remove(self.shape.body)
        space.remove(self.shape)
        del self.shape
        del self.original_surface
        super(CastleBatsSprite, self).kill()

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

    def update(self, dt):
        if self.animation_timer > 0:
            self.animation_timer -= dt
            if self.animation_timer <= 0:
                over = self.animation_timer
                try:
                    self.set_frame(next(self.current_animation))
                    self.animation_timer += over
                except StopIteration:
                    try:
                        # remove the old animation
                        self.state.pop()
                        animation = self.state.pop()
                    except IndexError:
                        animation = 'idle'
                    self.change_state(animation)

    def set_frame(self, frame):
        self.animation_timer, frame = frame
        new_surf, axis = frame
        self.axis = pymunk.Vec2d(axis)
        if self.flip:
            w, h = new_surf.get_size()
            new_surf = flip(new_surf, 1, 0)
            self.axis.x = -self.axis.x
        self.original_surface = new_surf
        self.dirty = True

    def set_animation(self, name, func=None):
        self.animation_timer, animation = self.animations[name]

        logger.info("%s set animation %s", self, name)

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


class BoxSprite(CastleBatsSprite):
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
            image = rotate(self.original_surface, angle)
            self.image = image.convert()
            self.rect = image.get_rect()
            self._old_angle = angle
            self.dirty = False

        self.shape.cache_bb()
        bb = self.shape.bb
        self.rect.topleft = bb.left, bb.bottom


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
        logger.info("resizing the viweports")
        rects = list()
        if len(self.viewports) == 1:
            x, y, w, h = self.rect
            rects = [
                (x, y, w, h),
            ]

        elif len(self.viewports) == 2:
            x, y, w, h = self.rect
            rects = [
                (x, y, w, h / 2),
                (x, h / 2 + y, w, h / 2 + y),
            ]

        else:
            logger.error(
                "too many viewports in the manager. only 2 are allowed.")
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
            # handle in case the vp is following this sprite
            for vp in self.viewports.keys():
                if vp.following is sprite:
                    vp.follow(None)
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
        self.rect = pygame.Rect(rect)
        md = self.parent.map_data
        colorkey = (128, 64, 128)
        self.map_layer = renderer.BufferedRenderer(md, self.rect.size)
        self.map_height = md.height * md.tileheight
        self.center()

        self.effects_buffer = pygame.Surface(rect.size, pygame.SRCALPHA)

        #self.camera_vector = pymunk.Vec2d(rect.center)

        if self.draw_overlay:
            md = self.parent.map_data
            height = md.height * md.tileheight
            width = md.width * md.width
            self.overlay_surface = pygame.Surface((width, height))
            self.overlay_surface.set_colorkey((0, 0, 0))
            alpha = config.getint('display', 'physics-overlay-alpha')
            self.overlay_surface.set_alpha(alpha)

    def add_internal(self, group):
        try:
            assert (isinstance(group, ViewPortGroup))
        except AssertionError:
            raise

        super(ViewPort, self).add_internal(group)
        self.parent = group

    def follow(self, sprite):
        """
        only follow a sprite, not a pymunk shape
        """
        if sprite is None:
            self.following = None
        else:
            assert (isinstance(sprite, CastleBatsSprite))
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

    def update(self, delta):
        self.center()

    def draw(self, surface, surface_rect):
        if not surface_rect == self.rect:
            self.set_rect(surface_rect)

        surface.set_clip(surface_rect)

        camera = self.rect.copy()
        camera.center = self.camera_vector

        xx, yy = -self.camera_vector + surface_rect.center - surface_rect.topleft

        surface_blit = surface.blit
        to_draw = list()

        # map_buffer = pygame.Surface(surface_rect.size, pygame.SRCALPHA)

        if self.draw_sprites:
            to_draw_append = to_draw.append
            camera_collide = camera.colliderect
            map_height = self.map_height

            for sprite in self.parent.sprites():
                if isinstance(sprite, CastleBatsSprite):
                    sprite.update_image()
                    new_rect = sprite.rect.copy()
                    new_rect.y = map_height - new_rect.y - new_rect.height

                    if sprite.axis:
                        new_rect.move_ip(*sprite.axis)

                    if camera_collide(new_rect):
                        new_rect = new_rect.move(xx, yy)
                        to_draw_append((sprite.image, new_rect, 1))

        if self.draw_map and self.draw_sprites:
            self.map_layer.draw(self.effects_buffer, to_draw)
            surface.blit(self.effects_buffer, surface_rect)

        elif self.draw_sprites:
            for s, r, l in to_draw:
                surface_blit(s, r)

        elif self.draw_map:
            self.map_layer.draw(surface, self.rect)

        if self.draw_overlay:
            overlay = self.overlay_surface
            overlay.set_clip(camera)
            overlay.fill((0, 0, 0))
            # pymunk_draw(overlay, self.parent.space)
            surface.blit(overlay, (xx, yy))

        # # lights layer
        # # draw circles for lights
        # # blend together
        dynamic_light_mask_size = (16, 16)
        dynamic_bloom_mask_size = (256, 128)

        draw_lights = 1
        if draw_lights:
            image = Image.new('RGBA', surface_rect.size, (0, 0, 0, 230))

            # TODO: get easier access to the tmx data?
            color = (0, 0, 0, 0)
            shapes = self.parent.map_data.tmx.get_layer_by_name('Lights')
            self.draw_circles(color, image, shapes, (xx, yy))

            image = image.resize(dynamic_light_mask_size)
            image = image.filter(ImageFilter.GaussianBlur(8))
            overlay = pygame.image.fromstring(image.tobytes(), image.size, image.mode)
            overlay = scale(overlay, surface_rect.size)
            surface_blit(overlay, surface_rect)

        # bloom layer
        # draw circles for lights
        # cut out screen pixels
        # blur
        # paste on screen

        draw_backlight = 0
        if self.following:
            backlight_sensor = self.following.rect
            shapes = self.parent.map_data.tmx.get_layer_by_name('Backlight')
            rects = [make_rect(i) for i in shapes]
            draw_backlight = not backlight_sensor.collidelist(rects) == -1

        if draw_backlight:
            image = Image.new('RGBA', surface_rect.size, (0, 0, 0, 24))

            color = (255, 239, 153, 128)

            # # TODO: get easier access to the tmx data?
            shapes = self.parent.map_data.tmx.get_layer_by_name('Backlight')
            self.draw_circles(color, image, shapes, (xx, yy))

            image = image.resize(dynamic_bloom_mask_size)
            small_buffer = pygame.transform.scale(self.effects_buffer, dynamic_bloom_mask_size)
            pygame_mask = pygame_to_pil_img(small_buffer)
            r, g, b, a = pygame_mask.split()
            inv_a = ImageChops.invert(a)
            image.paste(inv_a, (0, 0), mask=a)
            # image.putalpha(a)

            image = image.filter(ImageFilter.GaussianBlur(2))

            # image = image.filter(ImageFilter.BLUR)
            overlay = pygame.image.fromstring(image.tobytes(), image.size, image.mode)
            overlay = scale(overlay, surface_rect.size)
            surface_blit(overlay, surface_rect, None)

        surface.set_clip(None)

        # TODO: dirty updates
        return self.rect

    def draw_circles(self, color, image, shapes, offset=(0, 0)):
        draw = ImageDraw.Draw(image)
        draw_ellipse = draw.ellipse
        ox, oy = offset
        for shape in shapes:
            x1 = shape.x + ox
            y1 = shape.y + oy
            x2 = x1 + shape.width
            y2 = y1 + shape.height
            draw_ellipse((x1, y1, x2, y2), color)


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


def pygame_to_pil_img(pg_surface):
    """convert pygame surface to PIL Image"""
    imgstr = pygame.image.tostring(pg_surface, 'RGBA')
    return Image.fromstring('RGBA', pg_surface.get_size(), imgstr)

def pil_to_pygame_img(pil_img):
    """convert PIL Image to pygame surface"""
    imgstr = pil_img.tostring()
    return pygame.image.fromstring(imgstr, pil_img.size, 'RGB')