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
    def __init__(self, data, size, clamp_camera=False):

        # default options
        self.padding = 2
        self.clamp_camera = clamp_camera
        self.clipping = True

        # internal defaults
        self.data = data
        self.xoffset = None
        self.yoffset = None
        self.old_x = None
        self.old_y = None
        self.buffer = None
        self.map_rect = None
        self.view = None
        self.half_width = None
        self.half_height = None

        self.set_size(size)
        self.queue = iter([])

    def set_size(self, size):
        """ Set the size of the map in pixels
        """
        tw = self.data.tilewidth
        th = self.data.tileheight

        buffer_width = size[0] + tw * self.padding
        buffer_height = size[1] + th * self.padding

        self.buffer = pygame.Surface((buffer_width, buffer_height), pygame.SRCALPHA)

        self.view = pygame.Rect(0, 0,
                                math.ceil(buffer_width / tw),
                                math.ceil(buffer_height / th))

        # this is the pixel size of the entire map
        self.map_rect = pygame.Rect(0, 0,
                                self.data.width * tw,
                                self.data.height * th)

        self.half_width = size[0] / 2
        self.half_height = size[1] / 2

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
        self.old_x = 0
        self.old_y = 0

    def scroll(self, vector):
        """ scroll the background in pixels
        """
        self.center((vector[0] + self.old_x, vector[1] + self.old_y))

    def center(self, coords):
        """ center the map on a pixel
        """
        x, y = [round(i, 0) for i in coords]

        if self.clamp_camera:
            if x < self.half_width:
                x = self.half_width
            elif x + self.half_width > self.map_rect.width:
                x = self.map_rect.width - self.half_width
            if y < self.half_height:
                y = self.half_height
            elif y + self.half_height > self.map_rect.height:
                y = self.map_rect.height - self.half_height

        if self.old_x == x and self.old_y == y:
            return

        hpad = int(self.padding / 2)
        tw = self.data.tilewidth
        th = self.data.tileheight

        # calc the new postion in tiles and offset
        left, self.xoffset = divmod(x - self.half_width, tw)
        top, self.yoffset = divmod(y - self.half_height, th)

        # determine if tiles should be redrawn
        dx = int(left - hpad - self.view.left)
        dy = int(top - hpad - self.view.top)

        # adjust the offsets of the buffer is placed correctly
        self.xoffset += hpad * tw
        self.yoffset += hpad * th

        # completely redraw screen if position has changed significantly
        if (abs(dx) >= 2) or (abs(dy) >= 2):
            self.view = self.view.move((dx, dy))
            self.redraw()

        # adjust the view if the view has changed without a redraw
        elif (abs(dx) >= 1) or (abs(dy) >= 1):
            # mark portions to redraw
            self.view = self.view.move((dx, dy))

            # scroll the image (much faster than redrawing the entire map!)
            self.buffer.scroll(-dx * tw, -dy * th)
            self.update_queue(self.get_edge_tiles((dx, dy)))

        self.old_x, self.old_y = x, y

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

    def draw(self, surface, rect, surfaces=None):
        """ Draw the layer onto a surface

        pass a rect that defines the draw area for:
            dirty screen update support
            drawing to an area smaller that the whole window/screen

        surfaces may optionally be passed that will be blited onto the surface.
        this must be a list of tuples containing a layer number, image, and
        rect in screen coordinates.  surfaces will be drawn in order passed,
        and will be correctly drawn with tiles from a higher layer overlapping
        the surface.
        """
        surblit = surface.blit
        ox, oy = self.xoffset, self.yoffset
        ox -= rect.left
        oy -= rect.top

        # need to set clipping otherwise the map will draw outside its area
        original_clip = surface.get_clip()
        surface.set_clip(rect)

        # draw the entire map to the surface,
        # taking in account the scrolling offset
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

        surface.set_clip(original_clip)

        return [rect]

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
