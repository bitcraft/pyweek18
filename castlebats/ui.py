import pygame

__all__ = ['TextSprite']

pygame.init()
pygame.font.init()
default_font = pygame.font.get_default_font()
font = pygame.font.Font(default_font, 32)


class TextSprite(pygame.sprite.DirtySprite):
    def __init__(self, text, color=None, bgcolor=None):
        super(TextSprite, self).__init__()
        self._text_object = None
        self._text = None
        self._color = None
        self._bgcolor = None
        self.text = text
        self.color = color
        self.bgcolor = bgcolor
        self.image = None
        self.rect = pygame.Rect(0, 0, 1, 1)
        self.update_image()

    def update(self, dt=None):
        text = str(self._text_object)
        if not text == self._text:
            self._text = text
            self.update()

    def update_image(self):
        self.image = font.render(self._text, 0, self._color, self._bgcolor)
        self.rect.size = self.image.get_size()
        self.dirty = 1

    @property
    def bgcolor(self):
        return self._bgcolor

    @bgcolor.setter
    def bgcolor(self, value):
        color = pygame.Color(*value)
        if self._bgcolor is None:
            self._bgcolor = color
            return

        if not color == self._bgcolor:
            self._bgcolor = color
            self.update()

    @property
    def color(self):
        return self._color

    @color.setter
    def color(self, value):
        color = pygame.Color(*value)
        if self._color is None:
            self._color = color
            return

        if not color == self.color:
            self._color = color
            self.update()

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, value):
        text = str(value)
        if self._text is None:
            self._text_object = value
            self._text = text
            return

        if not text == self._text:
            self._text_object = value
            self._text = text
            self.update()
