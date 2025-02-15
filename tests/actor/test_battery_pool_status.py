# License: MIT
# Copyright © 2023 Frequenz Energy-as-a-Service GmbH
"""Tests for BatteryPoolStatus."""

import asyncio
from typing import Set

import pytest
from frequenz.channels import Broadcast
from pytest_mock import MockerFixture

from frequenz.sdk.actor.power_distributing._battery_pool_status import (
    BatteryPoolStatus,
    BatteryStatus,
)
from frequenz.sdk.microgrid.component import ComponentCategory

from ..utils.mock_microgrid_client import MockMicrogridClient
from .test_battery_status import battery_data, component_graph, inverter_data


# pylint: disable=protected-access
class TestBatteryPoolStatus:
    """Tests for BatteryPoolStatus"""

    @pytest.fixture
    async def mock_microgrid(self, mocker: MockerFixture) -> MockMicrogridClient:
        """Create and initialize mock microgrid

        Args:
            mocker: pytest mocker

        Returns:
            MockMicrogridClient
        """
        components, connections = component_graph()
        microgrid = MockMicrogridClient(components, connections)
        microgrid.initialize(mocker)
        return microgrid

    async def test_batteries_status(self, mock_microgrid: MockMicrogridClient) -> None:
        """Basic tests for BatteryPoolStatus.

        BatteryStatusTracker is more tested in its own unit tests.

        Args:
            mock_microgrid: mock microgrid client
        """
        batteries = {
            battery.component_id
            for battery in mock_microgrid.component_graph.components(
                component_category={ComponentCategory.BATTERY}
            )
        }
        battery_status_channel = Broadcast[BatteryStatus]("battery_status")
        battery_status_recv = battery_status_channel.new_receiver(maxsize=1)
        batteries_status = BatteryPoolStatus(
            battery_ids=batteries,
            battery_status_sender=battery_status_channel.new_sender(),
            max_data_age_sec=5,
            max_blocking_duration_sec=30,
        )
        await asyncio.sleep(0.1)

        expected_working: Set[int] = set()
        assert batteries_status.get_working_batteries(batteries) == expected_working

        batteries_list = list(batteries)

        await mock_microgrid.send(battery_data(component_id=batteries_list[0]))
        await asyncio.sleep(0.1)
        assert batteries_status.get_working_batteries(batteries) == expected_working

        expected_working.add(batteries_list[0])
        await mock_microgrid.send(inverter_data(component_id=batteries_list[0] - 1))
        await asyncio.sleep(0.1)
        assert batteries_status.get_working_batteries(batteries) == expected_working
        msg = await asyncio.wait_for(battery_status_recv.receive(), timeout=0.2)
        assert msg == batteries_status._current_status

        await mock_microgrid.send(inverter_data(component_id=batteries_list[1] - 1))
        await mock_microgrid.send(battery_data(component_id=batteries_list[1]))

        await mock_microgrid.send(inverter_data(component_id=batteries_list[2] - 1))
        await mock_microgrid.send(battery_data(component_id=batteries_list[2]))

        expected_working = set(batteries_list)
        await asyncio.sleep(0.1)
        assert batteries_status.get_working_batteries(batteries) == expected_working
        msg = await asyncio.wait_for(battery_status_recv.receive(), timeout=0.2)
        assert msg == batteries_status._current_status

        await batteries_status.update_status(
            succeed_batteries={106}, failed_batteries={206, 306}
        )
        await asyncio.sleep(0.1)
        assert batteries_status.get_working_batteries(batteries) == {106}

        await batteries_status.update_status(
            succeed_batteries={106, 206}, failed_batteries=set()
        )
        await asyncio.sleep(0.1)
        assert batteries_status.get_working_batteries(batteries) == {106, 206}

        await batteries_status.stop()
