class UserStatus:
    ACTIVE = 'ACTIVE'
    DISABLED = 'DISABLED'
    DELETING = 'DELETING'
    RESETTING = 'RESETTING'

    _ALL = (ACTIVE, DISABLED, DELETING, RESETTING)


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
