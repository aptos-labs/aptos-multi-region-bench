terraform {
  required_version = "~> 1.2.0"
  backend "gcs" {
    bucket = "aptos-googl-terraform-dev"
    prefix = "state/testnet"
  }
}

locals {
  region  = "europe-west3"
  zone    = "a"
  project = "omega-booster-372221"

  num_nodes = 16
}

module "aptos-node" {
  source = "github.com/aptos-labs/aptos-core.git//terraform/aptos-node/gcp?ref=experimental"

  region  = local.region  # Specify the region
  zone    = local.zone    # Specify the zone suffix
  project = local.project # Specify your GCP project name

  validator_name = "aptos-google-europe-nodes"

  # for naming purposes to avoid name collisions
  chain_name          = "aptos-google"
  num_validators      = local.num_nodes
  num_fullnode_groups = local.num_nodes

  era       = 1 # bump era number to wipe the chain. KEEP THIS NUMERIC
  image_tag = "performance_08e9119a20d2c873848dda724d811c239ca393e3"

  enable_monitoring = false
  enable_logger     = false

  utility_instance_num = local.num_nodes + 2

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
}

resource "local_file" "kubectx" {
  filename = "kubectx.sh"
  content  = <<EOF
  #!/bin/bash

  gcloud container clusters get-credentials aptos-${terraform.workspace} --zone ${local.region}-${local.zone} --project ${local.project}
  EOF
}
