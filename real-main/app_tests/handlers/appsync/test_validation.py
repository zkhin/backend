import pytest

from app.handlers.appsync.exceptions import ClientException
from app.handlers.appsync.validation import (
    validate_age_range,
    validate_current_location,
    validate_match_location_radius,
)
from app.models.user.enums import UserSubscriptionLevel


def test_validate_match_location_radius():
    # Case 1
    match_location_radius = 14

    with pytest.raises(ClientException, match='matchLocationRadius'):
        validate_match_location_radius(match_location_radius, UserSubscriptionLevel.BASIC)

    with pytest.raises(ClientException, match='matchLocationRadius'):
        validate_match_location_radius(match_location_radius, UserSubscriptionLevel.DIAMOND)

    # Case 2
    match_location_radius = 15

    assert validate_match_location_radius(match_location_radius, UserSubscriptionLevel.BASIC) is True
    assert validate_match_location_radius(match_location_radius, UserSubscriptionLevel.DIAMOND) is True

    # Case 3
    match_location_radius = 50

    assert validate_match_location_radius(match_location_radius, UserSubscriptionLevel.BASIC) is True
    assert validate_match_location_radius(match_location_radius, UserSubscriptionLevel.DIAMOND) is True

    # Case 4
    match_location_radius = 100

    assert validate_match_location_radius(match_location_radius, UserSubscriptionLevel.BASIC) is True
    assert validate_match_location_radius(match_location_radius, UserSubscriptionLevel.DIAMOND) is True

    # Case 5
    match_location_radius = 101

    with pytest.raises(ClientException, match='matchLocationRadius'):
        validate_match_location_radius(match_location_radius, UserSubscriptionLevel.BASIC)
    assert validate_match_location_radius(match_location_radius, UserSubscriptionLevel.DIAMOND) is True


def test_validate_age_range():
    valid_match_age_range_1 = {"min": 20, "max": 50}
    valid_match_age_range_2 = {"min": 18, "max": 100}
    invalid_match_age_range_1 = {"min": 100, "max": 50}
    invalid_match_age_range_2 = {"min": 17, "max": 100}
    invalid_match_age_range_3 = {"min": 17, "max": 101}
    invalid_match_age_range_4 = {"min": 18, "max": 101}

    # Pass the validation
    assert validate_age_range(valid_match_age_range_1) is True
    assert validate_age_range(valid_match_age_range_2) is True

    # Raise client exception
    with pytest.raises(ClientException, match='matchAgeRange'):
        validate_age_range(invalid_match_age_range_1)

    with pytest.raises(ClientException, match='matchAgeRange'):
        validate_age_range(invalid_match_age_range_2)

    with pytest.raises(ClientException, match='matchAgeRange'):
        validate_age_range(invalid_match_age_range_3)

    with pytest.raises(ClientException, match='matchAgeRange'):
        validate_age_range(invalid_match_age_range_4)


def test_validate_current_location():
    # Case 1
    current_location = {"latitude": -90, "longitude": -180, "accuracy": -1}

    with pytest.raises(ClientException, match='accuracy'):
        validate_current_location(current_location)

    # Case 2
    current_location = {"latitude": 90, "longitude": 180, "accuracy": 1}
    assert validate_current_location(current_location) is True

    # Case 3
    current_location = {"latitude": 0, "longitude": 0, "accuracy": 42}
    assert validate_current_location(current_location) is True

    # Case 4
    current_location = {"latitude": -90.1, "longitude": -180.1, "accuracy": None}

    with pytest.raises(ClientException, match='latitude'):
        validate_current_location(current_location)

    # Case 5
    current_location = {"latitude": 90.1, "longitude": 180.1}

    with pytest.raises(ClientException, match='latitude'):
        validate_current_location(current_location)
