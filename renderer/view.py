import math
from itertools import chain
from functools import partial
import logging
import pygame
from pygame import surfarray
from pygame.transform import scale

logger = logging.getLogger('renderer')


class BufferedRenderer(object):
    def __init__(self, data, size):
        self.data = data
        self.size = size
        self.renderers = list(self.create_layer_renderers())
        self.staging_buffer = pygame.Surface(size, pygame.SRCALPHA)

        self.light_image = pygame.image.load('renderer/light.png').convert_alpha()

        # copy the alpha channel
        alpha = surfarray.pixels_green(self.light_image)
        surfarray.pixels_alpha(self.light_image)[:] = alpha[:]
        del alpha  # required so that the mask surface lock is released

        surfarray.pixels_red(self.light_image)[:] = 255
        surfarray.pixels_green(self.light_image)[:] = 255
        surfarray.pixels_blue(self.light_image)[:] = 255

    def center(self, coords):
        for r in self.renderers:
            r.center(coords)

    def draw(self, surface, surfaces=None):
        for index, r in enumerate(self.renderers):
            r.draw(self.staging_buffer, surfaces)

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
        self.view = None
        self.buffer = None
        self.x_offset = None
        self.y_offset = None
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

        self.x_offset = 0
        self.y_offset = 0
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
        left, self.x_offset = divmod(x - self.half_width, tw)
        top, self.y_offset = divmod(y - self.half_height, th)

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

            draw_lights = self.layers == [2]
            if draw_lights:
                self.draw_lights(surface)

    def draw_tile_layer(self, surface):
        surface.blit(self.buffer, (-self.x_offset, -self.y_offset))

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

        return [blit(tile, (x * tw - ltw, y * th - tth))
                for x, y, l, tile in self.queue]

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

        light_color = 200, 200, 200
        dark_color = 0, 0, 8, 220
        dynamic_light_mask_size = 16, 16

        overlay_size = surface.get_size()
        overlay = pygame.Surface(overlay_size, pygame.SRCALPHA)
        overlay.fill(dark_color)

        shapes = self.get_dynamic_lights()
        self.draw_circles(light_color, overlay, shapes)

        # light_mask = scale(overlay, dynamic_light_mask_size)
        # image = pygame_to_pil_img(light_mask)
        # image = image.filter(ImageFilter.GaussianBlur(2))
        # temp = pg_fromstring(image.tobytes(), image.size, image.mode)
        # overlay = scale(temp, overlay_size)

        surface.blit(overlay, (0, 0))
        # surface.blit(overlay, (0, 0))

    def draw_circles(self, color, image, shapes):
        # draw_ellipse = pygame.gfxdraw.filled_ellipse
        translate = self.shape_to_local_rect
        light = self.parent.light_image
        for shape in shapes:
            rect = translate(shape)
            # x, y, rx, ry = [int(i) for i in rect]
            # draw_ellipse(image, x, y, rx, ry, color)
            light1 = scale(light, rect[2:])
            image.blit(light1, rect, None, pygame.BLEND_RGBA_MULT)

    def shape_to_local_rect(self, shape):
        ox, oy = self.calc_local_offset()
        return shape.x + ox, shape.y + oy, shape.width, shape.height

    def calc_local_offset(self):
        return (-self.view.left * self.data.tilewidth - self.x_offset,
                -self.view.top * self.data.tileheight - self.y_offset)

    def get_dynamic_lights(self):
        shapes = self.data.tmx.get_layer_by_name('Lights')
        return shapes

