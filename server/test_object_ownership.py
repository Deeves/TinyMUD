from __future__ import annotations

from world import Object


def test_owner_id_default_none_and_persistence():
    # Default owner_id is None
    o = Object(display_name="Test Item")
    assert getattr(o, 'owner_id', None) is None

    # to_dict includes owner_id key with None
    d = o.to_dict()
    assert 'owner_id' in d
    assert d['owner_id'] is None

    # from_dict missing owner_id -> None
    o2 = Object.from_dict({
        'display_name': 'Thing',
        'object_tag': ['small'],
    })
    assert getattr(o2, 'owner_id', None) is None

    # from_dict with owner_id populates field
    o3 = Object.from_dict({
        'display_name': 'Owned',
        'object_tag': ['small'],
        'owner_id': 'abc-123',
    })
    assert getattr(o3, 'owner_id', None) == 'abc-123'
