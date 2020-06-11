import re

from .exceptions import MalformedCardId


class CardSpec:

    comment_card_id_re = r'^([\w:-]+):COMMENT_ACTIVITY:([\w-]+)$'
    chat_card_id_re = r'^([\w:-]+):CHAT_ACTIVITY$'

    @classmethod
    def from_card_id(cls, card_id):
        if card_id and 'COMMENT_ACTIVITY' in card_id:
            m = re.search(cls.comment_card_id_re, card_id)
            if not m:
                raise MalformedCardId(card_id)
            user_id, post_id = m.group(1), m.group(2)
            return CommentCardSpec(user_id, post_id)

        if card_id and 'CHAT_ACTIVITY' in card_id:
            m = re.search(cls.chat_card_id_re, card_id)
            if not m:
                raise MalformedCardId(card_id)
            user_id = m.group(1)
            return ChatCardSpec(user_id)

        return None

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
    post_id = None

    def __init__(self, user_id):
        self.user_id = user_id
        self.card_id = f'{user_id}:CHAT_ACTIVITY'
