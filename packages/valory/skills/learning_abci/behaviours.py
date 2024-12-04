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

from abc import ABC
from typing import Dict, Generator, Optional, Set, Type, cast

from packages.valory.contracts.erc20.contract import ERC20
from packages.valory.contracts.gnosis_safe.contract import (
    GnosisSafeContract,
    SafeOperation,
)
from packages.valory.contracts.multisend.contract import (
    MultiSendContract,
    MultiSendOperation,
)
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.protocols.ledger_api import LedgerApiMessage
from packages.valory.skills.abstract_round_abci.base import AbstractRound
from packages.valory.skills.abstract_round_abci.behaviours import (
    AbstractRoundBehaviour,
    BaseBehaviour,
)
from packages.valory.skills.abstract_round_abci.io_.store import SupportedFiletype
from packages.valory.skills.learning_abci.models import (
    Params,
    SharedState,
)
from packages.valory.skills.learning_abci.payloads import (
    DecisionMakingPayload,
    TxPreparationPayload,
)
from packages.valory.skills.learning_abci.rounds import (
    DecisionMakingRound,
    Event,
    LearningAbciApp,
    SynchronizedData,
    TxPreparationRound,
)
from packages.valory.skills.transaction_settlement_abci.payload_tools import (
    hash_payload_to_hex,
)
from packages.valory.skills.transaction_settlement_abci.rounds import TX_HASH_LENGTH


# Define some constants
ZERO_VALUE = 0
GNOSIS_CHAIN_ID = "gnosis"
EMPTY_CALL_DATA = b"0x"
SAFE_GAS = 0
VALUE_KEY = "value"
TO_ADDRESS_KEY = "to_address"


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

    def get_sync_timestamp(self) -> float:
        """Get the synchronized time from Tendermint's last block."""
        now = cast(
            SharedState, self.context.state
        ).round_sequence.last_round_transition_timestamp.timestamp()

        return now


class DecisionMakingBehaviour(
    LearningBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """DecisionMakingBehaviour"""

    matching_round: Type[AbstractRound] = DecisionMakingRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address

            # Make a decision: either transact or not
            event = yield from self.get_next_event()

            payload = DecisionMakingPayload(sender=sender, event=event)

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_next_event(self) -> Generator[None, None, str]:
        """Get the next event: decide whether ot transact or not based on some data."""

        # This method showcases how to make decisions based on conditions.
        # This is just a dummy implementation.

        # Get the latest block number from the chain
        block_number = yield from self.get_block_number()

        # We stored the price using two approaches: synchronized_data and IPFS
        # Similarly, we retrieve using the corresponding ways

        # If we fail to get the block number, we send the ERROR event
        if not block_number:
            self.context.logger.info("Block number is None. Sending the ERROR event...")
            return Event.ERROR.value

        # ALWAYS TRANSCT
        return Event.TRANSACT.value

    def get_block_number(self) -> Generator[None, None, Optional[int]]:
        """Get the block number"""

        # Call the ledger connection (equivalent to web3.py)
        ledger_api_response = yield from self.get_ledger_api_response(
            performative=LedgerApiMessage.Performative.GET_STATE,
            ledger_callable="get_block_number",
            chain_id=GNOSIS_CHAIN_ID,
        )

        # Check for errors on the response
        if ledger_api_response.performative != LedgerApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Error while retrieving block number: {ledger_api_response}"
            )
            return None

        # Extract and return the block number
        block_number = cast(
            int, ledger_api_response.state.body["get_block_number_result"]
        )

        self.context.logger.error(f"Got block number: {block_number}")

        return block_number


class TxPreparationBehaviour(
    LearningBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """TxPreparationBehaviour"""

    matching_round: Type[AbstractRound] = TxPreparationRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address

            # Get the transaction hash
            tx_hash = yield from self.get_erc20_transfer_safe_tx_hash()

            payload = TxPreparationPayload(
                sender=sender, tx_submitter=self.auto_behaviour_id(), tx_hash=tx_hash
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_tx_hash(self) -> Generator[None, None, Optional[str]]:
        """Get the transaction hash"""

        # Here want to showcase how to prepare different types of transactions.
        # Depending on the timestamp's last number, we will make a native transaction,
        # an ERC20 transaction or both.

        # All transactions need to be sent from the Safe controlled by the agents.

        # Again, make a decision based on the timestamp (on its last number)
        now = int(self.get_sync_timestamp())
        self.context.logger.info(f"Timestamp is {now}")
        last_number = int(str(now)[-1])

        # Native transaction (Safe -> recipient)
        if last_number in [0, 1, 2, 3]:
            self.context.logger.info("Preparing a native transaction")
            tx_hash = yield from self.get_native_transfer_safe_tx_hash()
            return tx_hash

        # ERC20 transaction (Safe -> recipient)
        if last_number in [4, 5, 6]:
            self.context.logger.info("Preparing an ERC20 transaction")
            tx_hash = yield from self.get_erc20_transfer_safe_tx_hash()
            return tx_hash

        # Multisend transaction (both native and ERC20) (Safe -> recipient)
        self.context.logger.info("Preparing a multisend transaction")
        tx_hash = yield from self.get_multisend_safe_tx_hash()
        return tx_hash

    def get_native_transfer_safe_tx_hash(self) -> Generator[None, None, Optional[str]]:
        """Prepare a native safe transaction"""

        # Transaction data
        # This method is not a generator, therefore we don't use yield from
        data = self.get_native_transfer_data()

        # Prepare safe transaction
        safe_tx_hash = yield from self._build_safe_tx_hash(**data)
        self.context.logger.info(f"Native transfer hash is {safe_tx_hash}")

        return safe_tx_hash

    def get_native_transfer_data(self) -> Dict:
        """Get the native transaction data"""
        # Send 1 wei to the recipient
        data = {VALUE_KEY: 1, TO_ADDRESS_KEY: self.params.transfer_target_address}
        self.context.logger.info(f"Native transfer data is {data}")
        return data

    def get_erc20_transfer_safe_tx_hash(self) -> Generator[None, None, Optional[str]]:
        """Prepare an ERC20 safe transaction"""

        # Transaction data
        data_hex = yield from self.get_erc20_transfer_data()

        # Check for errors
        if data_hex is None:
            return None

        # Prepare safe transaction
        safe_tx_hash = yield from self._build_safe_tx_hash(
            to_address=self.params.transfer_target_address, data=bytes.fromhex(data_hex)
        )

        self.context.logger.info(f"ERC20 transfer hash is {safe_tx_hash}")

        return safe_tx_hash

    def get_erc20_transfer_data(self) -> Generator[None, None, Optional[str]]:
        """Get the ERC20 transaction data"""

        self.context.logger.info("Preparing ERC20 transfer transaction")

        # Use the contract api to interact with the ERC20 contract
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_RAW_TRANSACTION,  # type: ignore
            contract_address=self.params.olas_token_address,
            contract_id=str(ERC20.contract_id),
            contract_callable="build_transfer_tx",
            recipient=self.params.transfer_target_address,
            amount=10000000000000000000,
            chain_id=GNOSIS_CHAIN_ID,
        )

        # Check that the response is what we expect
        if response_msg.performative != ContractApiMessage.Performative.RAW_TRANSACTION:
            self.context.logger.error(
                f"Error while retrieving the balance: {response_msg}"
            )
            return None

        data_bytes: Optional[bytes] = response_msg.raw_transaction.body.get(
            "data", None
        )

        # Ensure that the data is not None
        if data_bytes is None:
            self.context.logger.error(
                f"Error while preparing the transaction: {response_msg}"
            )
            return None

        data_hex = data_bytes.hex()
        self.context.logger.info(f"ERC20 transfer data is {data_hex}")
        return data_hex

    def get_multisend_safe_tx_hash(self) -> Generator[None, None, Optional[str]]:
        """Get a multisend transaction hash"""
        # Step 1: we prepare a list of transactions
        # Step 2: we pack all the transactions in a single one using the mulstisend contract
        # Step 3: we wrap the multisend call inside a Safe call, as always

        multi_send_txs = []

        # Native transfer
        native_transfer_data = self.get_native_transfer_data()
        multi_send_txs.append(
            {
                "operation": MultiSendOperation.CALL,
                "to": self.params.transfer_target_address,
                "value": native_transfer_data[VALUE_KEY],
                # No data key in this transaction, since it is a native transfer
            }
        )

        # ERC20 transfer
        erc20_transfer_data_hex = yield from self.get_erc20_transfer_data()

        if erc20_transfer_data_hex is None:
            return None

        multi_send_txs.append(
            {
                "operation": MultiSendOperation.CALL,
                "to": self.params.olas_token_address,
                "value": ZERO_VALUE,
                "data": bytes.fromhex(erc20_transfer_data_hex),
            }
        )

        # Multisend call
        contract_api_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_RAW_TRANSACTION,  # type: ignore
            contract_address=self.params.multisend_address,
            contract_id=str(MultiSendContract.contract_id),
            contract_callable="get_tx_data",
            multi_send_txs=multi_send_txs,
            chain_id=GNOSIS_CHAIN_ID,
        )

        # Check for errors
        if (
            contract_api_msg.performative
            != ContractApiMessage.Performative.RAW_TRANSACTION
        ):
            self.context.logger.error(
                f"Could not get Multisend tx hash. "
                f"Expected: {ContractApiMessage.Performative.RAW_TRANSACTION.value}, "
                f"Actual: {contract_api_msg.performative.value}"
            )
            return None

        # Extract the multisend data and strip the 0x
        multisend_data = cast(str, contract_api_msg.raw_transaction.body["data"])[2:]
        self.context.logger.info(f"Multisend data is {multisend_data}")

        # Prepare the Safe transaction
        safe_tx_hash = yield from self._build_safe_tx_hash(
            to_address=self.params.multisend_address,
            value=ZERO_VALUE,  # the safe is not moving any native value into the multisend
            data=bytes.fromhex(multisend_data),
            operation=SafeOperation.DELEGATE_CALL.value,  # we are delegating the call to the multisend contract
        )
        return safe_tx_hash

    def _build_safe_tx_hash(
        self,
        to_address: str,
        value: int = ZERO_VALUE,
        data: bytes = EMPTY_CALL_DATA,
        operation: int = SafeOperation.CALL.value,
    ) -> Generator[None, None, Optional[str]]:
        """Prepares and returns the safe tx hash for a multisend tx."""

        self.context.logger.info(
            f"Preparing Safe transaction [{self.synchronized_data.safe_contract_address}]"
        )

        # Prepare the safe transaction
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.synchronized_data.safe_contract_address,
            contract_id=str(GnosisSafeContract.contract_id),
            contract_callable="get_raw_safe_transaction_hash",
            to_address=to_address,
            value=value,
            data=data,
            safe_tx_gas=SAFE_GAS,
            chain_id=GNOSIS_CHAIN_ID,
            operation=operation,
        )

        # Check for errors
        if response_msg.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                "Couldn't get safe tx hash. Expected response performative "
                f"{ContractApiMessage.Performative.STATE.value!r}, "  # type: ignore
                f"received {response_msg.performative.value!r}: {response_msg}."
            )
            return None

        # Extract the hash and check it has the correct length
        tx_hash: Optional[str] = response_msg.state.body.get("tx_hash", None)

        if tx_hash is None or len(tx_hash) != TX_HASH_LENGTH:
            self.context.logger.error(
                "Something went wrong while trying to get the safe transaction hash. "
                f"Invalid hash {tx_hash!r} was returned."
            )
            return None

        # Transaction to hex
        tx_hash = tx_hash[2:]  # strip the 0x

        safe_tx_hash = hash_payload_to_hex(
            safe_tx_hash=tx_hash,
            ether_value=value,
            safe_tx_gas=SAFE_GAS,
            to_address=to_address,
            data=data,
            operation=operation,
        )

        self.context.logger.info(f"Safe transaction hash is {safe_tx_hash}")

        return safe_tx_hash


class LearningRoundBehaviour(AbstractRoundBehaviour):
    """LearningRoundBehaviour"""

    initial_behaviour_cls = DecisionMakingBehaviour
    abci_app_cls = LearningAbciApp  # type: ignore
    behaviours: Set[Type[BaseBehaviour]] = [  # type: ignore
        DecisionMakingBehaviour,
        TxPreparationBehaviour,
    ]
