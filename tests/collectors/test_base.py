import pytest
from stake_watch.collectors.base import BaseCollector, CollectResult
from stake_watch.models.common import Chain

def test_base_collector_is_abstract():
    with pytest.raises(TypeError):
        BaseCollector(chain=Chain.BASE, protocol="test")

def test_collect_result_creation():
    result = CollectResult(positions=[], protocol_stats=None, errors=[])
    assert result.positions == []
    assert result.protocol_stats is None
    assert result.errors == []
