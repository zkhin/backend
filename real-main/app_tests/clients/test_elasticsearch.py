import pytest
import requests_mock

from app.clients import ElasticSearchClient

# the requests_mock parameter is auto-supplied, no need to even import the
# requests-mock library # https://requests-mock.readthedocs.io/en/latest/pytest.html


@pytest.fixture
def elasticsearch_client():
    yield ElasticSearchClient(domain='real.es.amazonaws.com')


def test_build_user_url(elasticsearch_client):
    user_id = 'my-user-id'
    assert elasticsearch_client.build_user_url(user_id) == 'https://real.es.amazonaws.com/users/_doc/my-user-id'


def test_build_user_document_minimal(elasticsearch_client):
    user_item = {
        'sortKey': 'profile',
        'partitionKey': 'user/us-east-1:088d2841-7089-4136-88a0-8aa3e5ae9ce1',
        'privacyStatus': 'PUBLIC',
        'userId': 'us-east-1:088d2841-7089-4136-88a0-8aa3e5ae9ce1',
        'username': 'TESTER-gotSOMEcaseotxxie',
    }
    expected_user_doc = {
        'userId': 'us-east-1:088d2841-7089-4136-88a0-8aa3e5ae9ce1',
        'username': 'TESTER-gotSOMEcaseotxxie',
    }
    assert elasticsearch_client.build_user_doc(user_item) == expected_user_doc


def test_build_user_document_maximal(elasticsearch_client):
    user_item = {
        'phoneNumber': '+14155551212',
        'sortKey': 'profile',
        'partitionKey': 'user/us-east-1:bca9f0ae-76e4-4ac9-a750-c691cbda505b',
        'privacyStatus': 'PUBLIC',
        'userId': 'us-east-1:bca9f0ae-76e4-4ac9-a750-c691cbda505b',
        'email': 'success@simulator.amazonses.com',
        'username': 'TESTER-o7jow8',
        'fullName': 'Joe Shmoe',
        'bio': 'Staying classy, just like San Diego',
        'photoPath': 'somewhere/good',
        'followerCount': 42,
        'followedCount': 54,
        'postCount': 10,
    }
    expected_user_doc = {
        'userId': 'us-east-1:bca9f0ae-76e4-4ac9-a750-c691cbda505b',
        'username': 'TESTER-o7jow8',
        'fullName': 'Joe Shmoe',
    }
    assert elasticsearch_client.build_user_doc(user_item) == expected_user_doc


def test_add_user(elasticsearch_client, monkeypatch):
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'foo')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'bar')

    user_id = 'us-east-1:088d2841-7089-4136-88a0-8aa3e5ae9ce1'
    user_item = {
        'userId': user_id,
        'username': 'TESTER-gotSOMEcaseotxxie',
    }
    doc = elasticsearch_client.build_user_doc(user_item)
    url = elasticsearch_client.build_user_url(user_id)

    with requests_mock.mock() as m:
        m.put(url, None)
        elasticsearch_client.add_user(user_id, user_item)

    assert len(m.request_history) == 1
    assert m.request_history[0].method == 'PUT'
    assert m.request_history[0].json() == doc


def test_update_user(elasticsearch_client, monkeypatch):
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'foo')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'bar')

    user_id = 'us-east-1:088d2841-7089-4136-88a0-8aa3e5ae9ce1'
    old_user_item = {
        'userId': user_id,
        'username': 'something-else',
    }
    new_user_item = {
        'userId': user_id,
        'username': 'TESTER-gotSOMEcaseotxxie',
    }
    new_doc = elasticsearch_client.build_user_doc(new_user_item)
    url = elasticsearch_client.build_user_url(new_doc['userId'])

    with requests_mock.mock() as m:
        m.put(url, None)
        elasticsearch_client.update_user(user_id, old_user_item, new_user_item)

    assert len(m.request_history) == 1
    assert m.request_history[0].method == 'PUT'
    assert m.request_history[0].json() == new_doc


def test_delete_user(elasticsearch_client, monkeypatch):
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'foo')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'bar')

    user_id = 'us-east-1:088d2841-7089-4136-88a0-8aa3e5ae9ce1'
    url = elasticsearch_client.build_user_url(user_id)

    with requests_mock.mock() as m:
        m.delete(url, None)
        elasticsearch_client.delete_user(user_id)

    assert len(m.request_history) == 1
    assert m.request_history[0].method == 'DELETE'


def test_updates_without_change_in_index_fields_dont_get_sent_to_elasticsearch(elasticsearch_client):
    user_id = 'us-east-1:088d2841-7089-4136-88a0-8aa3e5ae9ce1'
    old_user_item = {'userId': user_id, 'username': 'same-thing'}
    new_user_item = {'userId': user_id, 'username': 'same-thing'}
    with requests_mock.mock() as m:
        elasticsearch_client.update_user(user_id, old_user_item, new_user_item)
    assert len(m.request_history) == 0
