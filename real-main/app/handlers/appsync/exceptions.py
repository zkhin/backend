class ClientException(Exception):
    "Any error attributable to the graphql client"

    def __init__(self, message, data=None, info=None):
        self.message = message
        self.data = data
        self.info = info
        super().__init__()

    def __str__(self):
        return self.message
