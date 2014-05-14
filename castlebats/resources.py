import os

import pytmx.tmxloader
import pygame


__all__ = ['sounds', 'images', 'music', 'maps', 'load', 'play_music']

# because i am lazy
_jpath = os.path.join

sounds = None
images = None
music = None
maps = None
level_xml = None


def load():
    from . import config

    global sounds, images, music, maps, level_xml

    sounds = dict()
    images = dict()
    music = dict()
    maps = dict()

    resource_path = config.get('paths', 'resource-path')
    resource_path = os.path.abspath(resource_path)

    level_xml = _jpath(resource_path, 'maps', 'objects.xml')

    for name, filename in config.items('sound-files'):
        path = _jpath(resource_path, 'sounds', filename)
        sound = pygame.mixer.Sound(path)
        sounds[name] = sound
        yield sound

    for name, filename in config.items('image-files'):
        path = _jpath(resource_path, 'images', filename)
        image = pygame.image.load(path)
        images[name] = image
        yield image

    for name, filename in config.items('map-files'):
        path = _jpath(resource_path, 'maps', filename)
        map = pytmx.tmxloader.load_pygame(path, pixelalpha=True)
        maps[name] = map
        yield map

    for name, filename in config.items('music-files'):
        path = _jpath(resource_path, 'music', filename)
        music[name] = path
        yield path


def play_music(name):
    try:
        pygame.mixer.music.load(music[name])
        pygame.mixer.music.play(-1)
    except pygame.error:
        pass