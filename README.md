# DCPay
![image](https://github.com/user-attachments/assets/e1aba625-9e73-4d05-8f89-f234aed5e561)

DCPay is a decentralized cryptocurrency payment gateway that enables businesses to accept crypto payments securely and independently. Built on the OLAS stack, it leverages decentralization and consensus to ensure reliability and trust, with payment records stored on IPFS for long-term accessibility and security.
[more details](https://docs.google.com/document/d/1KC4O3u80VcUfUFCL4joMqhe22K09v7dChJSlvPrj4jQ/).




## OLAS Functionalities Used
- Decentralized Consensus based decision making
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


## Flow
![image](https://github.com/user-attachments/assets/be623460-2679-43cb-b1bb-aa3418b24a7f)
![image](https://github.com/user-attachments/assets/529ae371-93ae-42a7-a1c4-675e5f9d1961)
![image](https://github.com/user-attachments/assets/05d3bd89-2641-4e2d-bf70-1bc0156fdb63)
![image](https://github.com/user-attachments/assets/1f84fd2b-e46c-4794-8454-92da93565c0e)
![image](https://github.com/user-attachments/assets/a86633b0-de31-4a64-b43f-4697d56e8b8a)


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
    git clone --depth 1 https://github.com/miladtsx/academy-learning-agent-service
   
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

3. Create a [Tenderly](https://tenderly.co/) account and from your dashboard create a fork of ETHEREUM chain (virtual testnet).

4. From Tenderly, fund your agents and Safe with some ETH and USDC (`0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48`).

6. Make a copy of the env file:

    ```
    cp sample.env .env
    ```

7. Fill in the required environment variables in .env. These variables are:
- `ALL_PARTICIPANTS`: a list of your agent addresses. This will vary depending on whether you are running a single agent (`run_agent.sh` script) or the whole 4-agent service (`run_service.sh`)
- `GNOSIS_LEDGER_RPC`: set it to your Tenderly fork Admin RPC.


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
