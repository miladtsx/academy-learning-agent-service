# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2024 Valory AG
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
# ------------------------------------------------------------------------------

"""This package contains the rounds of DataPullAbciApp."""

from enum import Enum
from typing import Dict, FrozenSet, Optional, Set

from packages.valory.skills.abstract_round_abci.base import (
    AbciApp,
    AbciAppTransitionFunction,
    AppState,
    BaseSynchronizedData,
    CollectSameUntilThresholdRound,
    CollectionRound,
    DegenerateRound,
    DeserializedCollection,
    EventToTimeout,
    get_name,
)
from packages.valory.skills.data_pull_abci.payloads import (
    DataPullPayload,
)


class Event(Enum):
    """DataPullAbciApp Events"""

    DONE = "done"
    ERROR = "error"
    TRANSACT = "transact"
    NO_MAJORITY = "no_majority"
    ROUND_TIMEOUT = "round_timeout"


class SynchronizedData(BaseSynchronizedData):
    """
    Class to represent the synchronized data.

    This data is replicated by the tendermint application, so all the agents share the same data.
    """

    def _get_deserialized(self, key: str) -> DeserializedCollection:
        """Strictly get a collection and return it deserialized."""
        serialized = self.db.get_strict(key)
        return CollectionRound.deserialize_collection(serialized)

    @property
    def price(self) -> Optional[float]:
        """Get the token price."""
        return self.db.get("price", None)

    @property
    def price_ipfs_hash(self) -> Optional[str]:
        """Get the price_ipfs_hash."""
        return self.db.get("price_ipfs_hash", None)

    @property
    def native_balance(self) -> Optional[float]:
        """Get the native balance."""
        return self.db.get("native_balance", None)

    @property
    def erc20_balance(self) -> Optional[float]:
        """Get the erc20 balance."""
        return self.db.get("erc20_balance", None)

    @property
    def erc20_total_supply(self) -> Optional[float]:
        """Get the erc20 total supply."""
        return self.db.get("erc20_total_supply", None)

    @property
    def participant_to_data_round(self) -> DeserializedCollection:
        """Agent to payload mapping for the DataPullRound."""
        return self._get_deserialized("participant_to_data_round")

    @property
    def olas_eth_pair_price(self) -> DeserializedCollection:
        """Agent to payload mapping for the second DataPullRound."""
        return self._get_deserialized("olas_eth_pair_price")

    @property
    def most_voted_tx_hash(self) -> Optional[float]:
        """Get the token most_voted_tx_hash."""
        return self.db.get("most_voted_tx_hash", None)

    @property
    def participant_to_tx_round(self) -> DeserializedCollection:
        """Get the participants to the tx round."""
        return self._get_deserialized("participant_to_tx_round")


class DataPullRound(CollectSameUntilThresholdRound):
    """DataPullRound"""

    payload_class = DataPullPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY

    # Collection key specifies where in the synchronized data the agento to payload mapping will be stored
    collection_key = get_name(SynchronizedData.participant_to_data_round)

    # Selection key specifies how to extract all the different objects from each agent's payload
    # and where to store it in the synchronized data. Notice that the order follows the same order
    # from the payload class.
    selection_key = (
        get_name(SynchronizedData.price),
        get_name(SynchronizedData.price_ipfs_hash),
        get_name(SynchronizedData.native_balance),
        get_name(SynchronizedData.erc20_balance),
        get_name(SynchronizedData.erc20_total_supply),
    )

    # Event.ROUND_TIMEOUT  # this needs to be referenced for static checkers


class IPFSPullRound(CollectSameUntilThresholdRound):
    """IPFSPullRound"""

    payload_class = DataPullPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY

    collection_key = get_name(SynchronizedData.olas_eth_pair_price)

    selection_key = (get_name(SynchronizedData.olas_eth_pair_price))

    # Event.ROUND_TIMEOUT  # this needs to be referenced for static checkers


class FinishedDataPullRound(DegenerateRound):
    """FinishedDataPullRound"""


class DataPullAbciApp(AbciApp[Event]):
    """DataPullAbciApp"""

    initial_round_cls: AppState = DataPullRound
    initial_states: Set[AppState] = {
        DataPullRound,
    }
    transition_function: AbciAppTransitionFunction = {
        DataPullRound: {
            Event.NO_MAJORITY: DataPullRound,
            Event.ROUND_TIMEOUT: DataPullRound,
            Event.DONE: IPFSPullRound,
        },
        IPFSPullRound: {
            Event.NO_MAJORITY: IPFSPullRound,
            Event.ROUND_TIMEOUT: IPFSPullRound,
            Event.DONE: FinishedDataPullRound,
        },
        FinishedDataPullRound: {},
    }
    final_states: Set[AppState] = {
        FinishedDataPullRound,
    }
    event_to_timeout: EventToTimeout = {}
    cross_period_persisted_keys: FrozenSet[str] = frozenset()
    db_pre_conditions: Dict[AppState, Set[str]] = {
        DataPullRound: set(),
    }
    db_post_conditions: Dict[AppState, Set[str]] = {
        FinishedDataPullRound: set(),
    }
