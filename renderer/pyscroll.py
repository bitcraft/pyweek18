from PIL import Image
import pygame
import math
from itertools import product, chain
from six.moves import queue, range
from . import quadtree
from pygame import surfarray
from pygame.transform import scale, smoothscale
from pygame.image import fromstring as pg_fromstring
from PIL import Image, ImageFilter
from functools import partial


class BufferedRenderer(object):
    def __init__(self, data, size):
        self.data = data
        self.size = size
        self.renderers = list(self.create_layer_renderers())
        self.staging_buffer = pygame.Surface(size, pygame.SRCALPHA)

    def center(self, coords):
        for r in self.renderers:
            r.center(coords)

    def draw(self, surface, surfaces=None):
        for r in self.renderers:
            r.offset = self.offset
            r.draw(self.staging_buffer, surfaces)

        surface.blit(self.staging_buffer, (0, 0))

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
        self.padding = 4
        self.view = None
        self.buffer = None
        self.xoffset = None
        self.yoffset = None
        self.half_width = None
        self.half_height = None

        self.set_size(size)
        self.queue = iter([])

    def set_size(self, size):
        """ Set the size of the map in pixels
        """
        tw = self.data.tilewidth
        th = self.data.tileheight

        buffer_width = math.ceil(size[0] / tw) + self.padding
        buffer_height = math.ceil(size[1] / th) + self.padding

        self.view = pygame.Rect(0, 0, buffer_width, buffer_height)
        self.buffer = pygame.Surface((buffer_width * tw, buffer_height * th), pygame.SRCALPHA)

        self.half_width = self.buffer.get_width() / 2
        self.half_height = self.buffer.get_height() / 2

        # quadtree is used to correctly draw tiles that cover 'sprites'
        def make_rect(x, y):
            return pygame.Rect((x * tw, y * th), (tw, th))

        rects = [make_rect(x, y)
                 for x, y in product(range(self.view.width),
                                     range(self.view.height))]

        # TODO: figure out what depth -actually- does
        self.layer_quadtree = quadtree.FastQuadTree(rects, 4)

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

        tw = self.data.tilewidth
        th = self.data.tileheight

        # calc the new postion in tiles and offset
        left, self.xoffset = divmod(x - self.half_width, tw)
        top, self.yoffset = divmod(y - self.half_height, th)

        # determine if tiles should be redrawn
        dx = int(left - self.view.left)
        dy = int(top - self.view.top)

        half_padding = int(self.padding / 2)
        self.xoffset += half_padding * tw
        self.yoffset += half_padding * th

        # adjust the view if the view has changed without a redraw
        if not dx == dy == 0:
            self.view = self.view.move((dx, dy))
            # self.buffer.scroll(-dx * tw, -dy * th)
            # self.update_queue(self.get_edge_tiles((dx, dy)))
            # self.flush()
            self.redraw_tiles()

    def get_edge_tiles(self, offset):
        """ Get the tile coordinates that need to be redrawn
        """
        x, y = map(int, offset)
        layers = self.layers
        view = self.view
        getter = self.data.get_tile_images_by_range
        queue = None

        # right side
        if x > 0:
            queue = getter(view.right - x, view.right,
                           view.top, view.bottom, layers)

        # left side
        elif x < 0:
            queue = getter(view.left - x, view.left,
                           view.top, view.bottom, layers)

        # bottom side
        if y > 0:
            p = getter(view.left, view.right,
                       view.bottom - y, view.bottom, layers)
            if queue is None:
                queue = p
            else:
                queue = chain(p, queue)

        # top side
        elif y < 0:
            p = getter(view.left, view.right,
                       view.top, view.top - y, layers)
            if queue is None:
                queue = p
            else:
                queue = chain(p, queue)

        return queue

    def draw(self, surface, surfaces=None):
        """ Draw the layer onto a surface
        """
        self.blit_surface_with_offset(self.buffer, surface)
        self.draw_surfaces(surface, surfaces)

        draw_backlight = self.layers == [2]
        if draw_backlight:
            self.draw_backlight(surface)

        draw_lights = self.layers == [2]
        if draw_lights:
            self.draw_lights(surface)

    def blit_surface_with_offset(self, source, destination):
        destination.blit(source, (-self.xoffset, -self.yoffset))

    def draw_surfaces(self, surface, surfaces):
        surblit = surface.blit
        ox, oy = self.xoffset, self.yoffset

        if surfaces is not None:
            def above(x, y):
                return x > y

            left, top = self.view.topleft
            hit = self.layer_quadtree.hit
            get_tile = self.data.get_tile_image
            tile_layers = tuple(self.data.visible_tile_layers)
            layer = self.layers[0]
            dirty = [(surblit(i[0], i[1]), i[2]) for i in surfaces if i[2] == layer]

            # for dirty_rect, layer in dirty:
            #     for r in hit(dirty_rect.move(ox, oy)):
            #         x, y, tw, th = r
            #         for l in [i for i in tile_layers if above(i, layer)]:
            #             tile = get_tile((int(x / tw + left),
            #                              int(y / th + top), int(l)))
            #             if tile:
            #                 surblit(tile, (x - ox, y - oy))

    def flush(self):
        """ Blit the tiles and block until the tile queue is empty
        """
        self.blit_tiles(self.queue)

    def blit_tiles(self, iterator):
        """ Bilts (x, y, layer) tuples to buffer from iterator
        """
        tw = self.data.tilewidth
        th = self.data.tileheight
        ltw = self.view.left * tw
        tth = self.view.top * th
        blit = self.buffer.blit
        fill = self.buffer.fill
        clear_color = (0, 0, 0, 0)

        for x, y, l, tile in iterator:
            area = (x * tw - ltw, y * th - tth, tw, th)
            if l == 0 and tile:
                fill(clear_color, area)
                blit(tile, area)

            elif tile:
                blit(tile, area)

    def redraw_tiles(self):
        """ redraw the visible portion of the buffer -- it is slow.
        """
        # TODO: remove fill after debug
        self.buffer.fill((0, 0, 0, 0))
        self.queue = self.data.get_tile_images_by_range(
            self.view.left, self.view.right,
            self.view.top, self.view.bottom,
            self.layers)
        self.flush()

    def draw_lights(self, surface):
        xx = -self.view.left * self.data.tilewidth - self.xoffset
        yy = -self.view.top * self.data.tileheight - self.yoffset

        light_color = (0, 0, 0, 0)
        dark_color = (0, 0, 0, 200)
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

    def draw_backlight(self, surface):
        # needs more map things
        # if self.following:
        #     backlight_sensor = self.following.rect
        #     shapes = self.parent.map_data.tmx.get_layer_by_name('Backlight')
        #     rects = [make_rect(i) for i in shapes]
        #     draw_backlight = not backlight_sensor.collidelist(rects) == -1
        #
        xx = -self.view.left * self.data.tilewidth + self.xoffset
        yy = -self.view.top * self.data.tileheight - self.yoffset

        mask = self.parent.staging_buffer

        dynamic_bloom_mask_size = (256, 128)
        light_color = (255, 239, 153, 128)
        dark_color = (8, 8, 16, 255)

        overlay_size = mask.get_size()
        overlay = pygame.Surface(overlay_size, pygame.SRCALPHA)
        overlay.fill(dark_color)

        # # copy the alpha channel
        # alpha = surfarray.pixels_alpha(mask)
        # surfarray.pixels_alpha(overlay)[:] = alpha[:]
        # del alpha

        # shapes = self.data.tmx.get_layer_by_name('Backlight')
        # self.draw_circles(light_color, surface, shapes)

        bloom_buffer = smoothscale(self.buffer, dynamic_bloom_mask_size)

        image = pygame_to_pil_img(bloom_buffer)
        # image = image.filter(ImageFilter.GaussianBlur(2))

        temp = pg_fromstring(image.tobytes(), image.size, image.mode)
        overlay = scale(temp, overlay_size, overlay)

        surface.blit(overlay, (0, 0))
        #self.blit_surface_with_offset(overlay, surface)

    def draw_circles(self, color, image, shapes):
        draw_ellipse = pygame.draw.ellipse
        for shape in shapes:
            rect = (shape.x, shape.y, shape.width, shape.height)
            draw_ellipse(image, color, rect)

    def get_dynamic_lights(self):
        shapes = self.data.tmx.get_layer_by_name('Lights')
        return shapes


def pygame_to_pil_img(pg_surface):
    """convert pygame surface to PIL Image"""
    imgstr = pygame.image.tostring(pg_surface, 'RGBA')
    return Image.fromstring('RGBA', pg_surface.get_size(), imgstr)


def pil_to_pygame_img(pil_img):
    """convert PIL Image to pygame surface"""
    imgstr = pil_img.tostring()
    return pygame.image.fromstring(imgstr, pil_img.size, 'RGB')