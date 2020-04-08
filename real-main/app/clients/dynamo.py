import base64
import json
import os
import re

import boto3

DYNAMODB_TABLE = os.environ.get('DYNAMODB_TABLE')


class DynamoClient:

    def __init__(self, table_name=DYNAMODB_TABLE, create_table_schema=None):
        """
        If create_table_schema is not None, then the table will be created
        on-the-fly. Useful when testing with a mocked dynamodb backend.
        """
        assert table_name, "Table name is required"
        self.table_name = table_name

        boto3_resource = boto3.resource('dynamodb')

        if create_table_schema:
            create_table_schema['TableName'] = table_name
            boto3_resource.create_table(**create_table_schema)

        self.table = boto3_resource.Table(table_name)
        self.boto3_client = boto3.client('dynamodb')
        self.exceptions = self.boto3_client.exceptions

    def add_item(self, query_kwargs):
        "Put an item and return what was putted"
        # ensure query fails if the item already exists
        cond_exp = 'attribute_not_exists(partitionKey)'
        if 'ConditionExpression' in query_kwargs:
            cond_exp += ' and (' + query_kwargs['ConditionExpression'] + ')'
        query_kwargs['ConditionExpression'] = cond_exp

        self.table.put_item(**query_kwargs)
        return query_kwargs.get('Item')

    def update_item(self, query_kwargs):
        "Update an item and return the new item"
        # ensure query fails if the item does not exist
        cond_exp = 'attribute_exists(partitionKey)'
        if 'ConditionExpression' in query_kwargs:
            cond_exp += ' and (' + query_kwargs['ConditionExpression'] + ')'
        query_kwargs['ConditionExpression'] = cond_exp

        query_kwargs['ReturnValues'] = 'ALL_NEW'
        return self.table.update_item(**query_kwargs).get('Attributes')

    def get_item(self, pk, strongly_consistent=False):
        "Get an item by its primary key"
        kwargs = {
            'Key': {
                'partitionKey': pk['partitionKey'],
                'sortKey': pk['sortKey'],
            },
            'ConsistentRead': strongly_consistent,
        }
        return self.table.get_item(**kwargs).get('Item')

    def batch_get_items(self, typed_keys, projection_expression=None):
        """
        Get a bunch of items in one batch request.
        Both the input `typed_keys` and the return value should/will be in
        verbose format, with types.
        Order *not* maintained.
        """
        assert len(typed_keys) <= 100, "Max 100 items per batch get request"
        kwargs = {'RequestItems': {self.table_name: {'Keys': typed_keys}}}
        if projection_expression:
            kwargs['RequestItems'][self.table_name]['ProjectionExpression'] = projection_expression
        return self.boto3_client.batch_get_item(**kwargs)['Responses'][self.table_name]

    def delete_item(self, query_kwargs):
        "Delete an item and return what was deleted"
        query_kwargs['ReturnValues'] = 'ALL_OLD'
        # return None if nothing was deleted, rather than an empty dict
        return self.table.delete_item(**query_kwargs).get('Attributes') or None

    # TODO: remove me when Media model is removed, it's the only place this is used
    def delete_item_by_pk(self, pk):
        "Delete an item by its primary key"
        kwargs = {
            'Key': {
                'partitionKey': pk['partitionKey'],
                'sortKey': pk['sortKey'],
            },
            'ReturnValues': 'ALL_OLD',
        }
        return self.delete_item(kwargs)

    def encode_pagination_token(self, last_evaluated_key):
        "From a LastEvaluatedKey to a obfucated string"
        # https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.html#Query.Pagination
        return base64.b64encode(json.dumps(last_evaluated_key).encode('ascii')).decode('utf-8')

    def decode_pagination_token(self, token):
        "From a obfucated string to a ExclusiveStartKey"
        return json.loads(base64.b64decode(token.encode('ascii')).decode('utf-8'))

    def query(self, query_kwargs, limit=None, next_token=None):
        "Query the table and return items & pagination token from the result"

        if limit:
            query_kwargs['Limit'] = limit
        if next_token:
            query_kwargs['ExclusiveStartKey'] = self.decode_pagination_token(next_token)

        resp = self.table.query(**query_kwargs)

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
        query_kwargs['Limit'] = 1
        resp = self.table.query(**query_kwargs)
        return resp['Items'][0] if resp['Items'] else None

    def generate_all_query(self, query_kwargs):
        "Return a generator that iterates over all results of the query"
        next_token = False
        while (next_token is not None):
            paginated = self.query(query_kwargs, next_token=next_token)
            for item in paginated['items']:
                yield item
            next_token = paginated.get('nextToken')

    def generate_all_scan(self, scan_kwargs):
        "Return a generator that iterates over all results of the scan"
        last_key = False
        while (last_key is not None):
            if last_key:
                scan_kwargs['ExclusiveStartKey'] = last_key
            resp = self.table.scan(**scan_kwargs)
            for item in resp['Items']:
                yield item
            last_key = resp.get('LastEvaluatedKey')

    def transact_write_items(self, transact_items, transact_exceptions=None):
        """
        Apply the given write operations in a transaction.
        https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html#DynamoDB.Client.transact_write_items
        Note that:
            - since this uses the boto dynamo client, rather than the resource, the writes format is more verbose
            - caller does not need to specify TableName

        If one of the transact_item's conditional expressions fails, then the corresponding entry in
        trasact_exceptions will be raised, if it was provided.

        To support moto, if 'transact_write_items' is not defined, then the operations are just done sequentially.
        Obviously this isn't great to have the unit tests going on a different code path than the live system,
        but it's better than no unit tests at all.
        """
        if transact_exceptions is None:
            transact_exceptions = [None] * len(transact_items)
        else:
            assert len(transact_items) == len(transact_exceptions)

        for ti in transact_items:
            list(ti.values()).pop()['TableName'] = self.table_name

        # TODO: is there a way to tell when we're running under moto, other than this try-and-fail?
        try:
            try:
                self.boto3_client.transact_write_items(TransactItems=transact_items)
            except self.boto3_client.exceptions.TransactionCanceledException as err:
                # we want to raise a more specific error than 'the whole transaction failed'
                # there is no way to get the CancellationReasons in boto3, so this is the best we can do
                # https://github.com/aws/aws-sdk-go/issues/2318#issuecomment-443039745
                reasons = re.search(r'\[(.*)\]$', err.response['Error']['Message']).group(1).split(', ')
                for reason, transact_exception in zip(reasons, transact_exceptions):
                    if reason == 'ConditionalCheckFailed':
                        # the transact_item with this transaction_exception failed
                        if transact_exception is not None:
                            raise transact_exception
                raise err

        except AttributeError:
            # we're running under moto, ie, in the test suite
            for transact_item, transact_exception in zip(transact_items, transact_exceptions):
                assert len(transact_item) == 1
                key, kwargs = next(iter(transact_item.items()))

                if key == 'Put':
                    operation = self.boto3_client.put_item
                elif key == 'Delete':
                    operation = self.boto3_client.delete_item
                elif key == 'Update':
                    operation = self.boto3_client.update_item
                elif key == 'ConditionCheck':
                    # There is no corresponding operation we can do here, AFAIK
                    # Thus we can't test write failures due to ConditionChecks in test suite
                    continue
                else:
                    raise ValueError(f"Unrecognized transaction key '{key}'")

                try:
                    operation(**kwargs)
                except self.exceptions.ConditionalCheckFailedException as err:
                    if transact_exception is not None:
                        raise transact_exception
                    raise err
