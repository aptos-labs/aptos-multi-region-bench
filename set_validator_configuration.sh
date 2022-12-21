#!/bin/bash

set -e

./aptos-google-na/kubectx.sh

# for na nodes
for i in $(seq 0 2); do
  validator_host=$(kubectl get svc aptos-google-na-aptos-node-$i-validator-lb --output jsonpath='{.status.loadBalancer.ingress[0].ip}')
  fullnode_host=$(kubectl get svc aptos-google-na-aptos-node-$i-validator-lb --output jsonpath='{.status.loadBalancer.ingress[0].ip}')

  aptos genesis set-validator-configuration --owner-public-identity-file keys/aptos-google-na-$i/public-keys.yaml --local-repository-dir keys \
    --username aptos-google-na-$i \
    --validator-host $validator_host:6180 \
    --full-node-host $fullnode_host:6182 \
    --stake-amount 100000000000000
done
