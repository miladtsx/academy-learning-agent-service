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

"""This package contains round behaviours of DataPullAbciApp."""

import json
from abc import ABC
from pathlib import Path
from tempfile import mkdtemp
from typing import Generator, Optional, Set, Type, cast

from packages.valory.contracts.erc20.contract import ERC20
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.protocols.ledger_api import LedgerApiMessage
from packages.valory.skills.abstract_round_abci.base import AbstractRound
from packages.valory.skills.abstract_round_abci.behaviours import (
    AbstractRoundBehaviour,
    BaseBehaviour,
)
from packages.valory.skills.abstract_round_abci.io_.store import SupportedFiletype
from packages.valory.skills.data_pull_abci.models import (
    CoingeckoETHSpecs,
    CoingeckoSpecs,
    Params,
    SharedState,
)
from packages.valory.skills.data_pull_abci.payloads import (
    DataPullPayload,
)
from packages.valory.skills.data_pull_abci.rounds import (
    IPFSPullRound,
    DataPullRound,
    SynchronizedData,
)
from packages.valory.skills.data_pull_abci.rounds import DataPullAbciApp


# Define some constants
ZERO_VALUE = 0
HTTP_OK = 200
GNOSIS_CHAIN_ID = "gnosis"
METADATA_FILENAME = "metadata.json"


class DataPullBaseBehaviour(BaseBehaviour, ABC):  # pylint: disable=too-many-ancestors
    """Base behaviour for the data_pull_abci behaviours."""

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


class APIPullBehaviour(DataPullBaseBehaviour):  # pylint: disable=too-many-ancestors
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

            # Get the token total supply
            total_supply = yield from self.get_erc20_total_supply()

            # Prepare the payload to be shared with other agents
            # After consensus, all the agents will have the same price, price_ipfs_hash, balance and total_supply variables in their synchronized data
            payload = DataPullPayload(
                sender=sender,
                price=price,
                price_ipfs_hash=price_ipfs_hash,
                native_balance=native_balance,
                erc20_balance=erc20_balance,
                erc20_total_supply=total_supply,
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

    def get_erc20_total_supply(self) -> Generator[None, None, Optional[float]]:
        """Get ERC20 total supply"""
        self.context.logger.info(
            f"Getting Olas total supply {self.params.olas_token_address}"
        )

        # Use the contract api to interact with the ERC20 contract
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_RAW_TRANSACTION,  # type: ignore
            contract_address=self.params.olas_token_address,
            contract_id=str(ERC20.contract_id),
            contract_callable="total_supply",
            chain_id=GNOSIS_CHAIN_ID,
        )

        # Check that the response is what we expect
        if response_msg.performative != ContractApiMessage.Performative.RAW_TRANSACTION:
            self.context.logger.error(
                f"Error while retrieving the balance: {response_msg}"
            )
            return None

        total_supply = response_msg.raw_transaction.body.get("total_supply", None)

        # Ensure that the balance is not None
        if total_supply is None:
            self.context.logger.error(
                f"Error while retrieving the total supply:  {response_msg}"
            )
            return None

        total_supply = total_supply / 10**18  # from wei

        self.context.logger.info(
            f"OLAS {self.params.olas_token_address} has total supply of {total_supply} token"
        )
        return total_supply

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


class IPFSPullBehaviour(DataPullBaseBehaviour):  # pylint: disable=too-many-ancestors
    """This behaviours pulls OLAS/ETH pair price from API endpoints"""

    matching_round: Type[AbstractRound] = IPFSPullRound

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
                erc20_total_supply=0
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


class DataPullRoundBehaviour(AbstractRoundBehaviour):
    """LearningRoundBehaviour"""

    initial_behaviour_cls = IPFSPullBehaviour
    abci_app_cls = DataPullAbciApp  # type: ignore
    behaviours: Set[Type[BaseBehaviour]] = [  # type: ignore
        APIPullBehaviour,
        IPFSPullBehaviour,
    ]
