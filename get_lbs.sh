#!/bin/bash

# Get all the external LBs for multi-region testnet
# So we can run txn emitter and other tests
# as well as for intial network genesis

if [ -f lbs.txt ]; then
  rm lbs.txt
fi
touch lbs.txt

./aptos-google-asia/kubectx.sh
echo "=== asia ===" >> lbs.txt
kubectl get svc >> lbs.txt
echo "" >> lbs.txt

./aptos-google-europe/kubectx.sh
echo "=== europe ===" >> lbs.txt
kubectl get svc >> lbs.txt
echo "" >> lbs.txt

./aptos-google-na/kubectx.sh
echo "=== na ===" >> lbs.txt
kubectl get svc >> lbs.txt
echo "" >> lbs.txt
