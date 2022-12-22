#!/usr/bin/env python3

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

import subprocess
from typing import List, Optional, Sequence, Tuple, TypedDict

import click
import yaml
import os
import json

from kubernetes import client, config, watch


class Cluster(Enum):
    NA = "aptos-google-na"
    EU = "aptos-google-europe"
    ASIA = "aptos-google-asia"

GENESIS_DIRECTORY = "genesis"

GCP_PROJECT_NAME = "omega-booster-372221"
CLUSTERS = {Cluster.NA: 16, Cluster.EU: 16, Cluster.ASIA: 18}
KUBE_CONTEXTS = {
    Cluster.NA: "gke_omega-booster-372221_us-west1-a_aptos-aptos-google-na",
    Cluster.EU: "gke_omega-booster-372221_europe-west3-a_aptos-aptos-google-europe",
    Cluster.ASIA: "gke_omega-booster-372221_asia-east1-a_aptos-aptos-google-asia",
}
NAMESPACE = "default"
KUBE_CLIENTS = {}
config.load_kube_config()
for cluster, context in KUBE_CONTEXTS.items():
    KUBE_CLIENTS[cluster] = client.CoreV1Api(
        config.new_client_from_config(context=context)
    )
LAYOUT = {
    "root_key": "0x48136DF3174A3DE92AFDB375FFE116908B69FF6FAB9B1410E548A33FEA1D159D",
    "users": [
        f"{cluster.value}-node-{i}"
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


@dataclass
class ValidatorFullnodeHosts:
    validator_host: str
    fullnode_host: str


def get_validator_fullnode_host(
    services: client.V1ServiceList, node_name: str
) -> ValidatorFullnodeHosts:
    """
    Get the validator and fullnode hosts for the given node, in sorted order by their index
    """
    validator_host = ""
    fullnode_host = ""
    for service in services.items:
        if node_name in service.metadata.name:
            try:
                if "validator-lb" in service.metadata.name:
                    validator_host = service.status.load_balancer.ingress[0].ip
                if "fullnode-lb" in service.metadata.name:
                    fullnode_host = service.status.load_balancer.ingress[0].ip

            except (IndexError, TypeError):
                print(
                    f"Failed to get external LoadBalancer IP for service: {service.metadata.name}"
                )
                print("Please check that the service has an IP address")
                print(
                    f"kubectl --context {KUBE_CONTEXTS[cluster]} describe svc {service.metadata.name}"
                )
                raise SystemExit(1)
    return ValidatorFullnodeHosts(
        validator_host=validator_host, fullnode_host=fullnode_host
    )


# wipe network
def get_validator_fullnode_hosts(
    cluster: Cluster,
) -> List[ValidatorFullnodeHosts]:
    """
    Get the validator and fullnode hosts for the given cluster, in sorted order by their index
    """
    # get the services for each cluster
    client = KUBE_CLIENTS[cluster]
    services = client.list_namespaced_service(namespace=NAMESPACE)

    validator_fullnode_hosts_list = []

    num_nodes = CLUSTERS[cluster]
    for node in range(num_nodes):
        node_name = f"node-{node}"
        validator_fullnode_hosts = get_validator_fullnode_host(services, node_name)
        validator_fullnode_hosts_list.append(validator_fullnode_hosts)

    assert len(validator_fullnode_hosts_list) == num_nodes
    return validator_fullnode_hosts_list


def automatically_determine_targets() -> List[str]:
    """
    Automatically determine the targets for fullnode and validator hosts based on k8s services
    """
    output = subprocess.check_output(["kubectl", "get", "svc", "-o", "yaml"])
    services = yaml.safe_load(output)
    targets = []
    for service in services["items"]:
        # If we have ingress we can take traffic
        ingress = service.get("status", {}).get("loadBalancer", {}).get("ingress")
        name = service.get("metadata", {}).get("name", "")
        if ingress and "validator" in name:
            # Port is hardcoded for now
            port = 80
            targets.append(f"http://{name}:{port}")
    return targets


# authenticate with each network
@click.group()
def main() -> None:
    # Check that the current directory is the root of the repository.
    if not os.path.exists(".git"):
        print("This script must be run from the root of the repository.")
        raise SystemExit(1)


def auth_all_Cluster() -> int:
    ret = 0
    for cluster in Cluster:
        cp = subprocess.run(["bash", f"./terraform/{cluster}/kubectx.sh"])
        if cp.returncode != 0:
            ret = cp.returncode
            print(f"Failed to authenticate with cluster: {cluster}")
        else:
            print(f"Successfully authenticated with cluster: {cluster}")
    return ret


def reauth_gcloud() -> int:
    ret = subprocess.run(["gcloud", "auth", "login", "--update-adc"])
    if ret.returncode != 0:
        return ret.returncode
    ret = subprocess.run(["gcloud", "config", "set", "project", GCP_PROJECT_NAME])
    if ret.returncode != 0:
        return ret.returncode
    return 0


@main.command("auth")
def auth() -> None:
    ret = auth_all_Cluster()
    if ret != 0:
        print("Failed to authenticate with cluster")
        print("Attempting to re-authenticate with gcloud...")
        ret = reauth_gcloud()
        if ret != 0:
            print("Failed to re-authenticate with gcloud")
            raise SystemExit(1)
        ret = auth_all_Cluster()
        if ret != 0:
            print("Failed to authenticate with cluster")
            raise SystemExit(1)


def generate_keys_for_genesis() -> None:
    for cluster, nodes_per_cluster in CLUSTERS.items():
        for i in range(nodes_per_cluster):
            node_name = f"node-{i}"
            subprocess.run(
                [
                    "aptos",
                    "genesis",
                    "generate-keys",
                    "--output-dir",
                    f"{GENESIS_DIRECTORY}/{cluster.value}-{node_name}",
                ]
            )


def set_validator_configuration_for_genesis() -> None:
    # get the services for each cluster
    for cluster in CLUSTERS:
        validator_fullnode_hosts_cluster_list = get_validator_fullnode_hosts(cluster)
        for i, hosts in enumerate(validator_fullnode_hosts_cluster_list):
            node_index = f"node-{i}"
            node_username = f"{cluster.value}-{node_index}"
            print(f"Setting validator configuration for {node_username} via aptos CLI")
            subprocess.run(
                [
                    "aptos",
                    "genesis",
                    "set-validator-configuration",
                    "--owner-public-identity-file",
                    f"{GENESIS_DIRECTORY}/{node_username}/public-keys.yaml",
                    "--local-repository-dir",
                    "{GENESIS_DIRECTORY}",
                    "--username",
                    node_username,
                    "--validator-host",
                    f"{hosts.validator_host}:6180",
                    "--full-node-host",
                    f"{hosts.fullnode_host}:6182",
                    "--stake-amount",
                    f"{10**8 * 10**6}",  # 1M APT in octas
                ]
            )


# create genesis
@main.command("genesis")
@click.option(
    "--generate-keys",
    is_flag=True,
    default=False,
    help="Regenerate keys for genesis. Reuse files on disk if unset",
)
@click.option(
    "--set-validator-config",
    is_flag=True,
    default=False,
    help="Set validator config. Reuse files on disk if unset",
)
def genesis(
    generate_keys: bool = False,
    set_validator_config: bool = False,
) -> None:
    """
    Create genesis for the network
    """
    # generate new keys for each node
    if generate_keys:
        print("Regenerating keys for genesis via aptos CLI")
        generate_keys_for_genesis()

    # set the validator configuration for each node
    if set_validator_config:
        print("Setting validator configuration for genesis via aptos CLI")
        set_validator_configuration_for_genesis()

    # create the layout file
    with open("genesis/layout.yaml", "w") as outfile:
        yaml.dump(LAYOUT, outfile, default_flow_style=False)

    # create genesis
    subprocess.run(
        [
            "aptos",
            "genesis",
            "generate-genesis",
            "--local-repository-dir",
            GENESIS_DIRECTORY,
            "--output-dir",
            GENESIS_DIRECTORY,
        ]
    )


if __name__ == "__main__":
    main()