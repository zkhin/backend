# The schema of our master dynamodb table
# This should be kept in sync with what's described in serverless.yaml


table_schema = {
    'KeySchema': [
        {'AttributeName': 'partitionKey', 'KeyType': 'HASH'},
        {'AttributeName': 'sortKey', 'KeyType': 'RANGE'},
    ],
    'GlobalSecondaryIndexes': [
        {
            'IndexName': 'GSI-A1',
            'KeySchema': [
                {'AttributeName': 'gsiA1PartitionKey', 'KeyType': 'HASH'},
                {'AttributeName': 'gsiA1SortKey', 'KeyType': 'RANGE'},
            ],
            'Projection': {'ProjectionType': 'ALL'},
        },
        {
            'IndexName': 'GSI-A2',
            'KeySchema': [
                {'AttributeName': 'gsiA2PartitionKey', 'KeyType': 'HASH'},
                {'AttributeName': 'gsiA2SortKey', 'KeyType': 'RANGE'},
            ],
            'Projection': {'ProjectionType': 'ALL'},
        },
        {
            'IndexName': 'GSI-A3',
            'KeySchema': [
                {'AttributeName': 'gsiA3PartitionKey', 'KeyType': 'HASH'},
                {'AttributeName': 'gsiA3SortKey', 'KeyType': 'RANGE'},
            ],
            'Projection': {'ProjectionType': 'ALL'},
        },
        {
            'IndexName': 'GSI-K1',
            'KeySchema': [
                {'AttributeName': 'gsiK1PartitionKey', 'KeyType': 'HASH'},
                {'AttributeName': 'gsiK1SortKey', 'KeyType': 'RANGE'},
            ],
            'Projection': {'ProjectionType': 'KEYS_ONLY'},
        },
        {
            'IndexName': 'GSI-K2',
            'KeySchema': [
                {'AttributeName': 'gsiK2PartitionKey', 'KeyType': 'HASH'},
                {'AttributeName': 'gsiK2SortKey', 'KeyType': 'RANGE'},
            ],
            'Projection': {'ProjectionType': 'KEYS_ONLY'},
        },
        {
            'IndexName': 'GSI-K3',
            'KeySchema': [
                {'AttributeName': 'gsiK3PartitionKey', 'KeyType': 'HASH'},
                {'AttributeName': 'gsiK3SortKey', 'KeyType': 'RANGE'},
            ],
            'Projection': {'ProjectionType': 'KEYS_ONLY'},
        },
    ],
    'AttributeDefinitions': [
        {'AttributeName': 'partitionKey', 'AttributeType': 'S'},
        {'AttributeName': 'sortKey', 'AttributeType': 'S'},
        {'AttributeName': 'gsiA1PartitionKey', 'AttributeType': 'S'},
        {'AttributeName': 'gsiA1SortKey', 'AttributeType': 'S'},
        {'AttributeName': 'gsiA2PartitionKey', 'AttributeType': 'S'},
        {'AttributeName': 'gsiA2SortKey', 'AttributeType': 'S'},
        {'AttributeName': 'gsiA3PartitionKey', 'AttributeType': 'S'},
        {'AttributeName': 'gsiA3SortKey', 'AttributeType': 'S'},
        {'AttributeName': 'gsiK1PartitionKey', 'AttributeType': 'S'},
        {'AttributeName': 'gsiK1SortKey', 'AttributeType': 'S'},
        {'AttributeName': 'gsiK2PartitionKey', 'AttributeType': 'S'},
        {'AttributeName': 'gsiK2SortKey', 'AttributeType': 'S'},
        {'AttributeName': 'gsiK3PartitionKey', 'AttributeType': 'S'},
        {'AttributeName': 'gsiK3SortKey', 'AttributeType': 'N'},
    ],
}
