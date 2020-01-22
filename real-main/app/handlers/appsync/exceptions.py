class ClientException(Exception):
    "Any error attributable to the graphql client"

    def __init__(self, message, error_type=None, error_data=None, error_info=None):
        self.message = message
        self.error_type = error_type
        self.error_data = error_data
        self.error_info = error_info
        super().__init__()

    def __str__(self):
        return self.message
