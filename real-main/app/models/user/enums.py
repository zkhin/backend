class UserStatus:
    ACTIVE = 'ACTIVE'
    DISABLED = 'DISABLED'
    DELETING = 'DELETING'

    _ALL = (ACTIVE, DISABLED, DELETING)


class UserPrivacyStatus:
    PRIVATE = 'PRIVATE'
    PUBLIC = 'PUBLIC'

    _ALL = (PRIVATE, PUBLIC)
