terraform {
  required_version = "~> 1.2.0"
  backend "gcs" {
    bucket = "aptos-googl-terraform-dev"
    prefix = "state/testnet"
  }
}
module "aptos-node" {
  source = "github.com/aptos-labs/aptos-core.git//terraform/aptos-node/gcp?ref=experimental"

  region  = "europe-west3"         # Specify the region
  zone    = "a"                    # Specify the zone suffix
  project = "omega-booster-372221" # Specify your GCP project name

  # for naming purposes to avoid name collisions
  chain_name          = "aptos-google"
  num_validators      = 2
  num_fullnode_groups = 2
  validator_name      = "aptos-google-europe-nodes"

  era       = 1 # bump era number to wipe the chain. KEEP THIS NUMERIC
  image_tag = "performance_08e9119a20d2c873848dda724d811c239ca393e3"

  enable_monitoring = false
  enable_logger     = false

  utility_instance_num = 4

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
