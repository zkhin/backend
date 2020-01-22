import logging
import re

from .exceptions import UserValidationException

logger = logging.getLogger()


class UserValidate:

    # username restrictions: same as instagram
    username_regex = re.compile('[a-zA-Z0-9_.]{3,30}')

    def username(self, username):
        if not username:
            raise UserValidationException('Empty username')
        matched_username = self.username_regex.match(username)  # matches only from beginging of string
        if not matched_username or matched_username[0] != username:
            raise UserValidationException(f'Username `{username}` does not validate')
