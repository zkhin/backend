import json
import logging

from .logging import logger, LogLevelContext


class ClientException(Exception):
    "Any error attributable to the api client"
    pass


def handler(func):
    "Decorator to simplify handlers"

    def inner(event, context):
        with LogLevelContext(logger, logging.INFO):
            logger.info(f'Handling `{func.__name__}` event', extra={'event': event})

        try:
            data = func(event, context)
        except ClientException as err:
            return {
                'statusCode': 400,
                'body': json.dumps({'message': str(err)})
            }

        return {
            'statusCode': 200,
            'body': json.dumps(data),
        }

    return inner
