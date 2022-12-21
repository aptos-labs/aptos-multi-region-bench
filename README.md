# Load Test Setup for Google!

## Testnets

terraform/aptos-google - single region testnet

terraform/aptos-google-{asia,na,europe} - all part of multi region testnet

## Scripts

bin/loadtest.py - little loadtest utility.

This creates a loadtest pod in the current cluster

By default it just prints the pod output, use --apply to actually create the pod


## Multi-region setup

Google Cloud Inter-Region Latency and Throughput: [link](https://datastudio.google.com/u/0/reporting/fc733b10-9744-4a72-a502-92290f608571/page/70YCB)
* us-west1
* europe-west3
* asia-east1
