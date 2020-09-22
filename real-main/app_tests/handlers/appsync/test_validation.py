from decimal import Decimal

import pytest

from app.handlers.appsync.exceptions import ClientException
from app.handlers.appsync.validation import (
    validate_age_range,
    validate_current_location,
    validate_match_location_radius,
)
from app.models.user.enums import UserSubscriptionLevel


def test_validate_match_location_radius():
    valid_match_location_radius = Decimal('25')
    invalid_match_location_radius = Decimal('10')

    # Pass the validation
    assert validate_match_location_radius(valid_match_location_radius, UserSubscriptionLevel.BASIC) is True

    valid_match_location_radius = Decimal('200')
    assert validate_match_location_radius(valid_match_location_radius, UserSubscriptionLevel.DIAMOND) is True

    # Raise client exception
    with pytest.raises(ClientException):
        validate_match_location_radius(invalid_match_location_radius, UserSubscriptionLevel.DIAMOND)

    invalid_match_location_radius = Decimal('200')

    with pytest.raises(ClientException):
        validate_match_location_radius(invalid_match_location_radius, UserSubscriptionLevel.BASIC)


def test_validate_age_range():
    valid_match_age_range = {"min": Decimal('20'), "max": Decimal('50')}
    invalid_match_age_range = {"min": Decimal('100'), "max": Decimal('50')}

    # Pass the validation
    assert validate_age_range(valid_match_age_range) is True

    # Raise client exception
    with pytest.raises(ClientException):
        validate_age_range(invalid_match_age_range)


def test_validate_current_location():
    valid_current_location = {"latitude": Decimal('50'), "longitude": Decimal('50'), "accuracy": Decimal('50')}
    invalid_current_location_1 = {
        "latitude": Decimal('-100'),
        "longitude": Decimal('50'),
        "accuracy": Decimal('50'),
    }
    invalid_current_location_2 = {
        "latitude": Decimal('50'),
        "longitude": Decimal('200'),
        "accuracy": Decimal('50'),
    }
    invalid_current_location_3 = {
        "latitude": Decimal('50'),
        "longitude": Decimal('200'),
        "accuracy": Decimal('-10'),
    }

    # Pass the validation
    assert validate_current_location(valid_current_location) is True

    # Raise client exception
    with pytest.raises(ClientException):
        validate_current_location(invalid_current_location_1)

    with pytest.raises(ClientException):
        validate_current_location(invalid_current_location_2)

    with pytest.raises(ClientException):
        validate_current_location(invalid_current_location_3)
