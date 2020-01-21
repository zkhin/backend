"""
Parse and serialize datetimes to/from strings.

Expected formats:

In graphql: as its own scalar type https://docs.aws.amazon.com/appsync/latest/devguide/scalars.html#awsdatetime
In dynamo: as strings in format YYYY-MM-DDThh:mm:ssZ, with optional decimal on the seconds
In python runtime (outside of this lib): as python datetime objects in UTC, but with no tzinfo

Gotchas for parsing datetimes in python: https://stackoverflow.com/a/49784038
"""

from datetime import datetime, timezone


def parse(dt_str):
    # To be used to parse all datetime strings from graphql or dynamo
    # All incoming strings must have timezone information attatched
    if dt_str is None:
        return None
    # python's datetime.fromisoformat() can't handle 'Z' for timezone info
    dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    assert dt.tzinfo, f'Datetime string `{dt_str}` has no timezone info'
    dt = dt.astimezone(timezone.utc)
    dt = dt.replace(tzinfo=None)
    return dt


def serialize(dt):
    # To be used to serialize all datetime strings to graphql and dynamo
    # Incoming datetimes without timezone information are assumed to be in UTC
    if dt.tzinfo:
        if dt.tzinfo is not timezone.utc:
            dt = dt.astimezone(timezone.utc)
        dt = dt.replace(tzinfo=None)
    return dt.isoformat() + 'Z'


def split(dt_str):
    """
    Split the given datetime string into date and time parts.
    Incoming string is assumed to be in format returned by serialize().
    """
    return dt_str[:10], dt_str[11:-1]
