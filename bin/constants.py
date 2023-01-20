import os
import yaml
from enum import Enum
from typing import Dict
from kubernetes import config, client


class Cluster(Enum):
    US = "bench-us-west1"
    EU = "bench-europe-west4"
    ASIA = "bench-asia-east1"
    ALL = "all"


GENESIS_DIRECTORY = "genesis"
APTOS_NODE_HELM_CHART_DIRECTORY = "submodules/deployment-main/terraform/helm/aptos-node"
APTOS_NODE_HELM_VALUES_FILE = "aptos_node_helm_values.yaml"

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
if not GCP_PROJECT_ID:
    raise Exception("GCP_PROJECT_ID not set")

CLUSTERS = {Cluster.US: 16, Cluster.EU: 16, Cluster.ASIA: 18}
# CLUSTERS = {Cluster.NA: 5, Cluster.EU: 5, Cluster.ASIA: 6} # smaller cluster configuration for testing
KUBE_CONTEXTS = {
    Cluster.US: f"gke_{GCP_PROJECT_ID}_us-west1-a_aptos-{Cluster.US.value}",
    Cluster.EU: f"gke_{GCP_PROJECT_ID}_europe-west4-a_aptos-{Cluster.EU.value}",
    Cluster.ASIA: f"gke_{GCP_PROJECT_ID}_asia-east1-a_aptos-{Cluster.ASIA.value}",
}
NAMESPACE = "default"

with open(APTOS_NODE_HELM_VALUES_FILE, "r") as genesis_file:
    values = yaml.load(genesis_file, Loader=yaml.FullLoader)
    current_era = values["chain"]["era"]
    print(f"Loading config: {APTOS_NODE_HELM_VALUES_FILE} era: {current_era}")

LAYOUT = {
    # This is the same testing key as in forge: https://github.com/aptos-labs/aptos-core/blob/main/testsuite/forge/src/backend/k8s/constants.rs#L7-L10
    # The private mint key being: 0xE25708D90C72A53B400B27FC7602C4D546C7B7469FA6E12544F0EBFB2F16AE19
    "root_key": "0x48136DF3174A3DE92AFDB375FFE116908B69FF6FAB9B1410E548A33FEA1D159D",
    "users": [
        f"{cluster.value}-aptos-node-{i}"
        for cluster in CLUSTERS
        for i in range(CLUSTERS[cluster])
    ],
    "chain_id": int(
        current_era
    ),  # NOTE: the chain_id changes for each era to prevent new nodes from connecting to old chain as its shutting down
    "allow_new_validators": True,
    "epoch_duration_secs": 7200,
    "is_test": True,
    "min_price_per_gas_unit": 1,
    "min_stake": 10**8 * 10**6,
    "min_voting_threshold": 10**8 * 10**6,
    "max_stake": 10**8 * 10**9,
    "recurring_lockup_duration_secs": 86400,
    "required_proposer_stake": 10**8 * 10**6,
    "rewards_apy_percentage": 10,
    "voting_duration_secs": 43200,
    "voting_power_increase_limit": 20,
}

# load test
LOADTEST_POD_SPEC = "loadtest.yaml"
LOADTEST_POD_NAME = "loadtest"
LOADTEST_CLUSTERS = [Cluster.ASIA]

# clients generation
def kube_clients() -> Dict[Cluster, client.ApiClient]:
    clients = {}
    config.load_kube_config()
    for cluster, context in KUBE_CONTEXTS.items():
        clients[cluster] = config.new_client_from_config(context=context)
    return clients
