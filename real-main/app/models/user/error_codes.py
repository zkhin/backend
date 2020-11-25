from enum import Enum


class UserDatingMissingError(Enum):
    fullName = 'MISSING_FULL_NAME'
    photoPostId = 'MISSING_PHOTO_POST_ID'
    age = 'MISSING_AGE'
    gender = 'MISSING_GENDER'
    location = 'MISSING_LOCATION'
    height = 'MISSING_HEIGHT'
    matchAgeRange = 'MISSING_MATCH_AGE_RANGE'
    matchGenders = 'MISSING_MATCH_GENDERS'
    matchHeightRange = 'MISSING_MATCH_HEIGHT_RANGE'


class UserDatingWrongError(Enum):
    minAge = 'WRONG_AGE_MIN'
    maxAge = 'WRONG_AGE_MAX'
