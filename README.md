# Aptos Multi-Region Benchmark Setup

This repo contains deployment configurations, operational scripts, and benchmarks for a multi-region Aptos benchmark on GKE. 
* Each region is deployed separately via open source Terraform modules published by Aptos Labs
* A lightweight wrapper around the kube API and `kubectl` provides a way to form the network and submit load against the network

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

### Clone the repo

Clone the repo, including the git submodule which links to `aptos-labs/deployment` deployment configurations:

```
git clone --recurse-submodules git@github.com:aptos-labs/aptos-bench-benchmark.git bench
# OR
git clone --recurse-submodules https://github.com/aptos-labs/aptos-bench-benchmark.git
```

If you've already cloned the repo, you can update the submodules any time with: `git submodule init && git submodule update`

### Set up GCP access

Sign in with the `gcloud` CLI. Also it will be useful to set the environment variable `GCP_PROJECT_ID` for future use.

```
gcloud auth login --update-adc
gcloud config set project $GCP_PROJECT_ID
```

### Set up the infrastructure

Each region's infrasstructure is deployed separately, via Terraform. Each directory in the top-level `terraform/` directory corresponds to a Terraform project. Deploy and manage it via the following command in each directory:

```
TF_VAR_project=$GCP_PROJECT_ID terraform apply
```

After all the infrastructure is created, you can use the `cluster.py` utility to authenticate against all clusters. This will be your primary tool for interacting with each of the cluster's workloads. It is a wrapper around the kube API and familiar `kubectl` commands.

Authenticate with all GKE clusters
```
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

#### Spin up or down compute, e.g. to save cost by going idle

```
./bin/cluster.py start
./bin/cluster.py stop
```

#### Wipe the network and start from scratch

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

#### Changing the network size (and starting a new network)
* Edit `CLUSTERS` in `constants.py` to change the number of validators (and VFNs) in each region. Please note the quota
* Follow above instructions to re-run genesis and wipe the chain.

#### Changing the node deployment configuration
Each node is deployed via `helm` on each cluster. The configuration is controlled by helm values in the file: `aptos_node_helm_values.yaml`. Documentation on which values are available to configure can be found in aptos-core: https://github.com/aptos-labs/aptos-core/tree/main/terraform/helm/aptos-node

For example:
* `imageTag` -- change the image for each validator and VFN
* `chain.era` -- change the chain era and wipe storage
* `validator.config` -- override the [NodeConfig](https://github.com/aptos-labs/aptos-core/blob/main/config/src/config/mod.rs#L63-L98) as YAML, such as tuning execution, consensus, state sync, etc

### Misc

#### Grab the latest aptos-framework for genesis

```
docker run -it aptoslabs/tools:${IMAGE_TAG} bash
docker cp `docker container ls | grep tools:${IMAGE_TAG} | awk '{print $1}'`:/aptos-framework/move/head.mrb genesis/framework.mrb 
```

#### Individual GKE cluster auth

`./bin/cluster.py auth` authencates across all clusters, but you make want to use the below commands to authenticate and change your kube context manually for each cluster.

Each cluster is deployed in its own region via `terraform/` top-level directory. The `kubectx.sh` script in each will authenticate you against each cluster and set your kubectl context to match.
