from unittest.mock import Mock, call
from uuid import uuid4

import pytest


@pytest.fixture
def user_postprocessor(user_manager):
    yield user_manager.postprocessor


def test_run(user_postprocessor):
    # use simulated update to disable a user
    user_id = str(uuid4())
    pk = f'user/{user_id}'
    sk = 'profile'
    old_item = {'userId': {'S': user_id}}
    new_item = {'userId': {'S': user_id}}

    user_postprocessor.handle_elasticsearch = Mock(user_postprocessor.handle_elasticsearch)
    user_postprocessor.handle_pinpoint = Mock(user_postprocessor.handle_pinpoint)
    user_postprocessor.handle_requested_followers_card = Mock(user_postprocessor.handle_requested_followers_card)
    user_postprocessor.run(pk, sk, old_item, new_item)
    assert user_postprocessor.handle_elasticsearch.mock_calls == [call(old_item, new_item)]
    assert user_postprocessor.handle_pinpoint.mock_calls == [call(user_id, old_item, new_item)]
    assert user_postprocessor.handle_requested_followers_card.mock_calls == [call(user_id, old_item, new_item)]
