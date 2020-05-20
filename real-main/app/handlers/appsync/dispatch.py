"AppSync GraphQL data source"
import logging
import os

from app.logging import configure_logging, LogLevelContext

from . import routes
from .exceptions import ClientException

configure_logging()
logger = logging.getLogger()

# use this in the test suite to turn off auto-disocvery of routes
route_path = os.environ.get('APPSYNC_ROUTE_AUTODISCOVERY_PATH', 'app.handlers.appsync.handlers')
if route_path:
    routes.discover(route_path)


def dispatch(event, context):
    "Top-level dispatch of appsync event to the correct handler"

    field = event['field']          # graphql field name in format 'ParentType.fieldName'
    arguments = event['arguments']  # graphql field arguments, if any
    source = event.get('source')    # result of parent resolver, if any

    # identity.cognitoIdentityId is None when called by backend to trigger subscriptions
    identity = event.get('identity')
    caller_user_id = identity.get('cognitoIdentityId') if identity else None

    handler = routes.get_handler(field)
    if not handler:
        # should not be able to get here
        msg = f'No handler for field `{field}` found'
        logger.exception(msg)
        raise Exception(msg)

    # we suppress INFO logging, except this message
    with LogLevelContext(logger, logging.INFO):
        gql_details = {
            'field': field,
            'caller_user_id': caller_user_id,
            'arguments': arguments,
            'source': source,
        }
        logger.info(f'Handling AppSync GQL resolution of `{field}`', extra={'gql': gql_details})

    try:
        resp = handler(caller_user_id, arguments, source, context)
    except ClientException as err:
        msg = 'ClientError: ' + str(err)
        logger.warning(msg)
        return {'error': {
            'message': msg,
            'data': err.data,
            'info': err.info,
        }}
    except Exception as err:
        # By logging the exception and then raising the error here, we:
        #   1) get to log the error ourselves to CloudWatch in a nice json format with all the info we want
        #   2) ensure an error is returned to the client
        #   3) get the uncaught exception logged to CloudWatch in a format that that the built-in 'Errors'
        #      metric will catch, thus triggering alerts
        # Note that this means the error gets logged to CloudWatch twice, once with prefix `ERROR` (our json object)
        # with prefix `[ERROR]` (the error message and traceback as a string)
        logger.exception(str(err))
        raise err

    return {'success': resp}
