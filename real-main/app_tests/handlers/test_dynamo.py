from app.handlers.dynamo.dispatch import AttributeDispatch, ItemDispatch, attrs


def test_item_dispatch_empty():
    dispatch = ItemDispatch({})
    assert dispatch.search('any', 'thing') == []


def test_item_dispatch_general():
    f1, f2, f3, f4 = abs, all, any, ascii
    dispatch = ItemDispatch(
        {'pk_prefix1': {'sk_prefix11': [f1, f2], 'sk_prefix12': f3}, 'pk_prefix2': {'sk_prefix21': [f4]}}
    )
    assert dispatch.search('nope', 'sk_prefix11') == []
    assert dispatch.search('pk_prefix1', 'sk_prefix21') == []
    assert dispatch.search('pk_prefix1', 'sk_prefix12') == [f3]
    assert dispatch.search('pk_prefix1', 'sk_prefix11') == [f1, f2]
    assert dispatch.search('pk_prefix2', 'sk_prefix21') == [f4]


def test_attrs_empty():
    filterer = attrs()
    assert filterer({'any': 'thing', 'at': 'all'}) == {}
    assert filterer({}) == {}


def test_attrs_general():
    filterer = attrs(k1='d1', k2=None)
    assert filterer({}) == {'k1': 'd1', 'k2': None}
    assert filterer({'this': 'thing', 'at': 'all'}) == {'k1': 'd1', 'k2': None}
    assert filterer({'this': 'thing', 'k1': 'all'}) == {'k1': 'all', 'k2': None}
    assert filterer({'k2': 'thing', 'k1': 'all'}) == {'k1': 'all', 'k2': 'thing'}
    assert filterer({'k2': 'thing'}) == {'k1': 'd1', 'k2': 'thing'}


def test_attribute_dispatch_empty():
    dispatch = AttributeDispatch({})
    assert dispatch.search('any', 'thing', {}, {}) == []
    assert dispatch.search('any', 'thing', {'k1': 'v1'}, {'k1': 'v2'}) == []


def test_attribute_dispatch_general():
    dispatch = AttributeDispatch(
        {
            'pk_prefix1': {
                'sk_prefix11': {'f1': attrs(k1=None), 'f2': attrs(k2='yes')},
                'sk_prefix12': {'f3': attrs(k3=0)},
            },
            'pk_prefix2': {'sk_prefix21': {'f4': attrs(k4=None, k5=0, k6=True)}},
        }
    )
    # check conditions all going to defaults
    assert dispatch.search('nope', 'sk_prefix11', {}, {}) == []
    assert dispatch.search('pk_prefix1', 'sk_prefix21', {}, {}) == []
    assert dispatch.search('pk_prefix1', 'sk_prefix11', {}, {}) == []
    assert dispatch.search('pk_prefix1', 'sk_prefix12', {}, {}) == []
    assert dispatch.search('pk_prefix2', 'sk_prefix21', {}, {}) == []

    # check some conditions set to defaults, some matching
    item = {'k1': None, 'k2': 'yes', 'k3': 0, 'k4': None}
    assert dispatch.search('pk_prefix1', 'sk_prefix11', item, {}) == []
    assert dispatch.search('pk_prefix1', 'sk_prefix12', item, item) == []
    assert dispatch.search('pk_prefix2', 'sk_prefix21', {}, item) == []
    assert dispatch.search('pk_prefix2', 'sk_prefix21', {'k6': True}, {'k5': 0}) == []
    assert dispatch.search('pk_prefix1', 'sk_prefix12', {'other': 42}, {'other': 42, 'k3': 0}) == []

    # check some conditions set to non-defaults
    assert dispatch.search('pk_prefix1', 'sk_prefix11', {'k1': 'foo'}, {'k2': 'bar'}) == ['f1', 'f2']
    assert dispatch.search('pk_prefix1', 'sk_prefix12', {'k3': 42}, {}) == ['f3']
    assert dispatch.search('pk_prefix2', 'sk_prefix21', {'k6': False}, {'k5': 0}) == ['f4']
