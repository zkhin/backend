import pendulum


class CardTemplate:
    pass


class ChatCardTemplate(CardTemplate):

    action = 'https://real.app/chat/'
    post_id = None
    notify_user_after = pendulum.duration(minutes=5)

    def __init__(self, user_id, chats_with_unviewed_messages_count=None):
        self.user_id = user_id
        self.card_id = f'{user_id}:CHAT_ACTIVITY'
        if chats_with_unviewed_messages_count is not None:
            cnt = chats_with_unviewed_messages_count
            self.title = f'You have {cnt} chat{"s" if cnt > 1 else ""} with new messages'


class CommentCardTemplate(CardTemplate):

    notify_user_after = pendulum.duration(hours=24)

    def __init__(self, user_id, post_id, unviewed_comments_count=None):
        self.post_id = post_id
        self.user_id = user_id
        self.card_id = f'{user_id}:COMMENT_ACTIVITY:{post_id}'
        self.action = f'https://real.app/user/{user_id}/post/{post_id}/comments'
        if unviewed_comments_count is not None:
            cnt = unviewed_comments_count
            self.title = f'You have {cnt} new comment{"s" if cnt > 1 else ""}'


class PostLikesCardTemplate(CardTemplate):

    notify_user_after = pendulum.duration(hours=24)
    only_usernames = ('azim', 'ian', 'mike')

    def __init__(self, user_id, post_id):
        self.post_id = post_id
        self.user_id = user_id
        self.card_id = f'{user_id}:POST_LIKES:{post_id}'
        self.action = f'https://real.app/user/{user_id}/post/{post_id}/likes'
        self.title = 'You have new likes'


class PostViewsCardTemplate(CardTemplate):

    notify_user_after = pendulum.duration(hours=24)
    only_usernames = ('azim', 'ian', 'mike')

    def __init__(self, user_id, post_id):
        self.post_id = post_id
        self.user_id = user_id
        self.card_id = f'{user_id}:POST_VIEWS:{post_id}'
        self.action = f'https://real.app/user/{user_id}/post/{post_id}/views'
        self.title = 'You have new views'


class RequestedFollowersCardTemplate(CardTemplate):

    action = 'https://real.app/chat/'
    post_id = None
    notify_user_after = pendulum.duration(hours=24)

    def __init__(self, user_id, requested_followers_count=None):
        self.user_id = user_id
        self.card_id = f'{user_id}:REQUESTED_FOLLOWERS'
        if requested_followers_count is not None:
            cnt = requested_followers_count
            self.title = f'You have {cnt} pending follow request{"s" if cnt > 1 else ""}'
