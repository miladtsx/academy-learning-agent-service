#!/usr/bin/env bash

REPO_PATH=$PWD

# Remove previous service build
if test -d learning_service; then
  echo "Removing previous service build (requires sudo permission)"
  sudo rm -r learning_service
fi

# Remove empty directories to avoid wrong hashes
find . -empty -type d -delete

# Ensure that third party packages are correctly synced
make clean
AUTONOMY_VERSION=v$(autonomy --version | grep -oP '(?<=version\s)\S+')
AEA_VERSION=v$(aea --version | grep -oP '(?<=version\s)\S+')
autonomy packages sync --source valory-xyz/open-aea:$AEA_VERSION --source valory-xyz/open-autonomy:$AUTONOMY_VERSION --update-packages

# Ensure hashes are updated
autonomy packages lock

# Push packages to IPFS
autonomy push-all

# Fetch the service
autonomy fetch --local --service valory/learning_service && cd learning_service

# Build the image
autonomy init --reset --author author --remote --ipfs --ipfs-node "/dns/registry.autonolas.tech/tcp/443/https"
autonomy build-image

# Copy .env file
cp $REPO_PATH/.env .

# Copy the keys and build the deployment
cp $REPO_PATH/keys.json .

# Ensure the invoices directory is copied correctly
if [ -d "$REPO_PATH/invoices" ]; then
  cp -r $REPO_PATH/invoices .
else
  echo "Error: The invoices directory does not exist at $REPO_PATH/invoices."
  exit 1
fi

autonomy deploy build -ltm

# Run the deployment
autonomy deploy run --build-dir abci_build/
