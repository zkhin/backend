class AppStoreSubscriptionStatus:
    # Note: we do not have a grace period configured at this time
    ACTIVE = 'ACTIVE'
    EXPIRED = 'EXPIRED'
    CANCELLED = 'CANCELLED'

    _ALL = (ACTIVE, EXPIRED, CANCELLED)


class PricePlan:
    SUBSCRIPTION_DIAMOND = 'SUBSCRIPTION_DIAMOND'

    _ALL = SUBSCRIPTION_DIAMOND
