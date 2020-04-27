import boto3
import moto
import pytest
import types

from .table_schema import table_schema


@pytest.fixture
def dynamo_client_and_table():
    """
    Both the dynamo_client and dynamo_table must be generated under the same mock_dynamodb2
    instance in order for catching of exceptions thrown by operations with the table
    using the error definitions on the client to work.
    """
    with moto.mock_dynamodb2():
        client = boto3.client('dynamodb')

        # moto doesn't support transactions, so we patch in good-enough support for them
        def transact_write_items(self, TransactItems=[]):
            for transact_item in TransactItems:
                assert len(transact_item) == 1
                key, kwargs = next(iter(transact_item.items()))
                if key == 'Put':
                    operation = self.put_item
                elif key == 'Delete':
                    operation = self.delete_item
                elif key == 'Update':
                    operation = self.update_item
                elif key == 'ConditionCheck':
                    pass
                else:
                    raise ValueError(f"Unrecognized transaction key '{key}'")
                operation(**kwargs)

        client.transact_write_items = types.MethodType(transact_write_items, client)

        dynamo_resource = boto3.resource('dynamodb')
        table = dynamo_resource.create_table(TableName='test-table', BillingMode='PAY_PER_REQUEST', **table_schema)

        yield client, table


@pytest.fixture
def dynamo_client(dynamo_client_and_table):
    yield dynamo_client_and_table[0]


@pytest.fixture
def dynamo_table(dynamo_client_and_table):
    yield dynamo_client_and_table[1]


@pytest.fixture
def s3_bucket():
    with moto.mock_s3():
        yield boto3.resource('s3').create_bucket(Bucket='test-bucket')
