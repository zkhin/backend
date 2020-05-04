import json
import logging
import threading

threadLocal = threading.local()


def register_gql_details(request_id, field, caller_user_id, arguments, source):
    threadLocal.request_id = request_id
    threadLocal.gql_field = field
    threadLocal.gql_caller_user_id = caller_user_id
    threadLocal.gql_arguments = arguments
    threadLocal.gql_source = source


# https://docs.python.org/3/howto/logging-cookbook.html#using-a-context-manager-for-selective-logging
class LogLevelContext:
    def __init__(self, logger, level):
        self.logger = logger
        self.level = level

    def __enter__(self):
        self.old_level = self.logger.level
        self.logger.setLevel(self.level)

    def __exit__(self, et, ev, tb):
        self.logger.setLevel(self.old_level)


class AddRequestInfoFilter(logging.Formatter):
    "Logging filter that does not filter, but rather adds the graphql request info to the logging record"

    def filter(self, record):
        record.request_id = getattr(threadLocal, 'request_id', None)
        record.gql_field = getattr(threadLocal, 'gql_field', None)
        record.gql_caller_user_id = getattr(threadLocal, 'gql_caller_user_id', None)
        record.gql_arguments = getattr(threadLocal, 'gql_arguments', None)
        record.gql_source = getattr(threadLocal, 'gql_source', None)
        return True


# https://github.com/python/cpython/blob/master/Lib/logging/__init__.py#L510
class CloudWatchFormatter(logging.Formatter):
    "Format logging records so they json and readable in CloudWatch"

    def format(self, record):
        # clear away the lamba path prefix
        prefix = '/var/task/'
        start = len(prefix) if record.pathname.startswith(prefix) else 0
        path = record.pathname[start:]

        data = {
            'level': record.levelname,
            'requestId': record.request_id,
            'event': getattr(record, 'event', None),
            'gqlField': record.gql_field,
            'gqlCallerUserId': record.gql_caller_user_id,
            'gqlArguments': record.gql_arguments,
            'gqlSource': record.gql_source,
            'message': record.getMessage(),
            'sourceFile': path,
            'sourceLine': record.lineno,
        }
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            data['exceptionInfo'] = record.exc_text.split('\n')
        if record.stack_info:
            data['stackInfo'] = record.stack_info.split('\n')
        return f'{record.levelname} RequestId: {record.request_id} Data: {json.dumps(data)}'


# configure the root logger
logger = logging.getLogger()
logger.addFilter(AddRequestInfoFilter())
for handler in logger.handlers:
    handler.setFormatter(CloudWatchFormatter())
