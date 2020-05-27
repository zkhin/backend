"AppSync GraphQL data source"
import logging
import os

from app.logging import handler_logging, LogLevelContext

from . import routes
from .exceptions import ClientException

logger = logging.getLogger()

# use this in the test suite to turn off auto-disocvery of routes
route_path = os.environ.get('APPSYNC_ROUTE_AUTODISCOVERY_PATH', 'app.handlers.appsync.handlers')
if route_path:
    routes.discover(route_path)


@handler_logging
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

    return {'success': resp}
