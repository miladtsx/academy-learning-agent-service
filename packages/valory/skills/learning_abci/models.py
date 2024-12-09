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

"""This module contains the shared state for the abci skill of LearningAbciApp."""

from typing import Any, Dict, Optional

from packages.valory.skills.abstract_round_abci.models import ApiSpecs, BaseParams
from packages.valory.skills.abstract_round_abci.models import (
    BenchmarkTool as BaseBenchmarkTool,
)
from packages.valory.skills.abstract_round_abci.models import Requests as BaseRequests
from packages.valory.skills.abstract_round_abci.models import (
    SharedState as BaseSharedState,
)
from packages.valory.skills.learning_abci.rounds import LearningAbciApp


class SharedState(BaseSharedState):
    """Keep the current shared state of the skill."""

    abci_app_cls = LearningAbciApp


Requests = BaseRequests
BenchmarkTool = BaseBenchmarkTool


class Params(BaseParams):
    """Parameters."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the parameters object."""
        self.coingecko_price_template = self._ensure(
            "coingecko_price_template", kwargs, str
        )
        self.coingecko_api_key = kwargs.get("coingecko_api_key", None)
        self.transfer_target_address = self._ensure(
            "transfer_target_address", kwargs, str
        )
        self.olas_token_address = self._ensure("olas_token_address", kwargs, str)

        # multisend address is used in other skills, so we cannot pop it using _ensure
        self.multisend_address = kwargs.get("multisend_address", "")

        super().__init__(*args, **kwargs)


class CoingeckoSpecs(ApiSpecs):
    """A model that wraps ApiSpecs for Coingecko API."""


class Invoice:
    """Represents an invoice."""

    def __init__(
        self,
        uuid: str,
        sender_wallet_address: str,
        receiver_wallet_address: str,
        amount_in_wei: int,
        chain_id: int,
        erc20_token_address: str,
        is_settled: Optional[bool] = False,
    ) -> None:
        """Initialize the invoice with the provided parameters."""
        self.uuid = uuid
        self.sender_wallet_address = sender_wallet_address
        self.receiver_wallet_address = receiver_wallet_address
        self.amount_in_wei = amount_in_wei
        self.chain_id = chain_id
        self.erc20_token_address = erc20_token_address
        self.is_settled = is_settled

    def to_dict(self) -> Dict[str, Optional[object]]:
        """Convert the Invoice instance to a dictionary."""
        return {
            "uuid": self.uuid,
            "sender_wallet_address": self.sender_wallet_address,
            "receiver_wallet_address": self.receiver_wallet_address,
            "amount_in_wei": self.amount_in_wei,
            "chain_id": self.chain_id,
            "erc20_token_address": self.erc20_token_address,
            "is_settled": self.is_settled,
        }


class ETHLogsSpecs(ApiSpecs):
    """A model that wraps ApiSpecs for the eth_logs API."""
