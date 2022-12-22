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

## Env setup

* Login: `gcloud auth login --update-adc`
* Set gcloud project: `gcloud config set project omega-booster-372221`

## Get the latest aptos framework

docker run -it us-west1-docker.pkg.dev/aptos-global/aptos-internal/tools:${IMAGE_TAG} bash

docker cp `docker container ls | grep tools:${IMAGE_TAG} | awk '{print $1}'`:/aptos-framework/move/head.mrb keys/framework.mrb 
