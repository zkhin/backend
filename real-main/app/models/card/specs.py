class CommentCardSpec:

    title = 'You have new comments'
    action = 'https://real.app/chat/'

    def __init__(self, user_id):
        self.user_id = user_id
        self.card_id = f'{self.user_id}:COMMENT_ACTIVITY'


class ChatCardSpec:

    title = 'You have new messages'
    action = 'https://real.app/chat/'

    def __init__(self, user_id):
        self.user_id = user_id
        self.card_id = f'{self.user_id}:CHAT_ACTIVITY'
