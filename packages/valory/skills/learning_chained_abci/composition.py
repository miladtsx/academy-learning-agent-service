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

"""This package contains round behaviours of LearningChainedSkillAbciApp."""

import packages.valory.skills.learning_abci.rounds as LearningAbci
import packages.valory.skills.registration_abci.rounds as RegistrationAbci
import packages.valory.skills.reset_pause_abci.rounds as ResetAndPauseAbci
from packages.valory.skills.abstract_round_abci.abci_app_chain import (
    AbciAppTransitionMapping,
    chain,
)

abci_app_transition_mapping: AbciAppTransitionMapping = {
    RegistrationAbci.FinishedRegistrationRound: LearningAbci.CollectInvoicesRound,
    LearningAbci.FinishedRound: ResetAndPauseAbci.ResetAndPauseRound,
    ResetAndPauseAbci.FinishedResetAndPauseRound: LearningAbci.CollectInvoicesRound,
    ResetAndPauseAbci.FinishedResetAndPauseErrorRound: RegistrationAbci.RegistrationRound,
}

LearningChainedSkillAbciApp = chain(
    (
        RegistrationAbci.AgentRegistrationAbciApp,
        LearningAbci.LearningAbciApp,
        ResetAndPauseAbci.ResetPauseAbciApp,
    ),
    abci_app_transition_mapping,
)
