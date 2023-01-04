from enum import Enum
from kubernetes import config


class Cluster(Enum):
    NA = "aptos-google-na"
    # EU = "aptos-google-europe"
    # EU2 = "aptos-google-europe2"
    EU4 = "aptos-google-europe"
    ASIA = "aptos-google-asia"
    ALL = "all"


GENESIS_DIRECTORY = "genesis"
APTOS_NODE_HELM_CHART_DIRECTORY = (
    "submodules/aptos-core-experimental/terraform/helm/aptos-node"
)
APTOS_NODE_HELM_VALUES_FILE = "aptos_node_helm_values.yaml"

GCP_PROJECT_NAME = "omega-booster-372221"
CLUSTERS = {Cluster.NA: 16, Cluster.EU4: 16, Cluster.ASIA: 18}
# CLUSTERS = {Cluster.NA: 5, Cluster.EU: 5, Cluster.ASIA: 6} # smaller cluster configuration for testing
KUBE_CONTEXTS = {
    Cluster.NA: "gke_omega-booster-372221_us-west1-a_aptos-aptos-google-na",
    # Cluster.EU: "gke_omega-booster-372221_europe-west3-a_aptos-aptos-google-europe", # this region does not have enough resources
    # Cluster.EU2: "gke_omega-booster-372221_europe-west2-a_aptos-aptos-google-europe2", # this region does not have T2D
    Cluster.EU4: "gke_omega-booster-372221_europe-west4-a_aptos-aptos-google-europe4",
    Cluster.ASIA: "gke_omega-booster-372221_asia-east1-a_aptos-aptos-google-asia",
}
NAMESPACE = "default"
KUBE_CLIENTS = {}
config.load_kube_config()
for cluster, context in KUBE_CONTEXTS.items():
    KUBE_CLIENTS[cluster] = config.new_client_from_config(context=context)

LAYOUT = {
    # This is the same testing key as in forge: https://github.com/aptos-labs/aptos-core/blob/main/testsuite/forge/src/backend/k8s/constants.rs#L7-L10
    # The private mint key being: 0xE25708D90C72A53B400B27FC7602C4D546C7B7469FA6E12544F0EBFB2F16AE19
    "root_key": "0x48136DF3174A3DE92AFDB375FFE116908B69FF6FAB9B1410E548A33FEA1D159D",
    "users": [
        f"{cluster.value}-aptos-node-{i}"
        for cluster in CLUSTERS
        for i in range(CLUSTERS[cluster])
    ],
    "chain_id": 4,  # TESTING chain_id
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
