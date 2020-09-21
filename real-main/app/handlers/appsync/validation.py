from app.models.user.enums import UserSubscriptionLevel

from .exceptions import ClientException


def validate_match_location_radius(match_location_radius, caller_user):
    if match_location_radius < 15:
        raise ClientException('MatchLocationRadius should be greater than or equal to 15')
    if caller_user.subscription_level == UserSubscriptionLevel.BASIC and match_location_radius > 100:
        raise ClientException('MatchLocationRadius should be less than or equal to 100')
    return True


def validate_age_range(match_age_range):
    minAge = match_age_range.get('min')
    maxAge = match_age_range.get('max')

    if minAge > maxAge or minAge < 18 or maxAge > 100:
        raise ClientException('Invalid matchAgeRange')
    return True


def validate_current_location(current_location):
    latitude = current_location.get('latitude')
    longitude = current_location.get('longitude')
    accuracy = current_location.get('accuracy', 0)

    if latitude > 90 or latitude < -90:
        raise ClientException('Latitude should be in [-90, 90]')
    if longitude > 180 or longitude < -180:
        raise ClientException('Longitude should be in [-180, 180]')
    if accuracy < 0:
        raise ClientException('Accuracy should be greater than or equal to zero')
    return True
