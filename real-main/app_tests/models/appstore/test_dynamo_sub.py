from uuid import uuid4

import pendulum
import pytest

from app.models.appstore.dynamo import AppStoreSubDynamo
from app.models.appstore.exceptions import AppStoreSubAlreadyExists


@pytest.fixture
def appstore_sub_dynamo(dynamo_client):
    yield AppStoreSubDynamo(dynamo_client)


def test_add(appstore_sub_dynamo):
    # configure starting state, verify
    original_transaction_id = str(uuid4())
    original_purchase_at = pendulum.now('utc') - pendulum.duration(minutes=1)
    expires_at = pendulum.now('utc') + pendulum.duration(months=1)
    receipt_data_b64 = str(uuid4())
    latest_receipt_info = {'bunchOf': 'stuff'}
    user_id = str(uuid4())
    assert appstore_sub_dynamo.get(original_transaction_id) is None

    # add a new item, verify format
    item = appstore_sub_dynamo.add(
        original_transaction_id, original_purchase_at, expires_at, receipt_data_b64, latest_receipt_info, user_id
    )
    assert appstore_sub_dynamo.get(original_transaction_id) == item
    assert item == {
        'partitionKey': f'appStoreSub/{original_transaction_id}',
        'sortKey': '-',
        'schemaVersion': 0,
        'userId': user_id,
        'receiptDataB64': receipt_data_b64,
        'latestReceiptInfo': latest_receipt_info,
        'gsiA1PartitionKey': f'appStoreSub/{user_id}',
        'gsiA1SortKey': original_purchase_at.to_iso8601_string(),
        'gsiK1PartitionKey': 'appStoreSub',
        'gsiK1SortKey': expires_at.to_iso8601_string(),
    }

    # verify can't re-add another item with same original transaction id
    with pytest.raises(AppStoreSubAlreadyExists):
        appstore_sub_dynamo.add(
            original_transaction_id, pendulum.now('utc'), pendulum.now('utc'), str(uuid4()), {}, str(uuid4())
        )
    assert appstore_sub_dynamo.get(original_transaction_id) == item
