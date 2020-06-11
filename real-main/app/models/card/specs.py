class CardSpec:
    def __eq__(self, other):
        return self.card_id == other.card_id


class CommentCardSpec(CardSpec):

    title = 'You have new comments'

    def __init__(self, user_id, post_id):
        self.post_id = post_id
        self.user_id = user_id
        self.card_id = f'{user_id}:COMMENT_ACTIVITY:{post_id}'
        self.action = f'https://real.app/chat/post/{post_id}'


class ChatCardSpec(CardSpec):

    title = 'You have new messages'
    action = 'https://real.app/chat/'

    def __init__(self, user_id):
        self.user_id = user_id
        self.card_id = f'{user_id}:CHAT_ACTIVITY'
