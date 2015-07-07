import math
from itertools import chain
from functools import partial
import logging

import pygame
import pygame.gfxdraw
from pygame import surfarray
from pygame.transform import scale, smoothscale
from pygame.image import fromstring as pg_fromstring
from PIL import Image, ImageFilter

logger = logging.getLogger('renderer')


def pygame_to_pil_img(pg_surface):
    """convert pygame surface to PIL Image"""
    imgstr = pygame.image.tostring(pg_surface, 'RGBA')
    return Image.fromstring('RGBA', pg_surface.get_size(), imgstr)


class BufferedRenderer(object):
    def __init__(self, data, size):
        self.data = data
        self.size = size
        self.renderers = list(self.create_layer_renderers())
        self.staging_buffer = pygame.Surface(size, pygame.SRCALPHA)
        self.under_surface = pygame.Surface(size, pygame.SRCALPHA)

    def center(self, coords):
        for r in self.renderers:
            r.center(coords)

    def draw(self, surface, surfaces=None):
        for index, r in enumerate(self.renderers):
            r.draw(self.staging_buffer, surfaces)

        # creates cool 'night time effect' with back lighting
        # surface.blit(self.under_surface, (0, 0), None, pygame.BLEND_RGB_MULT)
        # surface.blit(self.under_surface, (0, 0), None, pygame.BLEND_RGB_SUB)

        surface.blit(self.under_surface, (0, 64))
        surface.blit(self.staging_buffer, (0, 64))

    def create_layer_renderers(self):
        for layer in self.data.visible_tile_layers:
            r = BuffereredTileLayer(self.data, self.size, [layer])
            r.parent = self
            yield r


class BuffereredTileLayer(object):
    """
    Base class to render a map onto a buffer that is suitable for blitting onto
    the screen as one surface, rather than a collection of tiles.
    """

    def __init__(self, data, size, layers):
        self.data = data
        self.layers = layers
        self.padding = 1
        self.view = None
        self.buffer = None
        self.xoffset = None
        self.yoffset = None
        self.half_width = None
        self.half_height = None
        self.parent = None
        self.queue = None
        self.clear_color = 0, 0, 0, 0

        self.set_size(size)

    def set_size(self, size):
        """ Set the size of the map view in pixels
        """
        tw, th = self.data.tile_size

        buffer_width = math.ceil(size[0] / tw) + 2
        buffer_height = math.ceil(size[1] / th) + 2

        self.view = pygame.Rect(0, 0, buffer_width, buffer_height)
        self.buffer = pygame.Surface((buffer_width * tw, buffer_height * th), pygame.SRCALPHA)

        self.half_width = self.buffer.get_width() / 2
        self.half_height = self.buffer.get_height() / 2

        self.xoffset = 0
        self.yoffset = 0
        self.redraw_tiles()

    def center(self, coords):
        """ center the map on a pixel
        """
        x, y = [round(i, 0) for i in coords]

        if len(self.layers) == 1:
            layer = self.data.tmx.layers[self.layers[0]]
            parallax_ratio = layer.properties.get('parallax_ratio', None)
            if parallax_ratio:
                parallax_offset = layer.properties.get('parallax_offset')
                px, py = [float(i) for i in parallax_ratio.split(',')]
                ox, oy = [float(i) for i in parallax_offset.split(',')]
                if px != 0:
                    x = x / px + ox
                if py != 0:
                    y = y / py + oy

        tw, th = self.data.tile_size

        # calc the new position in tiles and offset
        left, self.xoffset = divmod(x - self.half_width, tw)
        top, self.yoffset = divmod(y - self.half_height, th)

        # determine if tiles should be redrawn
        # int is req'd b/c of Surface.scroll(...)
        dx = int(left - self.view.left)
        dy = int(top - self.view.top)

        # adjust the view if the view has changed without a redraw
        view_change = max(abs(dx), abs(dy))
        if view_change == 1:
            self.buffer.scroll(-dx * tw, -dy * th)
            self.view.move_ip((dx, dy))
            self.draw_edge_tiles((dx, dy))

        elif view_change > 1:
            logger.info('scrolling too quickly.  redraw forced')
            self.view.move_ip((dx, dy))
            self.redraw_tiles()

        self._center = x, y

    def draw_edge_tiles(self, offset):
        """ Get the tile coordinates that need to be redrawn
        """
        x, y = map(int, offset)
        self.queue = iter([])
        v = self.view
        fill = partial(self.buffer.fill, self.clear_color)
        bw, bh = self.buffer.get_size()
        tw, th = self.data.tile_size

        def append(*args):
            self.queue = chain(self.queue, self.data.get_tile_images_by_range(*args))

        if x > 0:    # right side
            d = x * tw
            append(v.right - x, v.right, v.top, v.bottom, self.layers)
            fill((bw - d, 0, d, bh))

        elif x < 0:  # left side
            append(v.left - x, v.left, v.top, v.bottom, self.layers)
            fill((0, 0, -x * tw, bh))

        if y > 0:    # bottom side
            d = y * th
            append(v.left, v.right, v.bottom - y, v.bottom, self.layers)
            fill((0, bh - d, bw, d))

        elif y < 0:  # top side
            append(v.left, v.right, v.top, v.top - y, self.layers)
            fill((0, 0, bw, y * th))

        self.flush()

    def draw(self, surface, surfaces=None):
        """ Draw the layer onto a surface
        """
        self.draw_tile_layer(surface)

        if surfaces is not None:
            self.draw_surfaces(surface, surfaces)

            backlight_sensor = pygame.Rect(0, 0, 10, 10)
            backlight_sensor.center = self._center
            shapes = self.parent.data.tmx.get_layer_by_name('Backlight')
            rects = [self.shape_to_local_rect(i) for i in shapes]
            draw_backlight = not backlight_sensor.collidelist(rects) == -1

            if draw_backlight and self.layers == [2]:
                self.draw_backlight(surface, surfaces)

            draw_lights = self.layers == [2]
            if draw_lights:
                self.draw_lights(surface)

    def draw_tile_layer(self, surface):
        surface.blit(self.buffer, (-self.xoffset, -self.yoffset))

    def draw_surfaces(self, surface, surfaces):
        layer = self.layers[0]
        dirty = [surface.blit(i[0], i[1]) for i in surfaces if i[2] == layer]
        return dirty

    def flush(self):
        """ Blit the tiles and block until the tile queue is empty
        """
        tw, th = self.data.tile_size
        ltw = self.view.left * tw
        tth = self.view.top * th
        blit = self.buffer.blit

        for x, y, l, tile in self.queue:
            if tile:
                area = x * tw - ltw, y * th - tth, tw, th
                blit(tile, area)

    def redraw_tiles(self):
        """ redraw the visible portion of the buffer -- it is slow.
        """
        self.buffer.fill(self.clear_color)
        self.queue = self.data.get_tile_images_by_range(
            self.view.left, self.view.right,
            self.view.top, self.view.bottom,
            self.layers)
        self.flush()

    def draw_lights(self, surface):
        light_color = (0, 0, 0, 0)
        dark_color = (0, 0, 0, 220)
        dynamic_light_mask_size = (16, 16)

        overlay_size = surface.get_size()
        overlay = pygame.Surface(overlay_size, pygame.SRCALPHA)
        overlay.fill(dark_color)

        shapes = self.get_dynamic_lights()
        self.draw_circles(light_color, overlay, shapes)

        light_mask = scale(overlay, dynamic_light_mask_size)
        image = pygame_to_pil_img(light_mask)
        image = image.filter(ImageFilter.GaussianBlur(2))
        temp = pg_fromstring(image.tobytes(), image.size, image.mode)
        scale(temp, overlay_size, overlay)

        surface.blit(overlay, (0, 0))

    def draw_backlight(self, surface, surfaces):
        mask = pygame.Surface(surface.get_size(), pygame.SRCALPHA)

        for r in self.parent.renderers[1:]:
            r.draw_tile_layer(mask)
            r.draw_surfaces(mask, surfaces)

        shapes = self.data.tmx.get_layer_by_name('Backlight')
        rect = pygame.Rect(self.shape_to_local_rect(shapes[0]))

        x = rect.centerx - self._center[0]
        alpha = max(min(x / 1500. * 255, 255), 160)
        mod = max(min(x / 1500., 1.0), 0.7)
        print alpha, mod

        dynamic_bloom_mask_size = (256, 128)
        light_color = [int(i) for i in (235 * mod, 230 * mod, 200 * mod, alpha)]

        overlay_size = mask.get_size()
        overlay = pygame.Surface(overlay_size, pygame.SRCALPHA)

        shapes = self.data.tmx.get_layer_by_name('Backlight')
        self.draw_circles(light_color, surface, shapes)

        # copy the alpha channel
        alpha = surfarray.pixels_alpha(mask)
        surfarray.pixels_alpha(overlay)[:] = alpha[:]
        del alpha  # required so that the mask surface lock is released

        bloom_buffer = smoothscale(overlay, dynamic_bloom_mask_size)
        stencil = pygame_to_pil_img(bloom_buffer)

        # dark foreground
        dark = stencil.filter(ImageFilter.GaussianBlur(3))
        temp = pg_fromstring(dark.tobytes(), dark.size, dark.mode)
        dark_overlay = smoothscale(temp, overlay_size, overlay)

        # surface.blit(overlay, (0, 0), None, pygame.BLEND_RGBA_ADD)
        # surface.blit(light_overlay, (0, 0))
        surface.blit(dark_overlay, (0, 0))

    def draw_circles(self, color, image, shapes):
        draw_ellipse = pygame.gfxdraw.filled_ellipse
        translate = self.shape_to_local_rect
        for shape in shapes:
            rect = translate(shape)
            x, y, rx, ry = [int(i) for i in rect]
            draw_ellipse(image, x, y, rx, ry, color)

    def shape_to_local_rect(self, shape):
        ox, oy = self.calc_local_offset()
        return shape.x + ox, shape.y + oy, shape.width, shape.height

    def calc_local_offset(self):
        return (-self.view.left * self.data.tilewidth - self.xoffset,
                -self.view.top * self.data.tileheight - self.yoffset)

    def get_dynamic_lights(self):
        shapes = self.data.tmx.get_layer_by_name('Lights')
        return shapes
