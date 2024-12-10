# DCPay
DCPay (Decentralized Cryptocurrency Payment Gateway) is a tool that helps businesses accept cryptocurrency payments in a safe and independent way. It uses decentralized software to manage invoices, track payments, and confirm transactions securely. Payment records are stored on IPFS for easy access and long-term safety. With simple integration into business websites, DCPay makes handling cryptocurrency payments reliable, scalable, and easy to use, without needing middlemen.

# OLAS Functionalities Used
- API
- IPFS


## Rounds
- CollectInvoicesRound
    Read Invoices [API]
        For Demo, read invoices from a json file.
        If no Invoice exists, wait for 10s and try again.
- DecisionMakingRound
    Monitor Invoice Settlement On-Chain [API]
    Keep Settled Invoices Records on [IPFS]
- SelectKeeperRound
    Select a keepr to invoke the webhook
- ConfirmationRound
    Confirm Settlement via Webhook [API]
- Reset and Start Again


## TODO

- Read Invoices from Remote API
- Select Keeper Randomly [DRAND]
- Setup local DB to facilitate Admin Dashboard
- Call Remote Webhook

## System requirements

- Python `>=3.10`
- [Tendermint](https://docs.tendermint.com/v0.34/introduction/install.html) `==0.34.19`
- [IPFS node](https://docs.ipfs.io/install/command-line/#official-distributions) `==0.6.0`
- [Pip](https://pip.pypa.io/en/stable/installation/)
- [Poetry](https://python-poetry.org/)
- [Docker Engine](https://docs.docker.com/engine/install/)
- [Docker Compose](https://docs.docker.com/compose/install/)
- [Set Docker permissions so you can run containers as non-root user](https://docs.docker.com/engine/install/linux-postinstall/)


## Run you own agent

### Get the code

1. Clone this repo:

    ```
    git clone git@github.com:valory-xyz/academy-learning-service.git
    ```

2. Create the virtual environment:

    ```
    cd academy-learning-service
    poetry shell
    poetry install
    ```

3. Sync packages:

    ```
    autonomy packages sync --update-packages
    ```

### Prepare the data

1. Prepare a keys.json file containing wallet address and the private key for each of the four agents.

    ```
    autonomy generate-key ethereum -n 4
    ```

2. Prepare a `ethereum_private_key.txt` file containing one of the private keys from `keys.json`. Ensure that there is no newline at the end.

3. Deploy two [Safes on Gnosis](https://app.safe.global/welcome) (it's free) and set your agent addresses as signers. Set the signature threshold to 1 out of 4 for one of them and and to 3 out of 4 for the other. This way we can use the single-signer one for testing without running all the agents, and leave the other safe for running the whole service.

4. Create a [Tenderly](https://tenderly.co/) account and from your dashboard create a fork of Gnosis chain (virtual testnet).

5. From Tenderly, fund your agents and Safe with some xDAI and OLAS (`0xcE11e14225575945b8E6Dc0D4F2dD4C570f79d9f`).

6. Make a copy of the env file:

    ```
    cp sample.env .env
    ```

7. Fill in the required environment variables in .env. These variables are:
- `ALL_PARTICIPANTS`: a list of your agent addresses. This will vary depending on whether you are running a single agent (`run_agent.sh` script) or the whole 4-agent service (`run_service.sh`)
- `GNOSIS_LEDGER_RPC`: set it to your Tenderly fork Admin RPC.
- `COINGECKO_API_KEY`: you will need to get a free [Coingecko](https://www.coingecko.com/) API key.
- `TRANSFER_TARGET_ADDRESS`: any random address to send funds to, can be any of the agents for example.
- `SAFE_CONTRACT_ADDRESS_SINGLE`: the 1 out of 4 agents Safe address.
- `SAFE_CONTRACT_ADDRESS`: the 3 out of 4 Safe address.


### Run a single agent locally

1. Verify that `ALL_PARTICIPANTS` in `.env` contains only 1 address.

2. Run the agent:

    ```
    bash run_agent.sh
    ```

### Run the service (4 agents) via Docker Compose deployment

1. Verify that `ALL_PARTICIPANTS` in `.env` contains 4 address.

2. Check that Docker is running:

    ```
    docker
    ```

3. Run the service:

    ```
    bash run_service.sh
    ```

4. Look at the service logs for one of the agents (on another terminal):

    ```
    docker logs -f learningservice_abci_0
    ```

# TODO
1. Automate the requirement installation
2. Read invoices from the API instead of `invoices.json`
3. Should the Agent keep IPFS hashes in Smart Contract?