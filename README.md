# Load Test Setup for Google!

## Testnets

terraform/aptos-google - single region testnet

terraform/aptos-google-{asia,na,europe} - all part of multi region testnet

## Scripts

bin/loadtest.py - little loadtest utility.
bin/cluster.py - cluster management utility. Creates genesis, and manages nodes lifecycle

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

## Helpful commands

Grab the latest aptos-framework for genesis

```
docker run -it aptoslabs/tools:${IMAGE_TAG} bash
docker cp `docker container ls | grep tools:${IMAGE_TAG} | awk '{print $1}'`:/aptos-framework/move/head.mrb genesis/framework.mrb 
```

Spin up or down compute, e.g. to save cost by going idle

```
./bin/cluster.py start
./bin/cluster.py stop
```

Wipe the network and start from scratch

```
<edit aptos_node_helm_values.yaml with a new chain.era>

# re-run genesis and upload to all nodes
yes | ./bin/cluster.py genesis create

# to re-generate keys and re-fetch the external IPs
yes | ./bin/cluster.py genesis create --generate-keys --set-validator-config

# upload genesis configs to each node for startup
./bin/cluster.py genesis upload --apply

# upgrade all nodes (this may take a few minutes)
# this can be done in parallel with above upload step in another terminal
time ./bin/cluster.py helm-upgrade
```

Submit load test against the network:

```
# this root keypair is hardcoded in genesis
./bin/loadtest.py 0xE25708D90C72A53B400B27FC7602C4D546C7B7469FA6E12544F0EBFB2F16AE19 4 --apply --target-tps 5000

# more customizations can be seen here
./bin/loadtest.py --help
```

Individual GKE cluster auth:
* Multi-region k8s testnet
  * EU: `gcloud container clusters get-credentials aptos-aptos-google-europe --zone europe-west3-a --project omega-booster-372221`
  * ASIA: `gcloud container clusters get-credentials aptos-aptos-google-asia --zone asia-east1-a --project omega-booster-372221`
  * NA: `gcloud container clusters get-credentials aptos-aptos-google-na --zone us-west1-a --project omega-booster-372221`
* Single-region k8s testnet: `gcloud container clusters get-credentials aptos-aptos-google --zone us-central1-c --project omega-booster-372221`
