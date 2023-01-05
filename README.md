# Aptos Benchmark Setup for Google

This repo contains deployment configurations, operational scripts, and benchmarks for two Aptos testnets:
* terraform/aptos-google - Single region testnet
* terraform/aptos-google-{asia,na,europe*} - All part of multi region testnet. Each region is deployed separately

## Multi-region setup

Google Cloud Inter-Region Latency and Throughput: [link](https://datastudio.google.com/u/0/reporting/fc733b10-9744-4a72-a502-92290f608571/page/70YCB)
* asia-east1 -- Taiwan
* europe-west4 -- Netherlands
* us-west1 -- Oregon

### Raw data

The below latency and throughput stats were pulled from [Google Cloud Inter-Region Latency and Throughput](https://datastudio.google.com/u/0/reporting/fc733b10-9744-4a72-a502-92290f608571/page/70YCB). Raw filtered CSV can be found in the `./data` directory.

Latency (snapshot Dec 5, 2022 - Jan 3, 2023):

|sending_region|receiving_region|milliseconds|
|--------------|----------------|------------|
|asia-east1    |europe-west4    |251.794     |
|asia-east1    |us-west1        |118.553     |
|europe-west4  |asia-east1      |251.777     |
|europe-west4  |us-west1        |133.412     |
|us-west1      |asia-east1      |118.541     |
|us-west1      |europe-west4    |133.435     |


Throughput (snapshot Dec 5, 2022 - Jan 3, 2023):

|sending_region|receiving_region|Gbits/sec|
|--------------|----------------|---------|
|asia-east1    |europe-west4    |9.344    |
|asia-east1    |us-west1        |9.811    |
|europe-west4  |asia-east1      |9.326    |
|europe-west4  |us-west1        |9.815    |
|us-west1      |asia-east1      |9.802    |
|us-west1      |europe-west4    |9.778    |

## Env setup

```
# Set up GCP access
gcloud auth login --update-adc
gcloud config set project omega-booster-372221

# This step authenticates with all GKE clusters
./bin/cluster.py auth
```

## Scripts

`bin/loadtest.py` - little loadtest utility.
`bin/cluster.py` - cluster management utility. Creates genesis, and manages nodes lifecycle

### `loadtest.py`

Submit load test against the network. The root keypair is hardcoded in genesis. The below commands show some cutomization options for the loadtest utility.

```
# apply a loadtest with a constant target TPS
./bin/loadtest.py 0xE25708D90C72A53B400B27FC7602C4D546C7B7469FA6E12544F0EBFB2F16AE19 4 --apply --target-tps 5000

# apply a loadtest with mempool backlog 50,000 for 1 hour
./bin/loadtest.py 0xE25708D90C72A53B400B27FC7602C4D546C7B7469FA6E12544F0EBFB2F16AE19 4 --apply --duration 3600 --mempool-backlog 50000

# more customizations can be seen here
./bin/loadtest.py --help
```

### `cluster.py`

Spin up or down compute, e.g. to save cost by going idle

```
./bin/cluster.py start
./bin/cluster.py stop
```

Wipe the network and start from scratch

```
# 1. Changing the chain's era wipes all storage and tells the system to start from scratch
<edit aptos_node_helm_values.yaml with a new chain.era>

# 2. Re-run genesis and set all validator configs. You have a few options here

# a. re-generate keys and re-fetch the external IPs for validator config
yes | ./bin/cluster.py genesis create --generate-keys --set-validator-config
# b. to set validator config without generating new keys
yes | ./bin/cluster.py genesis create --set-validator-config

# 3. Upload genesis configs to each node for startup
./bin/cluster.py genesis upload --apply

# 4. Upgrade all nodes (this may take a few minutes)
# this can be done in parallel with above upload step in another terminal
time ./bin/cluster.py helm-upgrade
```

### Misc

Grab the latest aptos-framework for genesis

```
docker run -it aptoslabs/tools:${IMAGE_TAG} bash
docker cp `docker container ls | grep tools:${IMAGE_TAG} | awk '{print $1}'`:/aptos-framework/move/head.mrb genesis/framework.mrb 
```

Individual GKE cluster auth:
* Multi-region k8s testnet
  * EU: `gcloud container clusters get-credentials aptos-aptos-google-europe2 --zone europe-west2-a --project omega-booster-372221`
    * Due to quota limitations, we have a standby cluster in europe-west3a with less quota: `gcloud container clusters get-credentials aptos-aptos-google-europe --zone europe-west3-a --project omega-booster-372221`
  * ASIA: `gcloud container clusters get-credentials aptos-aptos-google-asia --zone asia-east1-a --project omega-booster-372221`
  * NA: `gcloud container clusters get-credentials aptos-aptos-google-na --zone us-west1-a --project omega-booster-372221`
* Single-region k8s testnet: `gcloud container clusters get-credentials aptos-aptos-google --zone us-central1-c --project omega-booster-372221`
