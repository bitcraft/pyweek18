import pygame
import math
from itertools import product, chain
from six.moves import queue, range
from . import quadtree


class BufferedRenderer(object):
    """
    Base class to render a map onto a buffer that is suitable for blitting onto
    the screen as one surface, rather than a collection of tiles.
    """
    def __init__(self, data, size):

        # default options
        self.padding = 10
        self.clipping = True

        # internal defaults
        self.data = data
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
        self.redraw()

    def scroll(self, vector):
        """ scroll the background in pixels
        """
        self.center((vector[0] + self.old_x, vector[1] + self.old_y))

    def center(self, coords):
        """ center the map on a pixel
        """
        x, y = [round(i, 0) for i in coords]

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
            self.redraw()

    def update_queue(self, iterator):
        """ Add some tiles to the queue
        """
        self.queue = chain(self.queue, iterator)

    def get_edge_tiles(self, offset):
        """ Get the tile coordinates that need to be redrawn
        """
        x, y = map(int, offset)
        layers = list(self.data.visible_tile_layers)
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
        surblit = surface.blit
        ox, oy = self.xoffset, self.yoffset

        # draw the entire map to the surface, taking in account the scrolling offset
        surblit(self.buffer, (-ox, -oy))

        if surfaces is not None:
            def above(x, y):
                return x > y

            left, top = self.view.topleft
            hit = self.layer_quadtree.hit
            get_tile = self.data.get_tile_image
            tile_layers = tuple(self.data.visible_tile_layers)
            dirty = [(surblit(i[0], i[1]), i[2]) for i in surfaces]

            for dirty_rect, layer in dirty:
                for r in hit(dirty_rect.move(ox, oy)):
                    x, y, tw, th = r
                    for l in [i for i in tile_layers if above(i, layer)]:
                        tile = get_tile((int(x / tw + left),
                                         int(y / th + top), int(l)))
                        if tile:
                            surblit(tile, (x - ox, y - oy))

    def flush(self):
        """ Blit the tiles and block until the tile queue is empty
        """
        self.blit_tiles(self.queue)

    def blit_tiles(self, iterator):
        """ Bilts (x, y, layer) tuples to buffer from iterator
        """
        tw = self.data.tilewidth
        th = self.data.tileheight
        blit = self.buffer.blit
        ltw = self.view.left * tw
        tth = self.view.top * th
        fill = self.buffer.fill
        fill_color = (0, 0, 0, 0)

        for x, y, l, tile in iterator:
            if l == 0:
                fill(fill_color,
                     (x * tw - ltw, y * th - tth, tw, th))

            if tile:
                blit(tile, (x * tw - ltw, y * th - tth))

    def redraw(self):
        """ redraw the visible portion of the buffer -- it is slow.
        """
        queue = self.data.get_tile_images_by_range(
            self.view.left, self.view.right,
            self.view.top, self.view.bottom,
            self.data.visible_tile_layers)

        self.queue = queue
        self.flush()
