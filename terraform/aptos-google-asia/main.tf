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

  num_nodes = 18

  aptos_affinity = {
    podAntiAffinity = { # don't schedule nodes on the same host
      requiredDuringSchedulingIgnoredDuringExecution = [
        {
          labelSelector = {
            matchExpressions = [
              {
                key      = "app.kubernetes.io/part-of",
                operator = "In",
                values   = ["aptos-node"]
              }
            ]
          }
          topologyKey = "kubernetes.io/hostname"
        }
      ]
    }
    nodeAffinity = { # affinity for the right instance types
      requiredDuringSchedulingIgnoredDuringExecution = {
        nodeSelectorTerms = [
          {
            matchExpressions = [
              {
                key      = "cloud.google.com/machine-family",
                operator = "In",
                values   = ["t2d"],
              }
            ]
          }
        ]
      }
    }
  }

  aptos_resources = {
    limits = {
      cpu    = "30"
      memory = "32Gi"
    }
    requests = {
      cpu    = "30"
      memory = "32Gi"
    }
  }
}

module "aptos-node" {
  source = "github.com/aptos-labs/aptos-core.git//terraform/aptos-node/gcp?ref=experimental"

  region  = local.region  # Specify the region
  zone    = local.zone    # Specify the zone suffix
  project = local.project # Specify your GCP project name

  validator_name = "aptos-google-asia-nodes"

  # for naming purposes to avoid name collisions
  chain_name          = "aptos-google"
  num_validators      = local.num_nodes
  num_fullnode_groups = local.num_nodes

  era       = 1 # bump era number to wipe the chain. KEEP THIS NUMERIC
  image_tag = "performance_08e9119a20d2c873848dda724d811c239ca393e3"

  # rely on separate monitoring and logging setup
  enable_monitoring = false
  enable_logger     = false

  # Autoscaling configuration
  gke_enable_autoscaling               = false
  gke_enable_node_autoprovisioning     = true
  gke_node_autoprovisioning_max_cpu    = 32 * 100 # space for at least 100 nodes
  gke_node_autoprovisioning_max_memory = 128 * 100

  # configure these
  helm_values = {
    validator = {
      image = {
        repo = "us-west1-docker.pkg.dev/aptos-global/aptos-internal/validator"
      }
      affinity  = local.aptos_affinity
      resources = local.aptos_resources
    }
    fullnode = {
      image = {
        repo = "us-west1-docker.pkg.dev/aptos-global/aptos-internal/validator"
      }
      affinity  = local.aptos_affinity
      resources = local.aptos_resources
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
