"""
This file contains two data classes for use with pytmx.
"""

import sys
import pytmx

__all__ = ['TiledMapData']


class TiledMapData(object):
    """ For PyTMX 3.x and 6.x
    """

    def __init__(self, tmx):
        self.tmx = tmx

    @property
    def tilewidth(self):
        return self.tmx.tilewidth

    @property
    def tileheight(self):
        return self.tmx.tileheight

    @property
    def tile_size(self):
        return self.tmx.tilewidth, self.tmx.tileheight

    @property
    def width(self):
        return self.tmx.width

    @property
    def height(self):
        return self.tmx.height

    @property
    def visible_tile_layers(self):
        return self.tmx.visible_tile_layers

    def get_tile_image(self, position):
        """ Return a surface for this position.

        Returns a blank tile if cannot be loaded.
        position is x, y, layer tuple
        """
        try:
            return self.tmx.get_tile_image(*position)
        except ValueError:
            return None

    def get_tile_image_by_gid(self, gid):
        """ Return surface for a gid (experimental)
        """
        return self.tmx.get_tile_image_by_gid(gid)

    def get_tile_images_by_range(self, x_start, x_stop, y_start, y_stop,
                                 layer_range):
        """ Not like python 'Range': will include the end index!

        :param x_start: Start x (column) index
        :param x_stop: Stop x (column) index
        :param y_start: Start of y (row) index
        :param y_stop: Stop of y (row) index
        :param layer_range:
        :return:
        """
        def do_rev(seq, start, stop):
            if start < stop:
                return enumerate(seq[start:stop], start)
            else:
                return enumerate(seq[stop:start], stop)

        images = self.tmx.images
        for layer_no in layer_range:
            data = self.tmx.layers[layer_no].data
            for y, row in do_rev(data, y_start, y_stop):
                for x, gid in do_rev(row, x_start, x_stop):
                    if gid:
                        yield x, y, layer_no, images[gid]


class LegacyTiledMapData(TiledMapData):
    """ For PyTMX 2.x series
    """

    @property
    def visible_layers(self):
        return (int(i) for (i, l) in enumerate(self.tmx.all_layers)
                if l.visible)

    @property
    def visible_tile_layers(self):
        return (int(i) for (i, l) in enumerate(self.tmx.visibleTileLayers))

    @property
    def visible_object_layers(self):
        return (layer for layer in self.tmx.objectgroups if layer.visible)

    def get_tile_image(self, position):
        """ Return a surface for this position.

        Returns a blank tile if cannot be loaded.
        position is x, y, layer tuple
        """
        x, y, l = position
        return self.tmx.getTileImage(x, y, l)

    def get_tile_image_by_gid(self, gid):
        """ Return surface for a gid (experimental)
        """
        return self.tmx.getTileImageByGid(gid)


try:
    if getattr(pytmx, "__version__", (0, 0, 0)) < (2, 18, 0):
        sys.stderr.write('pyscroll is using the legacy pytmx api\n')
        TiledMapData = LegacyTiledMapData
except (AttributeError, TypeError):
    sys.stderr.write('pyscroll is using the legacy pytmx api\n')
    TiledMapData = LegacyTiledMapData
