import hashlib
from uuid import uuid4

import pytest

from app.models.appstore.exceptions import AppStoreReceiptAlreadyExists


@pytest.fixture
def user(user_manager, cognito_client):
    user_id, username = str(uuid4()), str(uuid4())[:8]
    cognito_client.create_verified_user_pool_entry(user_id, username, f'{username}@real.app')
    yield user_manager.create_cognito_only_user(user_id, username)


def test_add_receipt(appstore_manager, user):
    # configure two receipts, check starting state
    receipt_data_1, receipt_data_2 = str(uuid4()), str(uuid4())
    receipt_data_1_md5 = hashlib.md5(receipt_data_1.encode('utf-8')).hexdigest()
    receipt_data_2_md5 = hashlib.md5(receipt_data_2.encode('utf-8')).hexdigest()
    assert appstore_manager.receipt_dynamo.get(receipt_data_1_md5) is None
    assert appstore_manager.receipt_dynamo.get(receipt_data_2_md5) is None

    # add one of the receipts, verify
    appstore_manager.add_receipt(receipt_data_1, user.id)
    assert appstore_manager.receipt_dynamo.get(receipt_data_1_md5)
    assert appstore_manager.receipt_dynamo.get(receipt_data_2_md5) is None

    # add the other receipt, verify
    appstore_manager.add_receipt(receipt_data_2, user.id)
    assert appstore_manager.receipt_dynamo.get(receipt_data_1_md5)
    assert appstore_manager.receipt_dynamo.get(receipt_data_2_md5)

    # verify can't double-add a receipt
    with pytest.raises(AppStoreReceiptAlreadyExists):
        appstore_manager.add_receipt(receipt_data_2, user.id)
