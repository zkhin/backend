from unittest.mock import call, Mock

import pytest


@pytest.fixture
def album(album_manager, user_manager):
    user = user_manager.create_cognito_only_user('uid', 'uname')
    album = album_manager.add_album(user.id, 'aid', 'album name')

    # mock out a bunch of stuff, each test will change the configuration
    album.post_manager.dynamo.generate_post_ids_in_album = Mock()
    album.update_art_images_one_post = Mock()
    album.update_art_images_grid = Mock()
    album.delete_art_images = Mock()

    yield album


def test_update_art_if_needed_no_change_no_posts(album):
    # do the update
    album.post_manager.dynamo.generate_post_ids_in_album.return_value = []
    album.update_art_if_needed()

    # verify calls
    'artHash' not in album.item
    assert album.post_manager.dynamo.generate_post_ids_in_album.mock_calls == [call(album.id, completed=True)]
    assert album.update_art_images_one_post.mock_calls == []
    assert album.update_art_images_grid.mock_calls == []
    assert album.delete_art_images.mock_calls == []


def test_update_art_if_needed_add_first_post(album):
    # update art
    album.post_manager.dynamo.generate_post_ids_in_album.return_value = ['a']
    album.update_art_if_needed()

    # verify calls
    assert album.item['artHash']
    assert album.post_manager.dynamo.generate_post_ids_in_album.mock_calls == [call(album.id, completed=True)]
    assert album.update_art_images_one_post.mock_calls == [call(album.item['artHash'], 'a')]
    assert album.update_art_images_grid.mock_calls == []
    assert album.delete_art_images.mock_calls == []


def test_update_art_if_needed_remove_last_post(album):
    # update art
    art_hash = 'hashhash'
    album.item['artHash'] = art_hash
    album.post_manager.dynamo.generate_post_ids_in_album.return_value = []
    album.update_art_if_needed()

    # verify calls
    'artHash' not in album.item
    assert album.post_manager.dynamo.generate_post_ids_in_album.mock_calls == [call(album.id, completed=True)]
    assert album.update_art_images_one_post.mock_calls == []
    assert album.update_art_images_grid.mock_calls == []
    assert album.delete_art_images.mock_calls == [call(art_hash)]


def test_update_art_if_needed_change_first_post(album):
    # update art
    album.post_manager.dynamo.generate_post_ids_in_album.return_value = ['a']
    album.update_art_if_needed()

    # verify calls
    art_hash_a = album.item['artHash']
    assert art_hash_a
    assert album.post_manager.dynamo.generate_post_ids_in_album.mock_calls == [call(album.id, completed=True)]
    assert album.update_art_images_one_post.mock_calls == [call(art_hash_a, 'a')]
    assert album.update_art_images_grid.mock_calls == []
    assert album.delete_art_images.mock_calls == []

    # clear mocks
    album.post_manager.dynamo.generate_post_ids_in_album.reset_mock()
    album.update_art_images_one_post.reset_mock()
    album.update_art_images_grid.reset_mock()
    album.delete_art_images.reset_mock()

    # add a post with an earlier posted_at
    album.post_manager.dynamo.generate_post_ids_in_album.return_value = ['b', 'a']
    album.update_art_if_needed()

    # verify calls
    art_hash_b = album.item['artHash']
    assert art_hash_b != art_hash_a
    assert album.post_manager.dynamo.generate_post_ids_in_album.mock_calls == [call(album.id, completed=True)]
    assert album.update_art_images_one_post.mock_calls == [call(art_hash_b, 'b')]
    assert album.update_art_images_grid.mock_calls == []
    assert album.delete_art_images.mock_calls == [call(art_hash_a)]


def test_update_art_if_needed_go_1_3_4_3_posts(album):
    # add one post
    album.post_manager.dynamo.generate_post_ids_in_album.return_value = ['a']
    album.update_art_if_needed()

    # verify calls
    art_hash_1 = album.item['artHash']
    assert art_hash_1
    assert album.post_manager.dynamo.generate_post_ids_in_album.mock_calls == [call(album.id, completed=True)]
    assert album.update_art_images_one_post.mock_calls == [call(art_hash_1, 'a')]
    assert album.update_art_images_grid.mock_calls == []
    assert album.delete_art_images.mock_calls == []

    # clear mocks
    album.post_manager.dynamo.generate_post_ids_in_album.reset_mock()
    album.update_art_images_one_post.reset_mock()
    album.update_art_images_grid.reset_mock()
    album.delete_art_images.reset_mock()

    # add two more posts
    album.post_manager.dynamo.generate_post_ids_in_album.return_value = ['a', 'b', 'c']
    album.update_art_if_needed()

    # verify calls
    assert album.item['artHash'] == art_hash_1
    assert album.post_manager.dynamo.generate_post_ids_in_album.mock_calls == [call(album.id, completed=True)]
    assert album.update_art_images_one_post.mock_calls == []
    assert album.update_art_images_grid.mock_calls == []
    assert album.delete_art_images.mock_calls == []

    # clear mocks
    album.post_manager.dynamo.generate_post_ids_in_album.reset_mock()
    album.update_art_images_one_post.reset_mock()
    album.update_art_images_grid.reset_mock()
    album.delete_art_images.reset_mock()

    # add a fourth post
    album.post_manager.dynamo.generate_post_ids_in_album.return_value = ['a', 'b', 'c', 'd']
    album.update_art_if_needed()

    # verify calls
    art_hash_4 = album.item['artHash']
    assert art_hash_4
    assert album.post_manager.dynamo.generate_post_ids_in_album.mock_calls == [call(album.id, completed=True)]
    assert album.update_art_images_one_post.mock_calls == []
    assert album.update_art_images_grid.mock_calls == [call(art_hash_4, ['a', 'b', 'c', 'd'])]
    assert album.delete_art_images.mock_calls == [call(art_hash_1)]

    # clear mocks
    album.post_manager.dynamo.generate_post_ids_in_album.reset_mock()
    album.update_art_images_one_post.reset_mock()
    album.update_art_images_grid.reset_mock()
    album.delete_art_images.reset_mock()

    # go back to three posts
    album.post_manager.dynamo.generate_post_ids_in_album.return_value = ['a', 'b', 'c']
    album.update_art_if_needed()

    # verify calls
    assert album.item['artHash'] == art_hash_1
    assert album.post_manager.dynamo.generate_post_ids_in_album.mock_calls == [call(album.id, completed=True)]
    assert album.update_art_images_one_post.mock_calls == [call(album.item['artHash'], 'a')]
    assert album.update_art_images_grid.mock_calls == []
    assert album.delete_art_images.mock_calls == [call(art_hash_4)]


def test_update_art_if_needed_4_8_9_15_16(album):
    # add four posts
    album.post_manager.dynamo.generate_post_ids_in_album.return_value = ['a', 'b', 'c', 'd']
    album.update_art_if_needed()

    # verify calls
    art_hash_4 = album.item['artHash']
    assert art_hash_4
    assert album.post_manager.dynamo.generate_post_ids_in_album.mock_calls == [call(album.id, completed=True)]
    assert album.update_art_images_one_post.mock_calls == []
    assert album.update_art_images_grid.mock_calls == [call(art_hash_4, ['a', 'b', 'c', 'd'])]
    assert album.delete_art_images.mock_calls == []

    # clear mocks
    album.post_manager.dynamo.generate_post_ids_in_album.reset_mock()
    album.update_art_images_one_post.reset_mock()
    album.update_art_images_grid.reset_mock()
    album.delete_art_images.reset_mock()

    # jump to 8 posts
    album.post_manager.dynamo.generate_post_ids_in_album.return_value = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
    album.update_art_if_needed()

    # verify calls
    assert album.item['artHash'] == art_hash_4
    assert album.post_manager.dynamo.generate_post_ids_in_album.mock_calls == [call(album.id, completed=True)]
    assert album.update_art_images_one_post.mock_calls == []
    assert album.update_art_images_grid.mock_calls == []
    assert album.delete_art_images.mock_calls == []

    # clear mocks
    album.post_manager.dynamo.generate_post_ids_in_album.reset_mock()
    album.update_art_images_one_post.reset_mock()
    album.update_art_images_grid.reset_mock()
    album.delete_art_images.reset_mock()

    # climb to 9 posts
    post_ids = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i']
    album.post_manager.dynamo.generate_post_ids_in_album.return_value = post_ids
    album.update_art_if_needed()

    # verify calls
    art_hash_9 = album.item['artHash']
    assert art_hash_9 != art_hash_4
    assert album.post_manager.dynamo.generate_post_ids_in_album.mock_calls == [call(album.id, completed=True)]
    assert album.update_art_images_one_post.mock_calls == []
    assert album.update_art_images_grid.mock_calls == [call(art_hash_9, post_ids)]
    assert album.delete_art_images.mock_calls == [call(art_hash_4)]

    # clear mocks
    album.post_manager.dynamo.generate_post_ids_in_album.reset_mock()
    album.update_art_images_one_post.reset_mock()
    album.update_art_images_grid.reset_mock()
    album.delete_art_images.reset_mock()

    # jump to 15 posts
    post_ids = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o']
    album.post_manager.dynamo.generate_post_ids_in_album.return_value = post_ids
    album.update_art_if_needed()

    # verify calls
    assert album.item['artHash'] == art_hash_9
    assert album.post_manager.dynamo.generate_post_ids_in_album.mock_calls == [call(album.id, completed=True)]
    assert album.update_art_images_one_post.mock_calls == []
    assert album.update_art_images_grid.mock_calls == []
    assert album.delete_art_images.mock_calls == []

    # clear mocks
    album.post_manager.dynamo.generate_post_ids_in_album.reset_mock()
    album.update_art_images_one_post.reset_mock()
    album.update_art_images_grid.reset_mock()
    album.delete_art_images.reset_mock()

    # climb to 16  posts
    post_ids = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p']
    album.post_manager.dynamo.generate_post_ids_in_album.return_value = post_ids
    album.update_art_if_needed()

    # verify calls
    art_hash_16 = album.item['artHash']
    assert art_hash_16 != art_hash_9
    assert album.post_manager.dynamo.generate_post_ids_in_album.mock_calls == [call(album.id, completed=True)]
    assert album.update_art_images_one_post.mock_calls == []
    assert album.update_art_images_grid.mock_calls == [call(art_hash_16, post_ids)]
    assert album.delete_art_images.mock_calls == [call(art_hash_9)]
