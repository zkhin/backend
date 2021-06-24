# keep in sync with object created handlers defined serverless.yml


class _VideoSize:
    def __init__(self, name, width, height):
        self.name = name
        self.width = width
        self.height = height

    @property
    def resolution(self):
        return {'width': self.width, 'height': self.height}


P1920 = _VideoSize('1920p', 1920, 1080)
P1280 = _VideoSize('1280p', 1280, 720)
P960 = _VideoSize('960p', 960, 540)
P640 = _VideoSize('640p', 640, 360)
P480 = _VideoSize('480p', 480, 278)
