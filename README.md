# Aptos Multi-Region Benchmark Setup

This repo contains deployment configurations, operational scripts, and benchmarks for a multi-region Aptos benchmark on GKE. 
* Each region is deployed separately via open source Terraform modules published by Aptos Labs. These are the same deployment modules used to run validators and fullnodes in production on mainnet. Validators and fullnodes connect to each other over the public internet.
* A lightweight wrapper around the kube API and `kubectl` provides a way to form the network and submit load against the network

## Multi-region setup

Google Cloud Inter-Region Latency and Throughput: [link](https://datastudio.google.com/u/0/reporting/fc733b10-9744-4a72-a502-92290f608571/page/70YCB)
* asia-east1 -- Taiwan
* europe-west4 -- Netherlands
* us-west1 -- Oregon

For each validator, the following is spun up:
* 2x `t2d-standard-48` -- one for each the validator itself and the validator-fullnode (VFN). The machine family and size can be tuned via kubernetes resources requests and nodeAffinities, using GKE's Node-autoprovisioning. More details in the below sections.
* 2x Google Cloud Load Balancers -- one for each the validator and VFN
* 2x 1 TiB SSD -- one for each validator and VFN

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

## Benchmark setup

### Clone the repo

This repo uses a git submodule to https://github.com/aptos-labs/deployment, so be sure to clone that as well

```
git clone https://github.com/aptos-labs/aptos-multi-region-bench.git --recurse-submodules
cd aptos-multi-region-bench
```

At any point you can update the submodule with:

```
git submodule update --remote
```

### Set up GCP access

Create a GCP project and sign in with the `gcloud` CLI. Also it will be useful to set the environment variable `GCP_PROJECT_ID` for future use.

For reference:
* Install `gcloud` CLI: https://cloud.google.com/sdk/docs/install
* Create a GCP project: https://cloud.google.com/resource-manager/docs/creating-managing-projects

```
export GCP_PROJECT_ID=<YOUR_GCP_PROJECT_ID>

gcloud auth login --update-adc
gcloud config set project $GCP_PROJECT_ID
```

### Set up the infrastructure

NOTE: This section may take a while to run through all the steps. A lot of the time will be spent running commands and waiting on cloud infrastructure to come alive.

Each region's infrastructure is deployed separately, via Terraform. Each directory in the top-level `terraform/` directory corresponds to a Terraform project. 

If you are unfamiliar with Terraform, it's highly recommended that you familiarize yourself with Terraform concepts before you get started. This will help you ensure the health of your infrastructure, as well as prevent unnecessary costs. Particularly, these reference documentation links:
* What is Terraform: https://developer.hashicorp.com/terraform/intro
* Terraform backends: https://developer.hashicorp.com/terraform/language/settings/backends/configuration
* Terraform workspaces: https://developer.hashicorp.com/terraform/language/state/workspaces

Create a storage bucket for storing the Terraform state on Google Cloud Storage. Use the console or this `gcs` command to create the bucket. The name of the bucket must be unique. See the Google Cloud Storage documentation here: https://cloud.google.com/storage/docs/creating-buckets#prereq-cli.

```
gsutil mb gs://BUCKET_NAME
# for example
gsutil mb gs://<project-name>-aptos-terraform-bench
```

Then, edit `terraform/example.backend.tfvars` to reference the gcs bucket created in the previous step. Rename `terraform/example.backend.tfvars` to `terraform/backend.tfvars`.

Deploy each region's infrastructure using the following commands. For each of the Terraform project directories in `terraform/`, run the following series of commands:

```
# Initialize terraform and its backend, using the backend configuration created in the previous step
# This will copy the public reference terraform modules written by Aptos Labs into the .terraform/modules directory
terraform init -backend-config=../backend.tfvars

# This environment variable is used to apply the infrastructure to the GCP project you set up in the previous step
export TF_VAR_project=$GCP_PROJECT_ID

# Initialize your terraform workspaces, one unique workspace name for each directory.
terraform workspace new <WORKSPACE_NAME>
# for example
terraform workspace new bench-asia-east1

# check the infrastructure that will be applied
terraform plan

# apply it
terraform apply
```


After all the infrastructure is created, you can use the `cluster.py` utility to authenticate against all clusters. This will be your primary tool for interacting with each of the cluster's workloads. It is a wrapper around the kube API and familiar `kubectl` commands.

Authenticate with all GKE clusters
```
# this script must be run from the repository root
./bin/cluster.py auth
```

### Initialize the Network

At this point, most of the required infrastructure has been set up. You must now begin the genesis process and start all the Aptos nodes in each kubernetes cluster. As a quick sanity check, visit this URL to view all your active kubernetes clusters within the project https://console.cloud.google.com/kubernetes/list/overview?referrer=search&project=<YOUR_PROJECT_ID>, and confirm that all are in a healthy "green" state. If not, use GKE's tooltips and logs to help debug.

By default, the Terraform modules will also install some baseline Aptos workloads on each of the kubernetes clusters as well (e.g. 1 validator). To check these running workloads, run the following from the project root:

```
./bin/cluster.py kube get pods 
```

These workloads will soon be replaced with the following steps, which initializes the benchmark network.

#### Install `aptos` CLI

Some of the scripts below require the `aptos` CLI to be installed. Install instructions: https://aptos.dev/cli-tools/aptos-cli-tool/

Also ensure that the CLI is available in the `PATH`.

#### Run genesis

In this setup, you will mostly be interacting with `aptos_node_helm_values.yaml` to configure the benchmark network as a whole.

Firstly, start all the validators and fullnodes.

```
# 1. This performs a helm upgrade to all clusters to spin up the validators and fullnodes (this may take a few minutes)
time ./bin/cluster.py upgrade --new
```

You will see most pods are in a `ContainerCreating` state. This is because these pods (fullnodes and validators) are waiting for their keys and genesis configurations, which will be done in a later step.

You might also see some pods in `Pending` state. This is likely due to GKE's underlying autoscaler kicking in. It may take a few minutes for the necessary compute to be available to the cluster. Part of why we install the validators and fullnodes workloads as the first step is to warm up the infrastructure.

In order to progress to the next steps, check that all LoadBalancers have been provisioned for each validator and fullnode. From the output, check if there are any services that have `<pending>` for their `EXTERNAL-IP`. Wait until all LoadBalancers are brought up before proceeding to the next step.

```
# 1.1. Filter all kubernetes services by LoadBalancer type, checking for pending
./bin/cluster.py kube get svc | grep LoadBalancer

# to continue, this should be zero
./bin/cluster.py kube get svc | grep -c pending
```

To run genesis for the first time:
```
# 2. You have a few options here

# a. (RECOMMENDED) re-generate keys and re-fetch the external IPs for validator config
yes | ./bin/cluster.py genesis create --generate-keys --set-validator-config
# b. to set validator config without generating new keys
yes | ./bin/cluster.py genesis create --set-validator-config
```

After the keys and validator configs are generated, they'll need to be uploaded to each node (via kubernetes) for startup:
```
# 3. Upload genesis configs to each node for startup
./bin/cluster.py genesis upload --apply
```

From here onwards, you can use Helm to manage the lifecycle of your nodes. If there is any config change you want to make, you can run `upgrade` again (NOTE: this time, without `--new`). If nothing has changed, running it again should be idempotent:
```
# 4. Upgrade all nodes (this may take a few minutes)
time ./bin/cluster.py upgrade
```

## Scripts Reference

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

#### Delete all workloads in each cluster, e.g. a clean wipe

```
./bin/cluster.py delete
```

To bring back the network, you can try: 

```
./bin/cluster.py upgrade --new
```


#### Wipe the network and start from scratch

To wipe the chain, change the chain's "era" in the helm values in `aptos_node_helm_values.yaml`. This tells the kubernetes workloads to switch their underlying volumes, thus starting the chian from scratch. Then, follow the steps above to [Run genesis](#run-genesis)

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

#### Changing machine types

This kubernetes setup relies on GKE's [Node auto-provisioning (NAP)](https://cloud.google.com/kubernetes-engine/docs/how-to/node-auto-provisioning). This allows us to specify a machine family in each workload's `nodeAffinity`. The size of the machine is automatically assigned, based on the size of the workload. In general the workload resource request must be a bit less than the max capacity. For example, if you want to use a 48 vCPU machine for validators, you may need to set the resource request at 42 vCPU only to give slack to the Node auto-provisioner, otherwise it may provision the next largest machine size.

The default machine configuration via node auto-provisioning is already set in `aptos_node_helm_values.yaml`. Particularly, note the following keys:
* `validator.affinity.nodeAffinity` -- guarantee machine type via NAP
* `validator.resources` -- resource request and limit
* `validator.affinity.podAntiAffinity` -- prevent validators from sharing the same machine as other validators and fullnodes
* `fullnode.affinity.nodeAffinity` -- same as above, but for fullnodes
* `fullnode.affinity.podAntiAffinity` -- same as above, but for fullnodes
* `fullnode.resources` -- same as above, but for fullnodes
