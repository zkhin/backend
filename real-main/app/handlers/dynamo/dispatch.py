import logging

logger = logging.getLogger()


class ItemDispatch:
    """
    A dispatcher that holds and allows searching over a catalogue of listener functions.
    """

    def __init__(self, listeners):
        "See usage examples for required format of `listeners`"
        self.listeners = listeners

    def search(self, pk_prefix, sk_prefix):
        "Returns a list of matching listener functions"
        resp = self.listeners.get(pk_prefix, {}).get(sk_prefix, [])
        return [resp] if callable(resp) else resp


class AttributeDispatch:
    """
    A dispatcher that holds and allows searching over a catalogue of listener functions
    according to matching conditions which should trigger a call.
    """

    def __init__(self, listeners):
        "See usage examples for required format of `listeners`"
        self.listeners = listeners

    def search(self, pk_prefix, sk_prefix, old_item, new_item):
        "Returns a list of matching listener functions"
        funcs_to_conditions = self.listeners.get(pk_prefix, {}).get(sk_prefix, {})
        return [func for func, cond in funcs_to_conditions.items() if cond(old_item) != cond(new_item)]


def attrs(**attrs_to_defaults):
    "Returns a callable that will filter down an item to the given keys, using the values as defaults"
    return lambda item: {attr: item.get(attr, default) for attr, default in attrs_to_defaults.items()}
