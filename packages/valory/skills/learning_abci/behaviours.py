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
    CoingeckoETHSpecs,
    CoingeckoSpecs,
    Params,
    SharedState,
)
from packages.valory.skills.learning_abci.payloads import (
    DataPullPayload,
    DecisionMakingPayload,
    TxPreparationPayload,
)
from packages.valory.skills.learning_abci.rounds import (
    DataPullOlasEthPriceRound,
    DataPullRound,
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
    def olas_eth_pair_price_specs(self) -> CoingeckoETHSpecs:
        """Get the Coingecko api specs."""
        return self.context.olas_eth_pair_price_specs

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


class DataPullBehaviour(LearningBaseBehaviour):  # pylint: disable=too-many-ancestors
    """This behaviours pulls token prices from API endpoints and reads the native balance of an account"""

    matching_round: Type[AbstractRound] = DataPullRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address

            # First mehtod to call an API: simple call to get_http_response
            price = yield from self.get_token_price_simple()

            # Second method to call an API: use ApiSpecs
            # This call replaces the previous price, it is just an example
            price = yield from self.get_token_price_specs()

            # Store the price in IPFS
            price_ipfs_hash = yield from self.send_price_to_ipfs(price)

            # Get the native balance
            native_balance = yield from self.get_native_balance()

            # Get the token balance
            erc20_balance = yield from self.get_erc20_balance()

            # Prepare the payload to be shared with other agents
            # After consensus, all the agents will have the same price, price_ipfs_hash and balance variables in their synchronized data
            payload = DataPullPayload(
                sender=sender,
                price=price,
                price_ipfs_hash=price_ipfs_hash,
                native_balance=native_balance,
                erc20_balance=erc20_balance,
            )

        # Send the payload to all agents and mark the behaviour as done
        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_token_price_simple(self) -> Generator[None, None, Optional[float]]:
        """Get token price from Coingecko usinga simple HTTP request"""

        # Prepare the url and the headers
        url_template = self.params.coingecko_price_template
        url = url_template.replace("{api_key}", self.params.coingecko_api_key)
        headers = {"accept": "application/json"}

        # Make the HTTP request to Coingecko API
        response = yield from self.get_http_response(
            method="GET", url=url, headers=headers
        )

        # Handle HTTP errors
        if response.status_code != HTTP_OK:
            self.context.logger.error(
                f"Error while pulling the price from CoinGecko: {response.body}"
            )

        # Load the response
        api_data = json.loads(response.body)
        price = api_data["autonolas"]["usd"]

        self.context.logger.info(f"Got token price from Coingecko: {price}")

        return price

    def get_token_price_specs(self) -> Generator[None, None, Optional[float]]:
        """Get token price from Coingecko using ApiSpecs"""

        # Get the specs
        specs = self.coingecko_specs.get_spec()

        # Make the call
        raw_response = yield from self.get_http_response(**specs)

        # Process the response
        response = self.coingecko_specs.process_response(raw_response)

        # Get the price
        price = response.get("usd", None)
        self.context.logger.info(f"Got token price from Coingecko: {price}")
        return price

    def send_price_to_ipfs(self, price) -> Generator[None, None, Optional[str]]:
        """Store the token price in IPFS"""
        data = {"price": price}
        price_ipfs_hash = yield from self.send_to_ipfs(
            filename=self.metadata_filepath, obj=data, filetype=SupportedFiletype.JSON
        )
        self.context.logger.info(
            f"Price data stored in IPFS: https://gateway.autonolas.tech/ipfs/{price_ipfs_hash}"
        )
        return price_ipfs_hash

    def get_erc20_balance(self) -> Generator[None, None, Optional[float]]:
        """Get ERC20 balance"""
        self.context.logger.info(
            f"Getting Olas balance for Safe {self.synchronized_data.safe_contract_address}"
        )

        # Use the contract api to interact with the ERC20 contract
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_RAW_TRANSACTION,  # type: ignore
            contract_address=self.params.olas_token_address,
            contract_id=str(ERC20.contract_id),
            contract_callable="check_balance",
            account=self.synchronized_data.safe_contract_address,
            chain_id=GNOSIS_CHAIN_ID,
        )

        # Check that the response is what we expect
        if response_msg.performative != ContractApiMessage.Performative.RAW_TRANSACTION:
            self.context.logger.error(
                f"Error while retrieving the balance: {response_msg}"
            )
            return None

        balance = response_msg.raw_transaction.body.get("token", None)

        # Ensure that the balance is not None
        if balance is None:
            self.context.logger.error(
                f"Error while retrieving the balance:  {response_msg}"
            )
            return None

        balance = balance / 10**18  # from wei

        self.context.logger.info(
            f"Account {self.synchronized_data.safe_contract_address} has {balance} Olas"
        )
        return balance

    def get_native_balance(self) -> Generator[None, None, Optional[float]]:
        """Get the native balance"""
        self.context.logger.info(
            f"Getting native balance for Safe {self.synchronized_data.safe_contract_address}"
        )

        ledger_api_response = yield from self.get_ledger_api_response(
            performative=LedgerApiMessage.Performative.GET_STATE,
            ledger_callable="get_balance",
            account=self.synchronized_data.safe_contract_address,
            chain_id=GNOSIS_CHAIN_ID,
        )

        if ledger_api_response.performative != LedgerApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Error while retrieving the native balance: {ledger_api_response}"
            )
            return None

        balance = cast(int, ledger_api_response.state.body["get_balance_result"])
        balance = balance / 10**18  # from wei

        self.context.logger.error(f"Got native balance: {balance}")

        return balance


class DataPull2Behaviour(LearningBaseBehaviour):  # pylint: disable=too-many-ancestors
    """This behaviours pulls OLAS/ETH pair price from API endpoints"""

    matching_round: Type[AbstractRound] = DataPullOlasEthPriceRound

    def async_act(self) -> Generator:

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address

            # Get OLAS/ETH Price from API
            price_from_api = yield from self.get_token_price_specs()
            self.context.logger.info(f"price_from_api: {price_from_api}")
         
            # Store the OLAS/ETH price in IPFS
            eth_price_ipfs_hash = yield from self.send_price_to_ipfs(price_from_api)
            self.context.logger.info(f"price_ipfs_hash: {eth_price_ipfs_hash}")

            # Read the OLAS/ETH price from IPFS
            price_read_from_ipfs = yield from self.get_price_from_ipfs(eth_price_ipfs_hash)
            self.context.logger.info(f"price_read_from_ipfs: {price_read_from_ipfs}")

            payload = DataPullPayload(
                sender=sender,
                price=price_read_from_ipfs.get('olas_eth_price'),
                price_ipfs_hash=eth_price_ipfs_hash,
                native_balance=0,
                erc20_balance=0,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_token_price_specs(self) -> Generator[None, None, Optional[float]]:
        """Get token price from Coingecko using ApiSpecs"""

        # Get the specs
        specs = self.olas_eth_pair_price_specs.get_spec()

        # Make the call
        raw_response = yield from self.get_http_response(**specs)

        # Process the response
        response = self.olas_eth_pair_price_specs.process_response(raw_response)

        # Get the price
        price = response.get("eth", None)
        self.context.logger.info(f"Got token eth price from Coingecko: {price}")
        return price

    def send_price_to_ipfs(self, price) -> Generator[None, None, Optional[str]]:
        """Store the olas/eth price in IPFS"""
        data = {"olas_eth_price": price}
        price_ipfs_hash = yield from self.send_to_ipfs(
            filename=self.metadata_filepath, obj=data, filetype=SupportedFiletype.JSON
        )
        self.context.logger.info(
            f"OLAS/ETH Price data stored in IPFS: https://gateway.autonolas.tech/ipfs/{price_ipfs_hash}"
        )
        return price_ipfs_hash

    def get_price_from_ipfs(self, ipfs_hash : str) -> Generator[None, None, Optional[dict]]:
        """Load the price data from IPFS"""
        price = yield from self.get_from_ipfs(
            ipfs_hash=ipfs_hash, filetype=SupportedFiletype.JSON
        )
        self.context.logger.error(f"Got price from IPFS: {price}")
        return price


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

        # Get the balance we calculated in the previous round
        native_balance = self.synchronized_data.native_balance

        # We stored the price using two approaches: synchronized_data and IPFS
        # Similarly, we retrieve using the corresponding ways
        token_price = self.synchronized_data.price
        token_price = yield from self.get_price_from_ipfs()

        # If we fail to get the block number, we send the ERROR event
        if not block_number:
            self.context.logger.info("Block number is None. Sending the ERROR event...")
            return Event.ERROR.value

        # If we fail to get the token price, we send the ERROR event
        if not token_price:
            self.context.logger.info("Token price is None. Sending the ERROR event...")
            return Event.ERROR.value

        # If we fail to get the token balance, we send the ERROR event
        if not native_balance:
            self.context.logger.info(
                "Native balance is None. Sending the ERROR event..."
            )
            return Event.ERROR.value

        # Make a decision based on the balance's last number
        last_number = int(str(native_balance)[-1])

        # If the number is even, we transact
        if last_number % 2 == 0:
            self.context.logger.info("Number is even. Transacting.")
            return Event.TRANSACT.value

        # Otherwise we send the DONE event
        self.context.logger.info("Number is odd. Not transacting.")
        return Event.DONE.value

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

    def get_price_from_ipfs(self) -> Generator[None, None, Optional[dict]]:
        """Load the price data from IPFS"""
        ipfs_hash = self.synchronized_data.price_ipfs_hash
        price = yield from self.get_from_ipfs(
            ipfs_hash=ipfs_hash, filetype=SupportedFiletype.JSON
        )
        self.context.logger.error(f"Got price from IPFS: {price}")
        return price


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
            tx_hash = yield from self.get_tx_hash()

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
            amount=1,
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

    initial_behaviour_cls = DataPullBehaviour
    abci_app_cls = LearningAbciApp  # type: ignore
    behaviours: Set[Type[BaseBehaviour]] = [  # type: ignore
        DataPullBehaviour,
        DataPull2Behaviour,
        DecisionMakingBehaviour,
        TxPreparationBehaviour,
    ]
