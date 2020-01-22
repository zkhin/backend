import string

import pytest

from app.models.user.validate import UserValidate
from app.models.user.exceptions import UserValidationException


@pytest.fixture
def user_validate():
    yield UserValidate()


def test_empty_username_fails_validation(user_validate):
    with pytest.raises(UserValidationException):
        user_validate.username(None)

    with pytest.raises(UserValidationException):
        user_validate.username('')


def test_username_length_fails_validation(user_validate):
    with pytest.raises(UserValidationException):
        user_validate.username('a' * 31)

    with pytest.raises(UserValidationException):
        user_validate.username('aa')


def test_username_bad_chars_fails_validation(user_validate):
    bad_chars = set(string.printable) - set(string.digits + string.ascii_letters + '_.')
    for bad_char in bad_chars:
        with pytest.raises(UserValidationException):
            user_validate.username('aaa' + bad_char)
        with pytest.raises(UserValidationException):
            user_validate.username(bad_char + 'aaa')
        with pytest.raises(UserValidationException):
            user_validate.username(bad_char * 3)


def test_good_username_validates(user_validate):
    user_validate.username('buzz_lightyear')
    user_validate.username('buzz.lightyear')
    user_validate.username('UpAndOver')
    user_validate.username('__.0009A_...')
