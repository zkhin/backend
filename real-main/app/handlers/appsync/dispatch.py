"AppSync GraphQL data source"
import logging
import os

from . import routes
from .logging import register_gql_details
from .exceptions import ClientException

logger = logging.getLogger()

# use this in the test suite to turn off auto-disocvery of routes
route_path = os.environ.get('APPSYNC_ROUTE_AUTODISCOVERY_PATH', 'app.handlers.appsync.handlers')
if route_path:
    routes.discover(route_path)


def dispatch(event, context):
    "Top-level dispatch of appsync event to the correct handler"

    req_id = getattr(context, 'aws_request_id', None)   # the RequestId that ends up in CloudWatch logs
    field = event['field']                              # graphql field name in format 'ParentType.fieldName'
    arguments = event['arguments']                      # graphql field arguments, if any
    source = event.get('source')                        # result of parent resolver, if any
    identity = event.get('identity')                    # AWS cognito identity, if the call was authenticated
    caller_user_id = identity.get('cognitoIdentityId') if identity else None

    if not caller_user_id:
        return {'error': 'No authentication found - all calls must be authenticated'}

    handler = routes.get_handler(field)
    if not handler:
        return {'error': f'No handler for field `{field}` found'}

    register_gql_details(req_id, field, caller_user_id, arguments, source)

    try:
        resp = handler(caller_user_id, arguments, source, context)
    except ClientException as err:
        msg = 'Client Error: ' + str(err)
        logger.warning(msg)
        return {'error': {
            'message': msg,
            'type': err.error_type,
            'data': err.error_data,
            'info': err.error_info,
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
