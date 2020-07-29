import logging
from functools import partialmethod

import pendulum

from app import models

from . import templates
from .appsync import CardAppSync
from .dynamo import CardDynamo
from .enums import CardNotificationType
from .exceptions import CardAlreadyExists
from .model import Card

logger = logging.getLogger()


class CardManager:
    def __init__(self, clients, managers=None):
        managers = managers or {}
        managers['card'] = self
        self.post_manager = managers.get('post') or models.PostManager(clients, managers=managers)
        self.user_manager = managers.get('user') or models.UserManager(clients, managers=managers)

        if 'appsync' in clients:
            self.appsync = CardAppSync(clients['appsync'])
        if 'dynamo' in clients:
            self.dynamo = CardDynamo(clients['dynamo'])
        if 'pinpoint' in clients:
            self.pinpoint_client = clients['pinpoint']

    def get_card(self, card_id, strongly_consistent=False):
        item = self.dynamo.get_card(card_id, strongly_consistent=strongly_consistent)
        return self.init_card(item) if item else None

    def init_card(self, item):
        kwargs = {
            'appsync': getattr(self, 'appsync', None),
            'dynamo': getattr(self, 'dynamo', None),
            'pinpoint_client': getattr(self, 'pinpoint_client', None),
            'post_manager': self.post_manager,
            'user_manager': self.user_manager,
        }
        return Card(item, **kwargs)

    def add_or_update_card(self, template, now=None):
        if template.only_usernames:
            user = self.user_manager.get_user(template.user_id)
            if not (user and user.username in template.only_usernames):
                return None

        created_at = now or pendulum.now('utc')
        notify_user_at = (
            created_at + template.notify_user_after if template.notify_user_after is not None else None
        )

        try:
            card_item = self.dynamo.add_card(
                template.card_id,
                template.user_id,
                template.title,
                template.action,
                created_at=created_at,
                notify_user_at=notify_user_at,
                post_id=template.post_id,
                sub_title=template.sub_title,
            )
        except CardAlreadyExists:
            card_item = self.dynamo.update_title(template.card_id, template.title)
        return self.init_card(card_item)

    def delete_post_cards(self, user_id, post_id):
        "Delete all cards associated with a given post for a given user"
        card_templates = (
            templates.CommentCardTemplate(user_id, post_id),
            templates.PostLikesCardTemplate(user_id, post_id),
            templates.PostViewsCardTemplate(user_id, post_id),
        )
        key_generator = (self.dynamo.pk(template.card_id) for template in card_templates)
        self.dynamo.client.batch_delete_items(key_generator)

    def notify_users(self, now=None, only_usernames=None):
        """
        Send out push notifications to all users for cards as needed.
        Use `only_usernames` if you don't want to send notifcations to all users.
        """
        # determine which users we should be sending notifcations to, if we're only doing some
        if only_usernames is None:
            only_user_ids = None
        elif only_usernames == []:
            return 0, 0
        else:
            only_users = [self.user_manager.get_user_by_username(username) for username in only_usernames]
            only_user_ids = [user.id for user in only_users if user]

        # send on notifcations for cards for those users
        now = pendulum.now('utc')
        total_count, success_count = 0, 0
        for card_id in self.dynamo.generate_card_ids_by_notify_user_at(now, only_user_ids=only_user_ids):
            card = self.get_card(card_id)
            success_count += card.notify_user()
            total_count += 1
            card.clear_notify_user_at()
        return total_count, success_count

    def on_card_add(self, card_id, new_item):
        self.init_card(new_item).trigger_notification(CardNotificationType.ADDED)

    def on_card_edit(self, card_id, new_item, old_item):
        self.init_card(new_item).trigger_notification(CardNotificationType.EDITED)

    def on_card_delete(self, card_id, old_item):
        self.init_card(old_item).trigger_notification(CardNotificationType.DELETED)

    def on_post_delete_delete_cards(self, post_id, old_item):
        user_id = old_item['postedByUserId']
        self.delete_post_cards(user_id, post_id)

    def on_user_delete_delete_cards(self, user_id, old_item):
        generator = self.dynamo.generate_cards_by_user(user_id, pks_only=True)
        self.dynamo.client.batch_delete_items(generator)

    def on_user_count_change_sync_card(self, dynamo_attr, card_template_class, user_id, new_item, old_item=None):
        cnt = new_item.get(dynamo_attr, 0)
        card_template = card_template_class(user_id, cnt)
        if cnt > 0:
            self.add_or_update_card(card_template)
        else:
            self.dynamo.delete_card(card_template.card_id)

    on_user_followers_requested_count_change_sync_card = partialmethod(
        on_user_count_change_sync_card, 'followersRequestedCount', templates.RequestedFollowersCardTemplate,
    )
    on_user_chats_with_unviewed_messages_count_change_sync_card = partialmethod(
        on_user_count_change_sync_card, 'chatsWithUnviewedMessagesCount', templates.ChatCardTemplate,
    )

    def on_post_view_count_change_update_cards(self, post_id, new_item, old_item=None):
        if new_item.get('viewCount', 0) <= (old_item or {}).get('viewCount', 0):
            return  # view count did not increase

        _, viewed_by_user_id = new_item['sortKey'].split('/')
        post = self.post_manager.get_post(post_id)
        if not post or post.user_id != viewed_by_user_id:
            return  # not viewed by post owner

        self.delete_post_cards(post.user_id, post_id)

    def on_post_comments_unviewed_count_change_update_card(self, post_id, new_item, old_item=None):
        new_cnt = new_item.get('commentsUnviewedCount', 0)
        user_id = new_item['postedByUserId']
        card_template = templates.CommentCardTemplate(user_id, post_id, unviewed_comments_count=new_cnt)
        if new_cnt > 0:
            self.add_or_update_card(card_template)
        else:
            self.dynamo.delete_card(card_template.card_id)

    def on_post_likes_count_change_update_card(self, post_id, new_item, old_item=None):
        new_cnt = new_item.get('onymousLikeCount', 0) + new_item.get('anonymousLikeCount', 0)
        # post likes card should be created on any new like up to but not including the 10th like
        if 0 < new_cnt < 10:
            user_id = new_item['postedByUserId']
            card_template = templates.PostLikesCardTemplate(user_id, post_id)
            self.add_or_update_card(card_template)

    def on_post_viewed_by_count_change_update_card(self, post_id, new_item, old_item=None):
        new_cnt = new_item.get('viewedByCount', 0)
        old_cnt = (old_item or {}).get('viewedByCount', 0)
        # post views card should only be created once per post, when it goes over 5 views
        if new_cnt > 5 and old_cnt <= 5:
            user_id = new_item['postedByUserId']
            card_template = templates.PostViewsCardTemplate(user_id, post_id)
            self.add_or_update_card(card_template)
