import json
import logging


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


# https://github.com/python/cpython/blob/v3.8.3/Lib/logging/__init__.py#L510
class CloudWatchFormatter(logging.Formatter):
    "Format logging records so they json and readable in CloudWatch"

    extras = ('event', 'gql', 's3_key')

    def format(self, record):
        # clear away the lamba path prefix
        prefix = '/var/task/'
        start = len(prefix) if record.pathname.startswith(prefix) else 0
        path = record.pathname[start:]

        # Undocumented feature: lambda adds the request_id to all log records, so we don't have to
        # https://gist.github.com/alanjds/000b15f7dcd43d7646aab34fcd3cef8c#file-awslambda-bootstrap-py-L429
        # Fail softly so we can still use this formatter outside the lambda exe context
        request_id = getattr(record, 'aws_request_id', None)

        data = {
            'level': record.levelname,
            'requestId': request_id,
            'message': record.getMessage(),
            'sourceFile': path,
            'sourceLine': record.lineno,
        }

        for extra in self.extras:
            if hasattr(record, extra):
                data[extra] = getattr(record, extra)

        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            data['exceptionInfo'] = record.exc_text.split('\n')
        if record.stack_info:
            data['stackInfo'] = record.stack_info.split('\n')
        return f'{record.levelname} RequestId: {request_id} Data: {json.dumps(data)}'


def configure_logging():
    # lambda already sets a handler for us
    # https://gist.github.com/alanjds/000b15f7dcd43d7646aab34fcd3cef8c#file-awslambda-bootstrap-py-L463
    logger = logging.getLogger()
    for handler in logger.handlers:
        handler.setFormatter(CloudWatchFormatter())
