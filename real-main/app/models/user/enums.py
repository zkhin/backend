class UserStatus:
    ACTIVE = 'ACTIVE'
    ANONYMOUS = 'ANONYMOUS'
    DISABLED = 'DISABLED'
    DELETING = 'DELETING'
    RESETTING = 'RESETTING'

    _ALL = (ACTIVE, ANONYMOUS, DISABLED, DELETING, RESETTING)


class UserPrivacyStatus:
    PRIVATE = 'PRIVATE'
    PUBLIC = 'PUBLIC'

    _ALL = (PRIVATE, PUBLIC)


class UserSubscriptionLevel:
    BASIC = 'BASIC'
    DIAMOND = 'DIAMOND'

    _ALL = (BASIC, DIAMOND)
    _PAID = (DIAMOND,)


class UserGender:
    MALE = 'MALE'
    FEMALE = 'FEMALE'

    _ALL = (MALE, FEMALE)


class UserDatingStatus:
    ENABLED = 'ENABLED'
    DISABLED = 'DISABLED'

    _ALL = (ENABLED, DISABLED)


class SubscriptionGrantCode:
    FREE_FOR_LIFE = 'FREE_FOR_LIFE'

    _ALL = FREE_FOR_LIFE


class IdVerificationImageType:
    JPEG = 'JPEG'
    PNG = 'PNG'

    _ALL = (JPEG, PNG)


class IdVerificationStatus:
    APPROVED = 'APPROVED'
    REJECTED = 'REJECTED'
    SUBMITTED = 'SUBMITTED'
    ERROR = 'ERROR'

    _ALL = (APPROVED, REJECTED, SUBMITTED, ERROR)
