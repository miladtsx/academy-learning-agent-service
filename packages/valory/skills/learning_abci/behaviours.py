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

"""This package contains round behaviours of LearningAbciApp."""

import json
from abc import ABC
from pathlib import Path
from tempfile import mkdtemp
from typing import Dict, Generator, Optional, Set, Type, cast
from packages.valory.skills.learning_abci.models import Invoice

from packages.valory.skills.abstract_round_abci.base import AbstractRound
from packages.valory.skills.abstract_round_abci.behaviours import (
    AbstractRoundBehaviour,
    BaseBehaviour,
)
from packages.valory.skills.learning_abci.models import (
    CoingeckoSpecs,
    Params,
    SharedState,
)
from packages.valory.skills.learning_abci.payloads import (
    InvoicesPayload,
    DecisionMakingPayload,
    KeeperPayload,
    ConfirmationResultPayload,
)
from packages.valory.skills.learning_abci.rounds import (
    CollectInvoicesRound,
    DecisionMakingRound,
    LearningAbciApp,
    SelectKeeperRound,
    SynchronizedData,
    ConfirmationRound,
)

# Define some constants
ZERO_VALUE = 0
HTTP_OK = 200
GNOSIS_CHAIN_ID = "gnosis"
EMPTY_CALL_DATA = b"0x"
SAFE_GAS = 0
VALUE_KEY = "value"
TO_ADDRESS_KEY = "to_address"
METADATA_FILENAME = "metadata.json"


class LearningBaseBehaviour(BaseBehaviour, ABC):  # pylint: disable=too-many-ancestors
    """Base behaviour for the learning_abci behaviours."""

    @property
    def params(self) -> Params:
        """Return the params. Configs go here"""
        return cast(Params, super().params)

    @property
    def synchronized_data(self) -> SynchronizedData:
        """Return the synchronized data. This data is common to all agents"""
        return cast(SynchronizedData, super().synchronized_data)

    @property
    def local_state(self) -> SharedState:
        """Return the local state of this particular agent."""
        return cast(SharedState, self.context.state)

    @property
    def coingecko_specs(self) -> CoingeckoSpecs:
        """Get the Coingecko api specs."""
        return self.context.coingecko_specs

    @property
    def metadata_filepath(self) -> str:
        """Get the temporary filepath to the metadata."""
        return str(Path(mkdtemp()) / METADATA_FILENAME)

    def get_sync_timestamp(self) -> float:
        """Get the synchronized time from Tendermint's last block."""
        now = cast(
            SharedState, self.context.state
        ).round_sequence.last_round_transition_timestamp.timestamp()

        return now


class CollectInvoicesBehaviour(
    LearningBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """
    This behaviours collects the invoices from the business API

    For the purpose of the Demo, the Invoices are read from a local JSON file.
    """

    matching_round: Type[AbstractRound] = CollectInvoicesRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():

            # fetch invoices in batch
            invoices = self.read_invoices()
            print(f"Invoices read: {invoices}")

            delay = 10  # TODO make it parametric
            if not invoices:
                self.context.logger.info(
                    f"NO INVOICE FOUND; TRYINGN AGAIN IN {delay} Seconds."
                )
                yield from self.sleep(delay)
                return

            invoices_stringified = json.dumps(
                [invoice.to_dict() for invoice in invoices]
            )
            # Prepare the payload to be shared with other agents
            # After consensus, all the agents will have the same price, price_ipfs_hash and balance variables in their synchronized data
            payload = InvoicesPayload(
                sender=self.context.agent_address, invoices=invoices_stringified
            )

        # Send the payload to all agents and mark the behaviour as done
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def read_invoices(self, limit: int = None) -> Optional[set[Invoice]]:
        """
        Read the unsetteled invoices from the Business API

        For the demo, there is a mock JSON file presenting the Invoices

        Returns: [Invoice] or None
        """
        invoices_path = Path("../invoices/invoices.json").resolve()

        if not invoices_path.exists():
            raise Exception(f"Error: The file {invoices_path} was not found.")

        try:
            with invoices_path.open("r", encoding="utf-8") as file:
                # TODO Load invoices from the API
                invoices_data = json.load(file)
                if not invoices_data or not len(invoices_data):
                    return None
                # Decerialized Invoice JSON into Object
                invoices = [Invoice(**invoice) for invoice in invoices_data]
                # Return only the first 'limit' invoices if 'limit' is provided
                return invoices if limit is None else invoices[:limit]
        except json.JSONDecodeError:
            self.context.logger.error("Error: Failed to decode JSON from the file.")
            return None
        except Exception as e:
            self.context.logger.error(f"An unexpected error occurred: {e}")
            return None


class DecisionMakingBehaviour(
    LearningBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """DecisionMakingBehaviour"""

    matching_round: Type[AbstractRound] = DecisionMakingRound

    def async_act(self) -> Generator:
        """Make a decision: are invoices settled."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            invoices = self.synchronized_data.invoices

            # Deserialize invoices from JSON string to Invoice objects
            invoices_json = json.loads(invoices)
            invoices = [Invoice(**invoice) for invoice in invoices_json]
            self.context.logger.info(
                f"Successfully deserialized {len(invoices)} invoices."
            )

            new_settled_invoices_uuids: list[str] = []

            for invoice in invoices:
                # Pass invoices that are already settled
                if invoice.is_settled:
                    self.context.logger.error(
                        f"Attempted to process already settled invoice: {invoice.uuid}"
                    )
                    continue
                else:
                    self.context.logger.info(
                        f"Processing unsettled invoice: {invoice.uuid}"
                    )

                    invoice.is_settled = self.is_invoice_settled(invoice=invoice)

                    if invoice.is_settled:
                        # identify the settled invoices
                        new_settled_invoices_uuids.append(invoice.uuid)

            self.update_mock_invoices(invoices)

            new_settled_invoices_uuids_stringified: str = ""

            if not len(new_settled_invoices_uuids):
                self.context.logger.info(
                    "ALL INVOICES ARE ALREADY SETTLED; FETCHING INVOICES AGAIN IN 10 SECONDS."
                )
                # right now, if there is no newly settled invoices, we pass to the next round with an empty settled_invoices_uuid payload. 
                # instead we should return back to the CollectInvoicesRound. but currently I don't know how to implement this.
                # yield from self.sleep(10)  # TODO make it parametric
                # TODO Question: return back to the CollectInvoicesRound round.
                pass
            else:
                new_settled_invoices_uuids_stringified = json.dumps(
                    new_settled_invoices_uuids
                )
                self.context.logger.info(f"Count of newly settled invoices: {len(new_settled_invoices_uuids)}")

            payload = DecisionMakingPayload(
                sender=sender,
                settled_invoices_uuid=new_settled_invoices_uuids_stringified,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def is_invoice_settled(self, invoice: Invoice) -> Generator[None, None, bool]:
        # TODO query on-chain
        self.context.logger.info(
            f"Checking if the invoice: {invoice.uuid} is settled ..."
        )
        return True

    def update_mock_invoices(self, invoices: set[Invoice]):
        # TODO MOCK BACKEND - UPDATE THE INVOICES
        updated_invoices_json = json.dumps([invoice.to_dict() for invoice in invoices])
        invoices_path = Path("../invoices/invoices.json").resolve()
        with invoices_path.open("w") as file:
            file.write(updated_invoices_json)


class SelectKeeperBehaviour(
    LearningBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """SelectKeeperBehaviour"""

    matching_round: Type[AbstractRound] = SelectKeeperRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        # TODO select a keeper randomly
        sender = self.context.agent_address
        print("selected_keeper_raw", sender)
        payload = KeeperPayload(sender=sender, selected_keeper=sender)

        yield from self.send_a2a_transaction(payload)
        yield from self.wait_until_round_end()

        self.set_done()


class ConfirmationBehaviour(
    LearningBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """ConfirmationBehaviour"""

    matching_round: Type[AbstractRound] = ConfirmationRound

    def _i_am_not_sending(self) -> bool:
        """Indicates if the current agent is the sender or not."""
        print("self.context.agent_address", self.context.agent_address)
        print(
            "self.synchronized_data.selected_keeper",
            self.synchronized_data.selected_keeper,
        )
        return self.context.agent_address != self.synchronized_data.selected_keeper

    def async_act(self) -> Generator:
        """
        Do the action.

         Steps:
        - If the agent is the keeper, then invoke the webhook and confirm settlement.
        - Otherwise, wait until the next round.
        """

        if self._i_am_not_sending():
            yield from self._not_sender_act()
        else:
            yield from self._sender_act()

    def _sender_act(self) -> Generator[None, None, None]:
        """Do the sender action."""

        sender = self.context.agent_address
        self.context.logger.info(
            "I am the designated sender, attempting to invoke the webhook..."
        )

        selected_keeper = self.synchronized_data.selected_keeper
        result: Dict[str, bool] = {}
        if self.synchronized_data.settled_invoices_uuid:
            print(
                "self.synchronized_data.settled_invoices_uuid",
                self.synchronized_data.settled_invoices_uuid,
            )
            settled_invoices = json.loads(self.synchronized_data.settled_invoices_uuid)

            if len(settled_invoices):
                print("selected_keeper", selected_keeper)
                print("settled_invoices", settled_invoices)

                for uuid in settled_invoices:
                    print("SIMULATING WEBHOOK CALL for: ", uuid)
                    webhook_result = yield from self._call_webhook()
                    result[uuid] = webhook_result
            else:
                pass

            print("len(settled_invoices)", len(settled_invoices))
        print("webhooks result", result)

        payload = ConfirmationResultPayload(sender=sender, is_webhook_ok=True)

        yield from self.send_a2a_transaction(payload)
        yield from self.wait_until_round_end()

        self.set_done()

    def _not_sender_act(self) -> Generator:
        """Do the non-sender action."""
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            self.context.logger.info(
                f"Waiting for the keeper to do its keeping: {self.synchronized_data.selected_keeper}"
            )
            yield from self.wait_until_round_end()
        self.set_done()

    def _call_webhook(self) -> Generator:
        # TODO implement
        yield from self.sleep(3)
        return True


class LearningRoundBehaviour(AbstractRoundBehaviour):
    """LearningRoundBehaviour"""

    initial_behaviour_cls = CollectInvoicesBehaviour
    abci_app_cls = LearningAbciApp  # type: ignore
    behaviours: Set[Type[BaseBehaviour]] = [  # type: ignore
        CollectInvoicesBehaviour,
        DecisionMakingBehaviour,
        SelectKeeperBehaviour,
        ConfirmationBehaviour,
    ]
