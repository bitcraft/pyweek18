import itertools

from .sprite import CastleBatsSprite


class Sprite(CastleBatsSprite):
    sprite_sheet = 'bat.png'
    name = 'bat'

    image_animations = [
        ('flying', 700, ((8, 5, 19, 23, 15, 0), (42, 5, 19, 16, 16, 5))),
    ]

    def __init__(self):
        super(Bat, self).__init__()
        bbox = physics.BBox((0, 0, 0, 20, 20, 20))
        self.body = physics.Body3(bbox, (0, 0), (0, 0), gravity=False)
        self.load_animations()
        self.change_state('flying')
        self.body.vel.y = 1.0

    def change_state(self, state):
        self.state.append(state)

        if 'flying' in self.state:
            self.set_animation('flying', itertools.cycle)