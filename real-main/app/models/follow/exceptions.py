class FollowException(Exception):
    pass


class AlreadyFollowing(FollowException):
    def __init__(self, follower_user_id, followed_user_id):
        self.follower_user_id = follower_user_id
        self.followed_user_id = followed_user_id
        super().__init__()

    def __str__(self):
        return f'User `{self.follower_user_id}` is or already requested following user `{self.followed_user_id}`'


class FollowingDoesNotExist(FollowException):
    def __init__(self, follower_user_id, followed_user_id):
        self.follower_user_id = follower_user_id
        self.followed_user_id = followed_user_id
        super().__init__()

    def __str__(self):
        return f'No following from `{self.follower_user_id}` to user `{self.followed_user_id}` found'


class AlreadyHasStatus(FollowException):
    def __init__(self, follower_user_id, followed_user_id, follow_status):
        self.follower_user_id = follower_user_id
        self.followed_user_id = followed_user_id
        self.follow_status = follow_status
        super().__init__()

    def __str__(self):
        return (
            f'Following from user `{self.follower_user_id}` to user `{self.followed_user_id}` '
            + f'already has status `{self.follow_status}`'
        )
