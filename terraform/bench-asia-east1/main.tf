terraform {
  required_version = "~> 1.3.6"
  backend "gcs" {}
}

variable "project" {
  type        = string
  description = "GCP project ID"
}

locals {
  region  = "asia-east1"
  zone    = "a"
  project = var.project
}

module "aptos-node" {
  source = "../../submodules/aptos-core/terraform/aptos-node/gcp"

  manage_via_tf = false # manage via cluster.py tooling instead

  region  = local.region  # Specify the region
  zone    = local.zone    # Specify the zone suffix
  project = local.project # Specify your GCP project name

  validator_name = "aptos-bench-asia-nodes"

  # for naming purposes to avoid name collisions
  chain_name          = "aptos-bench"

  # Toggle these on if you want a per-cluster monitoring and logging setup
  # Otherwise rely on a separate central monitoring and logging setup
  enable_monitoring = false
  enable_logger     = false

  # Autoscaling configuration
  gke_enable_autoscaling               = false
  gke_enable_node_autoprovisioning     = true
  # space for at least 100 k8s worker nodes, assuming 48 vCPU and 192 GB RAM per node
  gke_node_autoprovisioning_max_cpu    = 48 * 100
  gke_node_autoprovisioning_max_memory = 192 * 100
}

resource "local_file" "kubectx" {
  filename = "kubectx.sh"
  content  = <<-EOF
  #!/bin/bash

  gcloud container clusters get-credentials aptos-${terraform.workspace} --zone ${local.region}-${local.zone}
  EOF
}
