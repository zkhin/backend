import base64
import json
import logging
import os

import boto3
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from more_itertools import chunked

DYNAMO_TABLE = os.environ.get('DYNAMO_TABLE')
DYNAMO_PARTITION_KEY = os.environ.get('DYNAMO_PARTITION_KEY')
DYNAMO_SORT_KEY = os.environ.get('DYNAMO_SORT_KEY')
logger = logging.getLogger()


class DynamoClient:
    def __init__(
        self,
        table_name=DYNAMO_TABLE,
        partition_key=DYNAMO_PARTITION_KEY,
        sort_key=DYNAMO_SORT_KEY,
        batch_get_items_max=100,
        create_table_schema=None,
    ):
        """
        If create_table_schema is not None, then the table will be created
        on-the-fly. Useful when testing with a mocked dynamodb backend.
        """
        assert table_name, "Table name is required"
        self.table_name = table_name
        self.partition_key = partition_key
        self.sort_key = sort_key
        self.batch_get_items_max = batch_get_items_max

        boto3_resource = boto3.resource('dynamodb')
        self.table = (
            boto3_resource.create_table(TableName=table_name, **create_table_schema)
            if create_table_schema
            else boto3_resource.Table(table_name)
        )

        self.boto3_client = boto3.client('dynamodb')
        self.exceptions = self.boto3_client.exceptions

        # https://stackoverflow.com/a/46738251
        deserializer = TypeDeserializer()
        serializer = TypeSerializer()
        self.serialize = lambda item: {k: serializer.serialize(v) for k, v in item.items()}
        self.deserialize = lambda item: {k: deserializer.deserialize(v) for k, v in item.items()}

    def add_item(self, query_kwargs):
        "Put an item and return what was putted"
        assert self.partition_key
        kwargs = {
            **query_kwargs,
            'ConditionExpression': f'attribute_not_exists({self.partition_key})'
            + (f' and ({query_kwargs["ConditionExpression"]})' if 'ConditionExpression' in query_kwargs else ''),
        }
        self.table.put_item(**kwargs)
        return query_kwargs.get('Item')

    def get_item(self, pk, **kwargs):
        "Get an item by its primary key"
        return self.table.get_item(Key=pk, **kwargs).get('Item')

    def batch_get_items(self, key_generator, projection_expression=None):
        """
        Batch get the items identified by `key_generator`.
        If `projection_expression` is supplied, apply it.
        Returns a generator of item responses, output order may not match input order.
        """
        base_table_request = {'ProjectionExpression': projection_expression} if projection_expression else {}
        for keys in chunked(key_generator, self.batch_get_items_max):
            request_items = {self.table_name: {**base_table_request, 'Keys': [self.serialize(k) for k in keys]}}
            items = self.boto3_client.batch_get_item(RequestItems=request_items)['Responses'][self.table_name]
            for item in items:
                yield self.deserialize(item)

    def update_item(self, query_kwargs, failure_warning=None):
        """
        Update an item and return the new item.
        Set `failure_warning` fail softly with a logged warning rather than raise an exception.
        """
        assert self.partition_key
        kwargs = {
            **query_kwargs,
            'ConditionExpression': f'attribute_exists({self.partition_key})'
            + (f' and ({query_kwargs["ConditionExpression"]})' if 'ConditionExpression' in query_kwargs else ''),
            'ReturnValues': 'ALL_NEW',
        }
        try:
            return self.table.update_item(**kwargs).get('Attributes')
        except self.exceptions.ConditionalCheckFailedException:
            if failure_warning is None:
                raise
            logger.warning(failure_warning)

    def set_attributes(self, key, **attributes):
        """
        Set the given attributes for the given key.
        If the item does not exist, create it.
        """
        assert attributes, 'Must provide at least one attribute to set'
        kwargs = {
            'Key': key,
            'UpdateExpression': 'SET ' + ', '.join([f'{k} = :{k}' for k in attributes.keys()]),
            'ExpressionAttributeValues': {f':{k}': v for k, v in attributes.items()},
            'ReturnValues': 'ALL_NEW',
        }
        return self.table.update_item(**kwargs).get('Attributes')

    def increment_count(self, key, attribute_name):
        "Best-effort attempt to increment a counter. Logs a WARNING upon failure."
        assert self.partition_key
        query_kwargs = {
            'Key': key,
            'UpdateExpression': 'ADD #attrName :one',
            'ExpressionAttributeNames': {'#attrName': attribute_name},
            'ExpressionAttributeValues': {':one': 1},
            'ConditionExpression': f'attribute_exists({self.partition_key})',
        }
        failure_warning = f'Failed to increment {attribute_name} for key `{key}`'
        return self.update_item(query_kwargs, failure_warning=failure_warning)

    def decrement_count(self, key, attribute_name):
        "Best-effort attempt to decrement a counter. Logs a WARNING upon failure."
        assert self.partition_key
        query_kwargs = {
            'Key': key,
            'UpdateExpression': 'ADD #attrName :neg_one',
            'ExpressionAttributeNames': {'#attrName': attribute_name},
            'ExpressionAttributeValues': {':neg_one': -1, ':zero': 0},
            'ConditionExpression': f'attribute_exists({self.partition_key}) AND #attrName > :zero',
        }
        failure_warning = f'Failed to decrement {attribute_name} for key `{key}`'
        return self.update_item(query_kwargs, failure_warning=failure_warning)

    def batch_put_items(self, generator):
        "Batch put the items yielded by `generator`. Returns count of how many puts requested."
        cnt = 0
        with self.table.batch_writer() as batch:
            for item in generator:
                batch.put_item(Item=item)
                cnt += 1
        return cnt

    def delete_item(self, pk, **kwargs):
        "Delete an item and return what was deleted"
        return_values = kwargs.pop('ReturnValues', 'ALL_OLD')
        # return None if nothing was deleted, rather than an empty dict
        return self.table.delete_item(Key=pk, ReturnValues=return_values, **kwargs).get('Attributes') or None

    def batch_delete_items(self, generator):
        "Batch delete the items or keys yielded by `generator`. Returns count of how many deletes requested."
        assert self.partition_key
        assert self.sort_key
        key_generator = ({k: item[k] for k in (self.partition_key, self.sort_key)} for item in generator)
        return self.batch_delete(key_generator)

    def batch_delete(self, key_generator):
        "Batch delete items by keys yielded by `generator`. Returns count of how many deletes requested."
        cnt = 0
        with self.table.batch_writer() as batch:
            for key in key_generator:
                batch.delete_item(Key=key)
                cnt += 1
        return cnt

    def encode_pagination_token(self, last_evaluated_key):
        "From a LastEvaluatedKey to a obfucated string"
        # https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.html#Query.Pagination
        return base64.b64encode(json.dumps(last_evaluated_key).encode('ascii')).decode('utf-8')

    def decode_pagination_token(self, token):
        "From a obfucated string to a ExclusiveStartKey"
        return json.loads(base64.b64decode(token.encode('ascii')).decode('utf-8'))

    def query(self, query_kwargs, limit=None, next_token=None):
        "Query the table and return items & pagination token from the result"
        kwargs = {
            **query_kwargs,
            **({'Limit': limit} if limit else {}),
            **({'ExclusiveStartKey': self.decode_pagination_token(next_token)} if next_token else {}),
        }
        resp = self.table.query(**kwargs)
        last_key = resp.get('LastEvaluatedKey')
        return {
            'items': resp['Items'],
            'nextToken': self.encode_pagination_token(last_key) if last_key else None,
        }

    def query_head(self, query_kwargs):
        "Query the table and return the first item or None. Does not play well with Filters"
        # Note that supporting a filter expression is possible, but requires a separate codepath
        # if you want to avoid causing negative performance impacts for the common case
        assert 'FilterExpression' not in query_kwargs
        kwargs = {**query_kwargs, 'Limit': 1}
        resp = self.table.query(**kwargs)
        return resp['Items'][0] if resp['Items'] else None

    def generate_all_query(self, query_kwargs):
        "Return a generator that iterates over all results of the query"
        last_key = False
        while last_key is not None:
            start_kwargs = {'ExclusiveStartKey': last_key} if last_key else {}
            resp = self.table.query(**query_kwargs, **start_kwargs)
            for item in resp['Items']:
                yield item
            last_key = resp.get('LastEvaluatedKey')

    def generate_all_scan(self, scan_kwargs):
        "Return a generator that iterates over all results of the scan"
        last_key = False
        while last_key is not None:
            start_kwargs = {'ExclusiveStartKey': last_key} if last_key else {}
            resp = self.table.scan(**scan_kwargs, **start_kwargs)
            for item in resp['Items']:
                yield item
            last_key = resp.get('LastEvaluatedKey')
