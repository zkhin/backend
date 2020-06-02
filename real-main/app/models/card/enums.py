class _WellKnownCard:
    def __init__(self, name, title, action):
        self.name = name
        self.title = title
        self.action = action

    def get_card_id(self, user_id):
        return f'{user_id}:{self.name}'


COMMENT_ACTIVITY_CARD = _WellKnownCard(
    'COMMENT_ACTIVITY', 'You have new comment activity', 'https://real.app/comment/',
)
CHAT_ACTIVITY_CARD = _WellKnownCard('CHAT_ACTIVITY', 'You have new chat activity', 'https://real.app/chat/')
