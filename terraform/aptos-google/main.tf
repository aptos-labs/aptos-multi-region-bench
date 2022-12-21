terraform {
  required_version = "~> 1.2.0"
  backend "gcs" {
    bucket = "aptos-googl-terraform-dev"
    prefix = "state/testnet"
  }
}

locals {

  nap_n2_affinity = {
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
                values   = ["n2"],
              }
            ]
          }
        ]
      }
    }
  }

  # This is the minimum required for a validator as per https://aptos.dev/nodes/validator-node/operator/node-requirements/
  node_requirements_resources = {
    limits = {
      cpu    = "16"
      memory = "32Gi"
    }
    requests = {
      cpu    = "16"
      memory = "32Gi"
    }
  }

  # to push the system, use the next highest instance type
  n2_standard_32_resources = {
    limits = {
      cpu    = "30"
      memory = "60Gi"
    }
    requests = {
      cpu    = "30"
      memory = "60Gi"
    }
  }
}


module "forge" {
  source = "github.com/aptos-labs/aptos-core.git//terraform/aptos-node-testnet/gcp?ref=experimental"

  manage_via_tf = true

  num_validators      = 20
  num_fullnode_groups = 20

  # max out size
  cluster_ipv4_cidr_block = "/10"

  region  = "us-central1"          # Specify the region
  zone    = "c"                    # Specify the zone suffix
  project = "omega-booster-372221" # Specify your GCP project name

  # for naming purposes to avoid name collisions
  chain_name = terraform.workspace

  era       = 7 # bump era number to wipe the chain. KEEP THIS NUMERIC
  image_tag = "mainnet"

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
  aptos_node_helm_values = {
    validator = {
      affinity  = local.nap_n2_affinity
      resources = local.n2_standard_32_resources
    }
    fullnode = {
      affinity  = local.nap_n2_affinity
      resources = local.n2_standard_32_resources
    }
    haproxy = {
      affinity = local.nap_n2_affinity
    }
  }
  genesis_helm_values = {
    genesis = {
    }
  }

  monitoring_helm_values = {
    # # We can allow-list certain CIDR ranges to access the monitoring dashboard
    # service = {
    #   monitoring = {
    #     # Only allow office wifi to access
    #     loadBalancerSourceRanges = ["173.195.79.58/32"]
    #   }
    # }

    monitoring = {
      # give prometheus a bunch of resources since we may need to share the on-board Grafana externally
      prometheus = {
        useHttps = false
        storage = {
          size = "200Gi"
        }
        resources = {
          limits = {
            memory = "60Gi"
          }
          requests = {
            memory = "50Gi"
          }
        }
      }
    }
  }
}
