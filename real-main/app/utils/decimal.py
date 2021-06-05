from decimal import BasicContext, Decimal
from json import JSONEncoder


def to_decimal(value):
    return Decimal(value).normalize(context=BasicContext) if value is not None else None


class DecimalJsonEncoder(JSONEncoder):
    "Helper class that can handle encoding decimals into json (as floats, percision lost)"

    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalJsonEncoder, self).default(obj)


class DecimalAsStringJsonEncoder(JSONEncoder):
    "Helper class that can handle encoding decimals into json (as strings, no percision lost)"

    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super(DecimalAsStringJsonEncoder, self).default(obj)
