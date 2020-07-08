import re

import pendulum

from .exceptions import MalformedCardId


class CardSpec:

    comment_card_id_re = r'^([\w:-]+):COMMENT_ACTIVITY:([\w-]+)$'
    chat_card_id_re = r'^([\w:-]+):CHAT_ACTIVITY$'
    post_views_card_id_re = r'^([\w:-]+):POST_VIEWS:([\w-]+)$'
    requested_followers_card_id_re = r'^([\w:-]+):REQUESTED_FOLLOWERS$'

    @classmethod
    def from_card_id(cls, card_id):
        if card_id and 'COMMENT_ACTIVITY' in card_id:
            m = re.search(cls.comment_card_id_re, card_id)
            if not m:
                raise MalformedCardId(card_id)
            user_id, post_id = m.group(1), m.group(2)
            return CommentCardSpec(user_id, post_id)

        if card_id and 'POST_VIEWS' in card_id:
            m = re.search(cls.post_views_card_id_re, card_id)
            if not m:
                raise MalformedCardId(card_id)
            user_id, post_id = m.group(1), m.group(2)
            return PostViewsCardSpec(user_id, post_id)

        if card_id and 'CHAT_ACTIVITY' in card_id:
            m = re.search(cls.chat_card_id_re, card_id)
            if not m:
                raise MalformedCardId(card_id)
            user_id = m.group(1)
            return ChatCardSpec(user_id)

        if card_id and 'REQUESTED_FOLLOWERS' in card_id:
            m = re.search(cls.requested_followers_card_id_re, card_id)
            if not m:
                raise MalformedCardId(card_id)
            user_id = m.group(1)
            return RequestedFollowersCardSpec(user_id)

        return None


class CommentCardSpec(CardSpec):

    notify_user_after = pendulum.duration(hours=24)

    def __init__(self, user_id, post_id, unviewed_comments_count=None):
        self.post_id = post_id
        self.user_id = user_id
        self.card_id = f'{user_id}:COMMENT_ACTIVITY:{post_id}'
        self.action = f'https://real.app/user/{user_id}/post/{post_id}/comments'
        if unviewed_comments_count is not None:
            cnt = unviewed_comments_count
            self.title = f'You have {cnt} new comment{"s" if cnt > 1 else ""}'


class ChatCardSpec(CardSpec):

    action = 'https://real.app/chat/'
    post_id = None
    notify_user_after = pendulum.duration(minutes=5)

    def __init__(self, user_id, chats_with_unviewed_messages_count=None):
        self.user_id = user_id
        self.card_id = f'{user_id}:CHAT_ACTIVITY'
        if chats_with_unviewed_messages_count is not None:
            cnt = chats_with_unviewed_messages_count
            self.title = f'You have {cnt} chat{"s" if cnt > 1 else ""} with new messages'


class PostViewsCardSpec(CardSpec):

    notify_user_after = pendulum.duration(hours=24)

    def __init__(self, user_id, post_id):
        self.post_id = post_id
        self.user_id = user_id
        self.card_id = f'{user_id}:POST_VIEWS:{post_id}'
        self.action = f'https://real.app/user/{user_id}/post/{post_id}/views'
        self.title = 'You have new views'


class RequestedFollowersCardSpec(CardSpec):

    action = 'https://real.app/chat/'
    post_id = None
    notify_user_after = None

    def __init__(self, user_id, requested_followers_count=None):
        self.user_id = user_id
        self.card_id = f'{user_id}:REQUESTED_FOLLOWERS'
        if requested_followers_count is not None:
            cnt = requested_followers_count
            self.title = f'You have {cnt} pending follow request{"s" if cnt > 1 else ""}'
