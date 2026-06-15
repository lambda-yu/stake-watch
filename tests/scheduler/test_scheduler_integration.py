from unittest.mock import AsyncMock
import pytest
from stake_watch.scheduler.runner import ScheduledRunner

@pytest.mark.asyncio
async def test_scheduled_runner_registers_jobs():
    mock = AsyncMock()
    scheduled = ScheduledRunner(collection_runner=mock, position_interval=300, stats_interval=900)
    assert scheduled.position_interval == 300
    assert scheduled.stats_interval == 900

@pytest.mark.asyncio
async def test_scheduled_runner_can_trigger_manual():
    mock = AsyncMock()
    mock.run_collection_cycle.return_value = []
    scheduled = ScheduledRunner(collection_runner=mock, position_interval=300, stats_interval=900)
    await scheduled.trigger_now()
    mock.run_collection_cycle.assert_called_once()
