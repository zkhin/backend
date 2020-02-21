import boto3
import moto
import pytest
import types

from .table_schema import table_schema


@pytest.fixture
def dynamo_client():
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
        yield client


@pytest.fixture
def dynamo_table():
    with moto.mock_dynamodb2():
        dynamo_resource = boto3.resource('dynamodb')
        yield dynamo_resource.create_table(TableName='test-table', BillingMode='PAY_PER_REQUEST', **table_schema)
