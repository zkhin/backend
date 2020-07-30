import pendulum


class CardTemplate:

    title = None
    action = None
    notify_user_after = None
    sub_title = None
    target_item_id = None
    extra_fields = {}
    only_usernames = ()

    def __init__(self, user_id):
        self.user_id = user_id


class ChatCardTemplate(CardTemplate):

    action = 'https://real.app/chat/'
    notify_user_after = pendulum.duration(minutes=5)

    @staticmethod
    def get_card_id(user_id):
        return f'{user_id}:CHAT_ACTIVITY'

    def __init__(self, user_id, chats_with_unviewed_messages_count):
        super().__init__(user_id)
        self.card_id = self.get_card_id(user_id)
        cnt = chats_with_unviewed_messages_count
        self.title = f'You have {cnt} chat{"s" if cnt > 1 else ""} with new messages'


class CommentCardTemplate(CardTemplate):

    notify_user_after = pendulum.duration(hours=24)

    @staticmethod
    def get_card_id(user_id, post_id):
        return f'{user_id}:COMMENT_ACTIVITY:{post_id}'

    def __init__(self, user_id, post_id, unviewed_comments_count):
        super().__init__(user_id)
        self.card_id = self.get_card_id(user_id, post_id)
        self.action = f'https://real.app/user/{user_id}/post/{post_id}/comments'
        cnt = unviewed_comments_count
        self.title = f'You have {cnt} new comment{"s" if cnt > 1 else ""}'
        self.extra_fields = {'postId': post_id}
        self.target_item_id = post_id


class PostLikesCardTemplate(CardTemplate):

    title = 'You have new likes'
    notify_user_after = pendulum.duration(hours=24)

    @staticmethod
    def get_card_id(user_id, post_id):
        return f'{user_id}:POST_LIKES:{post_id}'

    def __init__(self, user_id, post_id):
        super().__init__(user_id)
        self.card_id = self.get_card_id(user_id, post_id)
        self.action = f'https://real.app/user/{user_id}/post/{post_id}/likes'
        self.extra_fields = {'postId': post_id}
        self.target_item_id = post_id


class PostMentionCardTemplate(CardTemplate):

    notify_user_after = pendulum.duration(hours=24)

    @staticmethod
    def get_card_id(user_id, post_id):
        return f'{user_id}:POST_MENTION:{post_id}'

    def __init__(self, user_id, post):
        super().__init__(user_id)
        self.card_id = self.get_card_id(user_id, post.id)
        self.action = f'https://real.app/user/{post.user_id}/post/{post.id}'
        self.title = f'@{post.user.username} tagged you in a post'
        self.extra_fields = {'postId': post.id}
        self.target_item_id = post.id


class PostViewsCardTemplate(CardTemplate):

    title = 'You have new views'
    notify_user_after = pendulum.duration(hours=24)

    @staticmethod
    def get_card_id(user_id, post_id):
        return f'{user_id}:POST_VIEWS:{post_id}'

    def __init__(self, user_id, post_id):
        super().__init__(user_id)
        self.card_id = self.get_card_id(user_id, post_id)
        self.action = f'https://real.app/user/{user_id}/post/{post_id}/views'
        self.extra_fields = {'postId': post_id}
        self.target_item_id = post_id


class RequestedFollowersCardTemplate(CardTemplate):

    action = 'https://real.app/chat/'
    notify_user_after = pendulum.duration(hours=24)

    @staticmethod
    def get_card_id(user_id):
        return f'{user_id}:REQUESTED_FOLLOWERS'

    def __init__(self, user_id, requested_followers_count):
        super().__init__(user_id)
        self.card_id = self.get_card_id(user_id)
        cnt = requested_followers_count
        self.title = f'You have {cnt} pending follow request{"s" if cnt > 1 else ""}'
