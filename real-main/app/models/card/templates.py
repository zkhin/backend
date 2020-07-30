import pendulum


class CardTemplate:

    notify_user_after = None
    sub_title = None
    extra_fields = {}
    only_usernames = ()

    def __init__(self, user_id):
        self.user_id = user_id


class ChatCardTemplate(CardTemplate):

    action = 'https://real.app/chat/'
    notify_user_after = pendulum.duration(minutes=5)

    def __init__(self, user_id, chats_with_unviewed_messages_count=None):
        super().__init__(user_id)
        self.card_id = f'{user_id}:CHAT_ACTIVITY'
        self.cnt = chats_with_unviewed_messages_count
        self.title = (
            f'You have {self.cnt} chat{"s" if self.cnt > 1 else ""} with new messages'
            if self.cnt is not None
            else None
        )


class CommentCardTemplate(CardTemplate):

    notify_user_after = pendulum.duration(hours=24)

    def __init__(self, user_id, post_id, unviewed_comments_count=None):
        super().__init__(user_id)
        self.card_id = f'{user_id}:COMMENT_ACTIVITY:{post_id}'
        self.cnt = unviewed_comments_count
        self.action = f'https://real.app/user/{user_id}/post/{post_id}/comments'
        self.title = (
            f'You have {self.cnt} new comment{"s" if self.cnt > 1 else ""}' if self.cnt is not None else None
        )
        self.extra_fields = {'postId': post_id}


class PostLikesCardTemplate(CardTemplate):

    title = 'You have new likes'
    notify_user_after = pendulum.duration(hours=24)
    only_usernames = ('azim', 'ian', 'mike')

    def __init__(self, user_id, post_id):
        super().__init__(user_id)
        self.card_id = f'{user_id}:POST_LIKES:{post_id}'
        self.action = f'https://real.app/user/{user_id}/post/{post_id}/likes'
        self.extra_fields = {'postId': post_id}


class PostViewsCardTemplate(CardTemplate):

    title = 'You have new views'
    notify_user_after = pendulum.duration(hours=24)
    only_usernames = ('azim', 'ian', 'mike')

    def __init__(self, user_id, post_id):
        super().__init__(user_id)
        self.card_id = f'{user_id}:POST_VIEWS:{post_id}'
        self.action = f'https://real.app/user/{user_id}/post/{post_id}/views'
        self.extra_fields = {'postId': post_id}


class RequestedFollowersCardTemplate(CardTemplate):

    action = 'https://real.app/chat/'
    notify_user_after = pendulum.duration(hours=24)

    def __init__(self, user_id, requested_followers_count=None):
        super().__init__(user_id)
        self.card_id = f'{user_id}:REQUESTED_FOLLOWERS'
        self.cnt = requested_followers_count
        self.title = (
            f'You have {self.cnt} pending follow request{"s" if self.cnt > 1 else ""}'
            if self.cnt is not None
            else None
        )
