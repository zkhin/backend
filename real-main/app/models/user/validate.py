import logging
import string

from .exceptions import UserValidationException

logger = logging.getLogger()


class UserValidate:

    def username(self, username):
        if not username:
            raise UserValidationException('Empty username')

        min_length, max_length = 3, 30  # same as instagram
        if len(username) < min_length:
            raise UserValidationException(f'Username too short {len(username)} < {min_length}')
        if len(username) > max_length:
            raise UserValidationException(f'Username too long {len(username)} > {max_length}')

        allowed_chars = set(string.ascii_letters + string.digits + '_.')
        if not set(username) <= allowed_chars:
            raise UserValidationException(
                f'Username `{username}` contains invalid chars (ie. non-alphanumeric, underscore or dot)'
            )
