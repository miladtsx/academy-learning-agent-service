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

"""This module contains the transaction payloads of the LearningAbciApp."""

from dataclasses import dataclass
from typing import Optional

from packages.valory.skills.abstract_round_abci.base import BaseTxPayload


@dataclass(frozen=True)
class InvoicesPayload(BaseTxPayload):
    """represents a tx payload for the Invoices in JSON format"""

    invoices: Optional[str]


@dataclass(frozen=True)
class DecisionMakingPayload(BaseTxPayload):
    """Represent a transaction payload for the settled invoices in the DecisionMakingRound."""

    settled_invoices_uuid: str


@dataclass(frozen=True)
class KeeperPayload(BaseTxPayload):
    """Represent a transaction payload for the selected keeper."""

    selected_keeper: str


@dataclass(frozen=True)
class ConfirmationResultPayload(BaseTxPayload):
    """Represent a transaction payload for the ConfirmationResultPayload."""

    is_webhook_ok: bool
