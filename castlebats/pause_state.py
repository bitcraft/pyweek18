from castlebats.lib2.state import State
from castlebats.lib2.animation import Animation
from castlebats.gui import GraphicBox
from castlebats import state_manager

from os.path import join


class Pause(State):
    def resume(self):
        filename = join('resources', 'images', 'dialog.png')
        import pygame

        image = pygame.image.load(filename).convert_alpha()

        self.box = GraphicBox(image)
        self.gui_mod = 0

        ani = Animation(gui_mod=1.0, duration=.25, transition='out_quint')
        ani.start(self)

    def draw(self, surface, rect):
        surface.fill(0)

        new = rect.copy()
        new.width = rect.width * self.gui_mod
        new.height = rect.height * self.gui_mod
        new.center = rect.center
        self.box.draw(surface, new)


state_manager.register_state(Pause)
