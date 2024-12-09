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

"""This package contains the rounds of LearningAbciApp."""

from abc import ABC
from enum import Enum
from typing import Dict, FrozenSet, Mapping, Optional, Set, Tuple, Type, cast
from packages.valory.skills.abstract_round_abci.base import (
    AbciApp,
    AbciAppTransitionFunction,
    AbstractRound,
    AppState,
    BaseSynchronizedData,
    CollectDifferentUntilAllRound,
    CollectSameUntilThresholdRound,
    CollectionRound,
    DegenerateRound,
    DeserializedCollection,
    EventToTimeout,
    OnlyKeeperSendsRound,
    get_name,
)
from packages.valory.skills.learning_abci.payloads import (
    InvoicesPayload,
    DecisionMakingPayload,
    KeeperPayload,
    ConfirmationResultPayload,
)


class Event(Enum):
    """LearningAbciApp Events"""

    DONE = "done"
    ERROR = "error"
    NO_INVOICE = "no_invoice"
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

    # DATA PULL ROUND
    @property
    def participant_to_invoices(self) -> Mapping[str, InvoicesPayload]:
        """Get the participant_to_invoices."""
        return cast(
            Mapping[str, InvoicesPayload],
            self._get_deserialized("participant_to_invoices"),
        )

    # @property
    # def collected_invoices(self) -> List[str]:
    #     """Get the invoices."""
    #     return (
    #         value.invoices for value in self.participant_to_invoices.values()
    #     )

    # ON-CHAIN MONITORING ROUND
    @property
    def agent_on_chain_monitoring_round(self) -> Optional[set[str]]:
        """List of onchain monitoring gathered by agents"""
        return self.db.get("agent_on_chain_monitoring_round")

    @property
    def invoices(self) -> Optional[str]:
        """Get the list of Invoices"""
        return self.db.get("invoices", None)

    @property
    def agent_to_invoices_round(self) -> DeserializedCollection:
        """
        Agent to payload mapping for
            the CollectInvoicesRound, passing the invoices received from the business API to the DecisionMakingRound
        """
        return self._get_deserialized("agent_to_invoices_round")

    @property
    def participant_to_webhook_round(self) -> DeserializedCollection:
        """
        Agent to payload mapping for the DecisionMakingRound;
        passing the uuid of the invoices that are settled and must be updated via the Webhook.
        """
        return self._get_deserialized("participant_to_webhook_round")

    @property
    def settled_invoices_uuid(self) -> Optional[str]:
        """Get the list of settled invoices"""
        return self.db.get("settled_invoices_uuid", None)

    @property
    def participant_to_select_keeper_round(self) -> DeserializedCollection:
        """
        Selected Keeper at the SelectKeeperBehaviour;
        """
        return self._get_deserialized("participant_to_select_keeper_round")

    @property
    def selected_keeper(self) -> Optional[str]:
        """Get the selected keeper address"""
        return self.db.get("selected_keeper", None)

    @property
    def participant_to_webhook_ok(self) -> DeserializedCollection:
        """
        Selected Keeper at the ConfirmationRound;
        """
        return self._get_deserialized("participant_to_webhook_ok")

    @property
    def is_webhook_ok(self) -> Optional[bool]:
        """Get the webhook status"""
        return self.db.get("is_webhook_ok", None)

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
    def most_voted_tx_hash(self) -> Optional[float]:
        """Get the token most_voted_tx_hash."""
        return self.db.get("most_voted_tx_hash", None)

    @property
    def participant_to_tx_round(self) -> DeserializedCollection:
        """Get the participants to the tx round."""
        return self._get_deserialized("participant_to_tx_round")

    @property
    def tx_submitter(self) -> str:
        """Get the round that submitted a tx to transaction_settlement_abci."""
        return str(self.db.get_strict("tx_submitter"))


class DPAYABCIAbstractRound(AbstractRound, ABC):
    """Abstract round for the DCPAY ABCI skill."""

    synchronized_data_class: Type[BaseSynchronizedData] = SynchronizedData

    @property
    def synchronized_data(self) -> SynchronizedData:
        """Return the synchronized data."""
        return cast(SynchronizedData, self._synchronized_data)


class CollectInvoicesRound(CollectSameUntilThresholdRound, DPAYABCIAbstractRound):
    """CollectInvoicesRound"""

    payload_class = InvoicesPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY

    collection_key = get_name(SynchronizedData.participant_to_invoices)
    selection_key = (get_name(SynchronizedData.invoices))


class DecisionMakingRound(CollectSameUntilThresholdRound, DPAYABCIAbstractRound):
    """
    DecisionMakingRound

    Monitor onchain events to see if an invoice is settled.
    """

    payload_class = DecisionMakingPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY
    collection_key = get_name(SynchronizedData.participant_to_webhook_round)
    selection_key = (get_name(SynchronizedData.settled_invoices_uuid))


class SelectKeeperRound(CollectSameUntilThresholdRound, DPAYABCIAbstractRound):
    """
    SelectKeeperRound
    Select the agent to invoke the webhook.
    """

    payload_class = KeeperPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY

    collection_key = get_name(SynchronizedData.participant_to_select_keeper_round)
    selection_key = get_name(SynchronizedData.selected_keeper)


class ConfirmationRound(CollectDifferentUntilAllRound, DPAYABCIAbstractRound):
    """
    Confirm the invoice settlement via the webhook so the business can continue the purchase flow.
    """

    keeper_payload: Optional[ConfirmationResultPayload] = None
    payload_class = ConfirmationResultPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE

    collection_key = get_name(SynchronizedData.participant_to_webhook_ok)
    selection_key = get_name(SynchronizedData.is_webhook_ok)

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""

        if self.collection_threshold_reached:
            synchronized_data = self.synchronized_data.update(
                participants=tuple(sorted(self.collection)),
                synchronized_data_class=SynchronizedData,
            )
            return synchronized_data, Event.DONE
        return None


class FinishedRound(DegenerateRound):
    """FinishedRound"""


class LearningAbciApp(AbciApp[Event]):
    """LearningAbciApp"""

    initial_round_cls: AppState = CollectInvoicesRound
    initial_states: Set[AppState] = {
        CollectInvoicesRound,
    }
    transition_function: AbciAppTransitionFunction = {
        CollectInvoicesRound: {
            Event.NO_MAJORITY: CollectInvoicesRound,
            Event.ROUND_TIMEOUT: CollectInvoicesRound,
            Event.NO_INVOICE: CollectInvoicesRound,
            Event.DONE: DecisionMakingRound,
        },
        DecisionMakingRound: {
            Event.NO_MAJORITY: CollectInvoicesRound,
            Event.ROUND_TIMEOUT: DecisionMakingRound,
            Event.DONE: SelectKeeperRound,
            Event.ERROR: CollectInvoicesRound,
            Event.NO_INVOICE: CollectInvoicesRound,
        },
        SelectKeeperRound: {
            Event.NO_MAJORITY: SelectKeeperRound,
            Event.ROUND_TIMEOUT: SelectKeeperRound,
            Event.DONE: ConfirmationRound,
            Event.ERROR: SelectKeeperRound,
            Event.NO_INVOICE: CollectInvoicesRound,
        },
        ConfirmationRound: {
            Event.NO_MAJORITY: ConfirmationRound,
            Event.ROUND_TIMEOUT: ConfirmationRound,
            Event.DONE: FinishedRound,
        },
        FinishedRound: {},
    }
    final_states: Set[AppState] = {
        FinishedRound,
    }
    event_to_timeout: EventToTimeout = {}
    cross_period_persisted_keys: FrozenSet[str] = frozenset()
    db_pre_conditions: Dict[AppState, Set[str]] = {
        CollectInvoicesRound: set(),
    }
    db_post_conditions: Dict[AppState, Set[str]] = {
        FinishedRound: set(),
    }
