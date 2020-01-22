from datetime import datetime, timezone

import pytest

from app.lib import datetime as real_datetime


def test_parse_datetime_string_successes():
    dt = real_datetime.parse('2019-01-01T01:01:01Z')
    assert dt.isoformat() == '2019-01-01T01:01:01'

    dt = real_datetime.parse('2019-01-01T01:01:01+00:00')
    assert dt.isoformat() == '2019-01-01T01:01:01'

    dt = real_datetime.parse('2019-01-01T01:01:01+01:00')
    assert dt.isoformat() == '2019-01-01T00:01:01'

    dt = real_datetime.parse('2019-01-01T01:01:01-01:00')
    assert dt.isoformat() == '2019-01-01T02:01:01'

    # AWSDateTime graphql scalar type supports seconds on the timezone field
    dt = real_datetime.parse('2019-01-01T01:01:01+00:00:01')
    assert dt.isoformat() == '2019-01-01T01:01:00'

    dt = real_datetime.parse('2019-01-01T01:01:01.023Z')
    assert dt.isoformat() == '2019-01-01T01:01:01.023000'

    dt = real_datetime.parse('2019-01-01T01:01:01.023546Z')
    assert dt.isoformat() == '2019-01-01T01:01:01.023546'

    dt = real_datetime.parse(None)
    assert dt is None


def test_parse_datetime_string_failures():
    with pytest.raises(AssertionError):
        real_datetime.parse('2019-01-01T01:01:01')

    with pytest.raises(Exception):
        real_datetime.parse('2019-01-01')

    with pytest.raises(Exception):
        real_datetime.parse(42)


def test_serialize_datetime():
    # UTC assumed
    dt = datetime.fromisoformat('2019-01-01T01:01:01')
    assert real_datetime.serialize(dt) == '2019-01-01T01:01:01Z'

    dt = datetime.fromisoformat('2019-01-01T01:01:01')
    dt.replace(tzinfo=timezone.utc)
    assert real_datetime.serialize(dt) == '2019-01-01T01:01:01Z'

    dt = datetime.fromisoformat('2019-01-01T01:01:01+01:00')
    assert real_datetime.serialize(dt) == '2019-01-01T00:01:01Z'


def test_split_datetime():
    dt_str = '2019-01-01T05:06:03.232Z'
    date_str, time_str = real_datetime.split(dt_str)
    assert date_str == '2019-01-01'
    assert time_str == '05:06:03.232'
