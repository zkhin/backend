from uuid import uuid4

import pendulum
import pytest

from app.models.appstore.dynamo import AppStoreReceiptDynamo
from app.models.appstore.exceptions import AppStoreReceiptAlreadyExists


@pytest.fixture
def appstore_receipt_dynamo(dynamo_client):
    yield AppStoreReceiptDynamo(dynamo_client)


def test_add(appstore_receipt_dynamo):
    # configure starting state, verify
    receipt_data_b64_md5 = str(uuid4())
    receipt_data_b64 = str(uuid4())
    user_id = str(uuid4())
    assert appstore_receipt_dynamo.get(receipt_data_b64_md5) is None

    # add a new item, verify format
    item = appstore_receipt_dynamo.add(receipt_data_b64_md5, receipt_data_b64, user_id)
    assert appstore_receipt_dynamo.get(receipt_data_b64_md5) == item
    assert item == {
        'partitionKey': f'appStoreReceipt/{receipt_data_b64_md5}',
        'sortKey': '-',
        'schemaVersion': 0,
        'userId': user_id,
        'receiptDataB64': receipt_data_b64,
        'receiptDataB64MD5': receipt_data_b64_md5,
        'gsiA1PartitionKey': f'appStoreReceipt/{user_id}',
        'gsiA1SortKey': '-',
    }

    # verify can't re-add another item with same md5
    with pytest.raises(AppStoreReceiptAlreadyExists):
        appstore_receipt_dynamo.add(receipt_data_b64_md5, 'other', 'stuff')
    assert appstore_receipt_dynamo.get(receipt_data_b64_md5) == item


def test_add_verification_attempt(appstore_receipt_dynamo):
    # add a receipt, verify it's there
    receipt_data_b64_md5 = str(uuid4())
    item = appstore_receipt_dynamo.add(receipt_data_b64_md5, str(uuid4()), str(uuid4()))
    assert appstore_receipt_dynamo.get(receipt_data_b64_md5) == item
    key = {k: item[k] for k in ('partitionKey', 'sortKey')}

    # add a first verification attempt, verify state
    status_code_1 = 234
    at_1 = pendulum.now('utc')
    new_item = appstore_receipt_dynamo.add_verification_attempt(key, status_code_1, at_1, first=True)
    assert pendulum.parse(new_item.pop('verifyAttemptsFirstAt')) == at_1
    assert pendulum.parse(new_item.pop('verifyAttemptsLastAt')) == at_1
    assert new_item.pop('verifyAttemptsCount') == 1
    assert new_item.pop('verifyAttemptsStatusCodes') == [status_code_1]
    assert new_item == item

    # add a second verification attempt, verify state
    status_code_2 = 345
    at_2 = pendulum.now('utc')
    at_3 = at_2 + pendulum.duration(hours=1)
    new_item = appstore_receipt_dynamo.add_verification_attempt(key, status_code_2, at_2, next_at=at_3)
    assert pendulum.parse(new_item.pop('verifyAttemptsFirstAt')) == at_1
    assert pendulum.parse(new_item.pop('verifyAttemptsLastAt')) == at_2
    assert new_item.pop('verifyAttemptsCount') == 2
    assert new_item.pop('verifyAttemptsStatusCodes') == [status_code_1, status_code_2]
    assert new_item.pop('gsiK1PartitionKey') == 'appStoreReceipt'
    assert pendulum.parse(new_item.pop('gsiK1SortKey')) == at_3
    assert new_item == item


def test_generate_keys_to_verify(appstore_receipt_dynamo):
    # add three receipts
    receipt_data_b64_md5_1 = str(uuid4())
    receipt_data_b64_md5_2 = str(uuid4())
    receipt_data_b64_md5_3 = str(uuid4())
    appstore_receipt_dynamo.add(receipt_data_b64_md5_1, str(uuid4()), str(uuid4()))
    item_2 = appstore_receipt_dynamo.add(receipt_data_b64_md5_2, str(uuid4()), str(uuid4()))
    item_3 = appstore_receipt_dynamo.add(receipt_data_b64_md5_3, str(uuid4()), str(uuid4()))
    key_2 = {k: item_2[k] for k in ('partitionKey', 'sortKey')}
    key_3 = {k: item_3[k] for k in ('partitionKey', 'sortKey')}

    # put two of those receipts in the 'to verify' index
    next_at_2 = pendulum.now('utc')
    next_at_3 = next_at_2 + pendulum.duration(minutes=1)
    appstore_receipt_dynamo.add_verification_attempt(key_2, 345, pendulum.now('utc'), next_at=next_at_2)
    appstore_receipt_dynamo.add_verification_attempt(key_3, 345, pendulum.now('utc'), next_at=next_at_3)

    # verify starting state
    assert 'gsiK1SortKey' not in appstore_receipt_dynamo.get(receipt_data_b64_md5_1)
    assert pendulum.parse(appstore_receipt_dynamo.get(receipt_data_b64_md5_2)['gsiK1SortKey']) == next_at_2
    assert pendulum.parse(appstore_receipt_dynamo.get(receipt_data_b64_md5_3)['gsiK1SortKey']) == next_at_3

    # generate no keys
    mus1 = pendulum.duration(microseconds=1)
    assert list(appstore_receipt_dynamo.generate_keys_to_verify(now=next_at_2 - mus1)) == []

    # generate one key
    assert list(appstore_receipt_dynamo.generate_keys_to_verify()) == [key_2]
    assert list(appstore_receipt_dynamo.generate_keys_to_verify(now=next_at_2)) == [key_2]
    assert list(appstore_receipt_dynamo.generate_keys_to_verify(now=next_at_3 - mus1)) == [key_2]

    # generate two keys
    assert list(appstore_receipt_dynamo.generate_keys_to_verify(now=next_at_3)) == [key_2, key_3]


def test_generate_keys_by_user(appstore_receipt_dynamo):
    # add three receipts by two users
    receipt_data_b64_md5_1 = str(uuid4())
    receipt_data_b64_md5_2 = str(uuid4())
    receipt_data_b64_md5_3 = str(uuid4())
    user_id_1, user_id_2 = str(uuid4()), str(uuid4())
    item_1 = appstore_receipt_dynamo.add(receipt_data_b64_md5_1, str(uuid4()), user_id_1)
    item_2 = appstore_receipt_dynamo.add(receipt_data_b64_md5_2, str(uuid4()), user_id_2)
    item_3 = appstore_receipt_dynamo.add(receipt_data_b64_md5_3, str(uuid4()), user_id_2)
    key_1 = {k: item_1[k] for k in ('partitionKey', 'sortKey')}
    key_2 = {k: item_2[k] for k in ('partitionKey', 'sortKey')}
    key_3 = {k: item_3[k] for k in ('partitionKey', 'sortKey')}

    # generate none, generate one, generate two
    assert list(appstore_receipt_dynamo.generate_keys_by_user(str(uuid4()))) == []
    assert list(appstore_receipt_dynamo.generate_keys_by_user(user_id_1)) == [key_1]
    assert list(appstore_receipt_dynamo.generate_keys_by_user(user_id_2)) == [key_2, key_3]
