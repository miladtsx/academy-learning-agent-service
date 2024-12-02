#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2021-2024 Valory AG
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


"""Updates fetched agent with correct config"""
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv


def main() -> None:
    """Main"""
    load_dotenv()

    with open(Path("learning_agent", "aea-config.yaml"), "r", encoding="utf-8") as file:
        config = list(yaml.safe_load_all(file))

        # Ledger RPCs
        if os.getenv("GNOSIS_LEDGER_RPC"):
            config[2]["config"]["ledger_apis"]["gnosis"][
                "address"
            ] = f"${{str:{os.getenv('GNOSIS_LEDGER_RPC')}}}"

        # Params
        if os.getenv("COINGECKO_API_KEY"):
            # Coingecko API key (params)
            config[-1]["models"]["params"]["args"][
                "coingecko_api_key"
            ] = f"${{str:{os.getenv('COINGECKO_API_KEY')}}}"  # type: ignore

            # Coingecko API key (ApiSpecs)
            config[-1]["models"]["coingecko_specs"]["args"]["parameters"][
                "x_cg_demo_api_key"
            ] = f"${{str:{os.getenv('COINGECKO_API_KEY')}}}"  # type: ignore

            # Coingecko2 API key (ApiSpecs)
            config[-1]["models"]["olas_eth_pair_price_specs"]["args"]["parameters"][
                "x_cg_demo_api_key"
            ] = f"${{str:{os.getenv('COINGECKO_API_KEY')}}}"  # type: ignore

            # ALL_PARTICIPANTS
            config[-1]["models"]["params"]["args"]["setup"][
                "all_participants"
            ] = f"${{list:{os.getenv('ALL_PARTICIPANTS')}}}"  # type: ignore

            # SAFE_CONTRACT_ADDRESS_SINGLE
            config[-1]["models"]["params"]["args"]["setup"][
                "safe_contract_address"
            ] = f"${{str:{os.getenv('SAFE_CONTRACT_ADDRESS_SINGLE')}}}"  # type: ignore

            # TRANSFER_TARGET_ADDRESS
            config[-1]["models"]["params"]["args"][
                "transfer_target_address"
            ] = f"${{str:{os.getenv('TRANSFER_TARGET_ADDRESS')}}}"  # type: ignore

    with open(Path("learning_agent", "aea-config.yaml"), "w", encoding="utf-8") as file:
        yaml.dump_all(config, file, sort_keys=False)


if __name__ == "__main__":
    main()
