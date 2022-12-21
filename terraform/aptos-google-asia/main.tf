terraform {
  required_version = "~> 1.2.0"
  backend "gcs" {
    bucket = "aptos-googl-terraform-dev"
    prefix = "state/testnet"
  }
}

locals {
  region  = "asia-east1"
  zone    = "a"
  project = "omega-booster-372221"
}

module "aptos-node" {
  source = "github.com/aptos-labs/aptos-core.git//terraform/aptos-node/gcp?ref=experimental"

  region  = local.region  # Specify the region
  zone    = local.zone    # Specify the zone suffix
  project = local.project # Specify your GCP project name

  validator_name = "aptos-google-asia-nodes"

  # for naming purposes to avoid name collisions
  chain_name          = "aptos-google"
  num_validators      = 2
  num_fullnode_groups = 2

  era       = 1 # bump era number to wipe the chain. KEEP THIS NUMERIC
  image_tag = "performance_08e9119a20d2c873848dda724d811c239ca393e3"

  enable_monitoring    = false
  enable_logger        = false
  utility_instance_num = 4

  # disable nodepool autoscaling 
  gke_enable_autoscaling = false
  # enable node autoprovisioning (NAP)
  # NOTE: 1000 seems to be the upper bound for NAP
  # NOTE: Using the recommended n2-standard-32 (32 vCPUs, 128 GB memory) as the target size
  gke_enable_node_autoprovisioning     = true
  gke_node_autoprovisioning_max_cpu    = 32 * 1000 # space for at least 1000 nodes
  gke_node_autoprovisioning_max_memory = 128 * 1000

  ### NOTE: storage on each node can be changed via: https://cloud.google.com/kubernetes-engine/docs/how-to/node-auto-provisioning#custom_boot_disk

  # configure these
  helm_values = {
    validator = {
      image = {
        repo = "us-west1-docker.pkg.dev/aptos-global/aptos-internal/validator"
      }
    }
    fullnode = {
      image = {
        repo = "us-west1-docker.pkg.dev/aptos-global/aptos-internal/validator"
      }
    }
}

resource "local_file" "kubectx" {
  filename = "kubectx.sh"
  content  = <<EOF
  #!/bin/bash

  gcloud container clusters get-credentials aptos-${terraform.workspace} --zone ${local.region}-${local.zone} --project ${local.project}
  EOF
}
