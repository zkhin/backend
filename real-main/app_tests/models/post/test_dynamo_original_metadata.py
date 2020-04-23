import pytest

from app.models.post.dynamo import PostOriginalMetadataDynamo


@pytest.fixture
def pom_dynamo(dynamo_client):
    yield PostOriginalMetadataDynamo(dynamo_client)


def test_transact_add_original_metadata_and_delete(pom_dynamo):
    post_id = 'pid'
    original_metadata = 'stringified json'
    assert pom_dynamo.get(post_id) is None

    # set the original metadata
    transacts = [pom_dynamo.transact_add(post_id, original_metadata)]
    pom_dynamo.client.transact_write_items(transacts)

    # verify format in DB
    item = pom_dynamo.get(post_id)
    assert item['originalMetadata'] == original_metadata
    assert item['schemaVersion'] == 0

    # verify can't set it again
    transacts = [pom_dynamo.transact_add(post_id, 'new value')]
    with pytest.raises(pom_dynamo.client.exceptions.ConditionalCheckFailedException):
        pom_dynamo.client.transact_write_items(transacts)
    assert pom_dynamo.get(post_id)

    # delete the original metadata, verify it disappears
    pom_dynamo.delete(post_id)
    assert pom_dynamo.get(post_id) is None

    # verify a no-op delete is ok
    pom_dynamo.delete(post_id)
    assert pom_dynamo.get(post_id) is None
