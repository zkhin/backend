class CardNotificationType:
    ADDED = 'ADDED'
    DELETED = 'DELETED'

    _ALL = (ADDED, DELETED)


class _WellKnownCard:
    def __init__(self, name, title, action):
        self.name = name
        self.title = title
        self.action = action

    def get_card_id(self, user_id):
        return f'{user_id}:{self.name}'


# these both say 'new', but more accurate would be 'new, edited or deleted'
COMMENT_ACTIVITY_CARD = _WellKnownCard('COMMENT_ACTIVITY', 'You have new comments', 'https://real.app/chat/',)
CHAT_ACTIVITY_CARD = _WellKnownCard('CHAT_ACTIVITY', 'You have new messages', 'https://real.app/chat/')
