#!/usr/bin/env python3

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import json

import subprocess
import time
from typing import List, Tuple

import click
import yaml
import os

from kubernetes import client

from constants import *


@dataclass
class ValidatorFullnodeHosts:
    validator_host: str
    fullnode_host: str


def get_validator_fullnode_host(
    cluster: Cluster, services: client.V1ServiceList, node_name: str
) -> ValidatorFullnodeHosts:
    """
    Get the validator and fullnode hosts for the given node, in sorted order by their index
    """
    validator_host = ""
    fullnode_host = ""
    validator_svc_substring = "validator-lb" if HAPROXY_ENABLED else "validator"
    fullnode_svc_substring = "fullnode-lb" if HAPROXY_ENABLED else "fullnode"
    for service in services.items:
        if node_name in service.metadata.name:
            try:
                if validator_svc_substring in service.metadata.name:
                    validator_host = service.status.load_balancer.ingress[0].ip
                if fullnode_svc_substring in service.metadata.name:
                    fullnode_host = service.status.load_balancer.ingress[0].ip

            except:
                print(
                    f"Failed to get external LoadBalancer IP for service: {service.metadata.name}"
                )
                print("Please check that the service has an EXTERNAL-IP address")
                print(
                    f"kubectl --context {KUBE_CONTEXTS[cluster]} get svc {service.metadata.name}"
                )
                raise SystemExit(1)
    if validator_host == "" or fullnode_host == "":
        print(f"Failed to get validator and fullnode hosts for node: {node_name}")
        print(f"kubectl --context {KUBE_CONTEXTS[cluster]} get svc | grep {node_name}")
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
    core_client = client.CoreV1Api(kube_clients()[cluster])
    services = core_client.list_namespaced_service(namespace=NAMESPACE)

    validator_fullnode_hosts_list = []

    num_nodes = CLUSTERS[cluster]
    for node in range(num_nodes):
        node_name = f"node-{node}"
        validator_fullnode_hosts = get_validator_fullnode_host(
            cluster, services, node_name
        )
        validator_fullnode_hosts_list.append(validator_fullnode_hosts)

    assert len(validator_fullnode_hosts_list) == num_nodes
    return validator_fullnode_hosts_list


# authenticate with each network
@click.group()
def main() -> None:
    """Aptos Multi-region Cluster Management CLI"""
    # Check that the current directory is the root of the repository.
    if not os.path.exists(".git"):
        print("This script must be run from the root of the repository.")
        raise SystemExit(1)


def auth_all_clusters() -> int:
    ret = 0
    for cluster in CLUSTERS:
        cp = subprocess.run(["bash", f"./terraform/{cluster.value}/kubectx.sh"])
        if cp.returncode != 0:
            ret = cp.returncode
            print(f"Failed to authenticate with cluster: {cluster}")
            print("Did you run `terraform apply` for this cluster?")
        else:
            print(f"Successfully authenticated with cluster: {cluster}")
    return ret


def reauth_gcloud() -> int:
    ret = subprocess.run(["gcloud", "auth", "login", "--update-adc"])
    if ret.returncode != 0:
        return ret.returncode
    ret = subprocess.run(["gcloud", "config", "set", "project", GCP_PROJECT_ID])
    if ret.returncode != 0:
        return ret.returncode
    return 0


@main.command("auth")
def auth() -> None:
    """Authenticate with all clusters"""
    ret = auth_all_clusters()
    if ret != 0:
        print("Failed to authenticate with cluster")
        print("Attempting to re-authenticate with gcloud...")
        ret = reauth_gcloud()
        if ret != 0:
            print("Failed to re-authenticate with gcloud")
            raise SystemExit(1)
        ret = auth_all_clusters()
        if ret != 0:
            print("Failed to authenticate with cluster")
            raise SystemExit(1)


def generate_keys_for_genesis(cli_path: str = "") -> None:
    procs: List[subprocess.Popen] = []
    for cluster, nodes_per_cluster in CLUSTERS.items():
        for i in range(nodes_per_cluster):
            node_name = f"aptos-node-{i}"
            procs.append(
                subprocess.Popen(
                    [
                        f"{cli_path}aptos",
                        "genesis",
                        "generate-keys",
                        "--output-dir",
                        f"{GENESIS_DIRECTORY}/{cluster.value}-{node_name}",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )

    for proc in procs:
        proc.wait()
        if proc.returncode != 0:
            print(f"Failed to generate keys")
            outs, errs = proc.communicate()
            print(outs)
            print(errs)
            raise SystemExit(1)


def set_validator_configuration_for_genesis(cli_path: str = "") -> None:
    procs: List[subprocess.Popen] = []
    # get the services for each cluster
    for cluster in CLUSTERS:
        validator_fullnode_hosts_cluster_list = get_validator_fullnode_hosts(cluster)
        for i, hosts in enumerate(validator_fullnode_hosts_cluster_list):
            node_index = f"aptos-node-{i}"
            node_username = f"{cluster.value}-{node_index}"
            validator_host_with_port = f"{hosts.validator_host}:6180"
            fullnode_host_with_port = f"{hosts.fullnode_host}:6182"
            print(
                f"Setting validator configuration for {node_username} via aptos CLI: validator host: {validator_host_with_port}, fullnode host: {fullnode_host_with_port}"
            )
            procs.append(
                subprocess.Popen(
                    [
                        f"{cli_path}aptos",
                        "genesis",
                        "set-validator-configuration",
                        "--owner-public-identity-file",
                        f"{GENESIS_DIRECTORY}/{node_username}/public-keys.yaml",
                        "--local-repository-dir",
                        GENESIS_DIRECTORY,
                        "--username",
                        node_username,
                        "--validator-host",
                        validator_host_with_port,
                        "--full-node-host",
                        fullnode_host_with_port,
                        "--stake-amount",
                        f"{10**8 * 10**6}",  # 1M APT in octas
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )

    for proc in procs:
        proc.wait()
        if proc.returncode != 0:
            print(f"Failed to set validator configuration")
            print(proc.args)
            outs, errs = proc.communicate()
            print(outs)
            print(errs)
            raise SystemExit(1)


@main.group()
def genesis() -> None:
    """
    Create genesis for the network
    """
    pass


@genesis.command("create")
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
@click.option(
    "--cli-path",
    default="",
    help="Path to the aptos CLI executable",
)
def create_genesis(
    generate_keys: bool = False,
    set_validator_config: bool = False,
    cli_path: str = "",
) -> None:
    """
    Create genesis for the network and write it to the genesis directory
    """
    # generate new keys for each node
    if generate_keys:
        print("Regenerating keys for genesis via aptos CLI")
        generate_keys_for_genesis(cli_path)

    # set the validator configuration for each node
    if set_validator_config:
        print("Setting validator configuration for genesis via aptos CLI")
        set_validator_configuration_for_genesis(cli_path)

    # create the layout file
    with open("genesis/layout.yaml", "w") as outfile:
        yaml.dump(LAYOUT, outfile, default_flow_style=False)

    # create genesis
    subprocess.run(
        [
            f"{cli_path}aptos",
            "genesis",
            "generate-genesis",
            "--local-repository-dir",
            GENESIS_DIRECTORY,
            "--output-dir",
            GENESIS_DIRECTORY,
        ]
    )


@genesis.command("upload")
@click.option(
    "--apply",
    is_flag=True,
    default=False,
    help="Apply the genesis secrets to the relevant k8s clusters",
)
def kube_upload_genesis(
    apply: bool = False,
) -> None:
    """
    Upload genesis kubernetes secrets for each validator
    """
    dry_run_args = ["--dry-run=client", "--output=yaml"]

    # current_era = get_current_era()
    with open(APTOS_NODE_HELM_VALUES_FILE, "r") as genesis_file:
        values = yaml.load(genesis_file, Loader=yaml.FullLoader)
        current_era = values["chain"]["era"]
        print(f"Current era: {current_era}")

    # use kubectl to easily create secrets from files
    procs: List[subprocess.Popen] = []
    for available_cluster, nodes_per_cluster in CLUSTERS.items():

        cluster_kube_config = KUBE_CONTEXTS[available_cluster]
        cluster_genesis_fd = open(f"{available_cluster.value}-genesis.yaml", "w")

        # wipe the previous eras stuff too
        clean_previous_era_secrets(available_cluster, current_era)
        clean_previous_era_pvc(available_cluster, current_era)
        clean_previous_era_stateful_set(available_cluster, current_era)

        for i in range(nodes_per_cluster):
            node_name = f"aptos-node-{i}"
            node_username = f"{available_cluster.value}-{node_name}"

            # delete if found in apply mode
            if apply:
                subprocess.run(
                    [
                        "kubectl",
                        "--context",
                        cluster_kube_config,
                        "delete",
                        "secret",
                        f"{node_username}-genesis-e{current_era}",
                        "--ignore-not-found",
                    ],
                    stdout=cluster_genesis_fd,
                    stderr=subprocess.PIPE,
                    text=True,
                )

                procs.append(
                    subprocess.Popen(
                        [
                            "kubectl",
                            "--context",
                            cluster_kube_config,
                            "create",
                            "secret",
                            "generic",
                            f"{node_username}-genesis-e{current_era}",
                            f"--from-file=genesis.blob={GENESIS_DIRECTORY}/genesis.blob",
                            f"--from-file=waypoint.txt={GENESIS_DIRECTORY}/waypoint.txt",
                            f"--from-file=validator-identity.yaml={GENESIS_DIRECTORY}/{node_username}/validator-identity.yaml",
                            f"--from-file=validator-full-node-identity.yaml={GENESIS_DIRECTORY}/{node_username}/validator-full-node-identity.yaml",
                        ]
                        + (dry_run_args if not apply else []),
                        stdout=cluster_genesis_fd,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                )
                cluster_genesis_fd.flush()
                cluster_genesis_fd.write(f"---\n")
                cluster_genesis_fd.flush()

    # wait for everything
    for proc in procs:
        proc.wait()
        if proc.returncode != 0:
            print(f"Error uploading genesis secrets to nodes")
            outs, errs = proc.communicate()
            print(outs)
            print(errs)
            raise SystemExit(1)


@main.command("kube")
@click.argument("args", nargs=-1)
@click.option(
    "--cluster",
    type=click.Choice([c.value for c in Cluster]),
    default=Cluster.ALL.value,
    help="Cluster to run the command on",
)
def kube_commands(
    args: Tuple[str, ...],
    cluster: str,
) -> None:
    """Run kubectl commands on the selected cluster(s)"""
    cluster = Cluster(cluster)
    args = " ".join(args).split()
    print(args)
    for available_cluster in CLUSTERS:
        if cluster != available_cluster and cluster != Cluster.ALL:
            continue
        cluster_kube_config = KUBE_CONTEXTS[available_cluster]
        print(f"=== {available_cluster.value} ===")
        subprocess.run(
            [
                "kubectl",
                "--context",
                cluster_kube_config,
                *args,
            ]
        )
        print()


@main.command("helm")
@click.argument("args", nargs=-1)
@click.option(
    "--cluster",
    type=click.Choice([c.value for c in Cluster]),
    default=Cluster.ALL.value,
    help="Cluster to run the command on",
)
def helm_commands(
    args: Tuple[str, ...],
    cluster: str,
) -> None:
    """Run helm commands on the selected cluster(s)"""
    cluster = Cluster(cluster)
    args = " ".join(args).split()
    print(args)
    for available_cluster in CLUSTERS:
        if cluster != available_cluster and cluster != Cluster.ALL:
            continue
        cluster_kube_config = KUBE_CONTEXTS[available_cluster]
        print(f"=== {available_cluster.value} ===")
        subprocess.run(
            [
                "helm",
                "--kube-context",
                cluster_kube_config,
                *args,
            ],
        )
        print()


def patch_node_scale(
    cluster: Cluster,
    node_name: str,
    replicas: int,
    haproxy_enabled: bool = False,
) -> None:
    """
    Patch the node count for the given node
    """
    apps_client = client.AppsV1Api(kube_clients()[cluster])
    long_node_name = f"{cluster.value}-{node_name}"
    validator_sts_prefix = f"{long_node_name}-validator"
    fullnode_sts_prefix = f"{long_node_name}-fullnode-e"
    stateful_sets = apps_client.list_namespaced_stateful_set(NAMESPACE)
    for stateful_set in stateful_sets.items:
        if (
            validator_sts_prefix in stateful_set.metadata.name
            or fullnode_sts_prefix in stateful_set.metadata.name
        ):
            apps_client.patch_namespaced_stateful_set_scale(
                stateful_set.metadata.name,
                NAMESPACE,
                [{"op": "replace", "path": "/spec/replicas", "value": replicas}],
            )
    if haproxy_enabled:
        apps_client.patch_namespaced_deployment_scale(
            f"{long_node_name}-haproxy",
            NAMESPACE,
            [{"op": "replace", "path": "/spec/replicas", "value": replicas}],
        )

    print(f"Patched {long_node_name} scale to {replicas}")


@main.command("stop")
@click.option(
    "--cluster",
    type=click.Choice([c.value for c in Cluster]),
    default=Cluster.ALL.value,
    help="Cluster to run the command on",
)
def kube_stop(
    cluster: str,
) -> None:
    """Stop all compute on the cluster"""
    cluster = Cluster(cluster)
    for available_cluster in CLUSTERS:
        if cluster != available_cluster and cluster != Cluster.ALL:
            continue
        for i in range(CLUSTERS[available_cluster]):
            node_name = f"aptos-node-{i}"
            patch_node_scale(available_cluster, node_name, 0)


@main.command("start")
@click.option(
    "--cluster",
    type=click.Choice([c.value for c in Cluster]),
    default=Cluster.ALL.value,
    help="Cluster to run the command on",
)
def kube_start(
    cluster: str,
) -> None:
    """Start all compute on the cluster"""
    cluster = Cluster(cluster)
    for available_cluster in CLUSTERS:
        if cluster != available_cluster and cluster != Cluster.ALL:
            continue
        for i in range(CLUSTERS[available_cluster]):
            node_name = f"aptos-node-{i}"
            patch_node_scale(available_cluster, node_name, 1)


@main.command("delete")
@click.option(
    "--cluster",
    type=click.Choice([c.value for c in Cluster]),
    default=Cluster.ALL.value,
    help="Cluster to run the command on",
)
def helm_delete(
    cluster: str,
) -> None:
    """
    Delete all Aptos-created kubernetes resources on the cluster.
    Useful for a hard reset of the network, in case of a bad deploy, such as when helm is stuck in a bad state
    """
    cluster = Cluster(cluster)
    user_input = input("Delete all existing cluster resources (y/n)? ")
    if user_input.lower() != "y":
        print("Aborting delete operation")
        return
    delete_cluster(cluster)


def delete_cluster(
    cluster: Cluster,
) -> None:
    """
    Delete the cluster from the GCP project
    """
    procs = []
    for available_cluster in CLUSTERS:
        if cluster != available_cluster and cluster != Cluster.ALL:
            continue
        cluster_kube_config = KUBE_CONTEXTS[available_cluster]
        procs.append(
            subprocess.Popen(
                [
                    "helm",
                    "--kube-context",
                    cluster_kube_config,
                    "uninstall",
                    available_cluster.value,  # the helm_release is named after the cluster it is in
                ],
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
            )
        )
        print()

    for proc in procs:
        proc.wait()
        if proc.returncode != 0:
            print(f"Error deleting cluster workloads: {proc.args}")
            outs, errs = proc.communicate()
            print(outs.decode())
            print(errs.decode())
            raise SystemExit(1)


def get_current_era() -> str:
    """
    Get the current era from each of the clusters. They should be matching
    """
    eras = set()
    # for each cluster, infer the era from the helm values
    for cluster in CLUSTERS:
        cluster_kube_config = KUBE_CONTEXTS[cluster]
        ret = subprocess.run(
            [
                "helm",
                "--kube-context",
                cluster_kube_config,
                "get",
                "values",
                cluster.value,  # the helm_release is named after the cluster it is in
                "-o",
                "json",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        try:
            values = json.loads(ret.stdout)
            e = values["chain"]["era"]
        except Exception as e:
            print(f"Error fetching helm values for cluster {cluster.value}")
            print(e)
            print(ret.stdout)
            raise
        eras.add(e)

    assert len(eras) == 1, "Eras are not matching across clusters"
    cluster_era = eras.pop()
    print(f"Current testnet era across all clusters: {cluster_era}")
    return cluster_era


def aptos_node_helm_upgrade(
    cluster: Cluster, helm_chart_directory: str, values_file: str
) -> Tuple[Cluster, int]:
    num_nodes = CLUSTERS[cluster]
    helm_upgrade_override_values = [
        "--set",
        f"numFullnodeGroups={num_nodes}",
        "--set",
        f"numValidators={num_nodes}",
    ]
    # # delete the previous helm release secret
    # # this removes helm history, but speeds up the apply process substantially
    # core_client = client.CoreV1Api(kube_clients()[cluster])
    # secrets = core_client.list_namespaced_secret(NAMESPACE)
    # for secret in secrets.items:
    #     if secret.metadata.name.startswith(f"sh.helm.release.v1.{cluster.value}"):
    #         print(f"Deleting previous helm release secret: {secret.metadata.name}")
    #         core_client.delete_namespaced_secret(secret.metadata.name, NAMESPACE)
    return subprocess.Popen(
        [
            "helm",
            "--kube-context",
            KUBE_CONTEXTS[cluster],
            "upgrade",
            "--force",
            "--history-max=2",
            "--install",
            cluster.value,  # the helm_release is named after the cluster it is in
            helm_chart_directory,  # the helm chart version is that of the subdirectory
            "-f",
            values_file,
            *helm_upgrade_override_values,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


@main.command("upgrade")
@click.option(
    "--cluster",
    type=click.Choice([c.value for c in Cluster]),
    default=Cluster.ALL.value,
    help="Cluster to run the command on",
)
@click.option(
    "--values-file",
    "-f",
    type=click.Path(exists=True),
    help="Path to the values file to use",
    required=True,
    default=APTOS_NODE_HELM_VALUES_FILE,
)
@click.option(
    "--helm-chart-directory",
    "-d",
    type=click.Path(exists=True),
    help="Path to the helm chart directory",
    default=APTOS_NODE_HELM_CHART_DIRECTORY,
)
@click.option(
    "--new",
    is_flag=True,
    default=False,
    help="Whether to start the cluster from scratch",
)
def upgrade(
    cluster: str,
    values_file: str,
    helm_chart_directory: str,
    new: bool,
) -> None:
    """Wipes the cluster and redeploys via helm chart"""
    cluster = Cluster(cluster)
    procs: List[subprocess.Popen] = []
    # delete the cluster if it exists
    if new:
        print()
        user_input = input(
            "Delete existing cluster resources before installing network from scratch. This will de-provision all existing LoadBalancers and may take a while. (y/n)? "
        )
        if user_input.lower() != "y":
            print("Aborting upgrade")
            return
        try:
            delete_cluster(cluster)
        except SystemExit as e:
            print("The helm release in this cluster may not exist")
            print("Continuing with upgrade...")

    else:
        print(
            "Skipping cluster deletion, and reusing cluster state. (Use --new to delete clusters before upgrading)"
        )
    for available_cluster in CLUSTERS:
        if cluster != available_cluster and cluster != Cluster.ALL:
            continue
        print(
            f"Upgrading aptos-node helm release for cluster {available_cluster.value}"
        )
        procs.append(
            aptos_node_helm_upgrade(
                available_cluster, helm_chart_directory, values_file
            )
        )

    # wait for everything
    ret = 0
    sample_failed_process = None
    for proc in procs:
        proc.wait()
        if proc.returncode != 0:
            ret = proc.returncode
            sample_failed_process = proc

    if ret != 0:
        print(f"Error upgrading helm chart for cluster {sample_failed_process.args[3]}")
        outs, errs = sample_failed_process.communicate()
        print(outs)
        print(errs)
        print("Try deleting all helm state and trying again")
        print("./bin/cluster.py delete")
        print("./bin/cluster.py upgrade --new")
        raise SystemExit(1)


def clean_previous_era_secrets(cluster: Cluster, era: str) -> None:
    """
    Clean up previous era secrets from the given cluster
    """
    genesis_secret_era_substring = "genesis-e"
    for available_cluster in CLUSTERS:
        if cluster != available_cluster and cluster != Cluster.ALL:
            continue
        core_client = client.CoreV1Api(kube_clients()[available_cluster])
        secrets = core_client.list_namespaced_secret(NAMESPACE)
        for secret in secrets.items:
            # if the secret has an era in the name and is not the current era, delete it
            if (
                genesis_secret_era_substring in secret.metadata.name
                and f"{genesis_secret_era_substring}{era}" not in secret.metadata.name
            ):
                print(f"Deleting old secret {secret.metadata.name}")
                core_client.delete_namespaced_secret(
                    secret.metadata.name, secret.metadata.namespace
                )


def clean_previous_era_pvc(cluster: Cluster, era: str) -> None:
    """
    Clean up previous era PVCs from the given cluster
    """
    fullnode_pvc_era_substring = "fullnode-e"
    validator_pvc_era_substring = "validator-e"
    for available_cluster in CLUSTERS:
        if cluster != available_cluster and cluster != Cluster.ALL:
            continue
        for pvc_substring in [fullnode_pvc_era_substring, validator_pvc_era_substring]:
            core_client = client.CoreV1Api(kube_clients()[available_cluster])
            pvcs = core_client.list_namespaced_persistent_volume_claim(NAMESPACE)
            for pvc in pvcs.items:
                # if the PVC has an era in the name and is not the current era, delete it
                if (
                    pvc_substring in pvc.metadata.name
                    and f"{pvc_substring}{era}" not in pvc.metadata.name
                ):
                    print(f"Deleting old PVC {pvc.metadata.name}")
                    core_client.delete_namespaced_persistent_volume_claim(
                        pvc.metadata.name, pvc.metadata.namespace
                    )


def clean_previous_era_stateful_set(cluster: Cluster, era: str) -> None:
    """
    Clean up previous era stateful sets from the given cluster
    """
    fullnode_stateful_set_era_substring = "fullnode-e"
    for available_cluster in CLUSTERS:
        if cluster != available_cluster and cluster != Cluster.ALL:
            continue
        apps_client = client.AppsV1Api(kube_clients()[available_cluster])
        stateful_sets = apps_client.list_namespaced_stateful_set(NAMESPACE)
        for stateful_set in stateful_sets.items:
            # if the stateful_set has an era in the name and is not the current era, delete it
            if (
                fullnode_stateful_set_era_substring in stateful_set.metadata.name
                and f"{fullnode_stateful_set_era_substring}{era}"
                not in stateful_set.metadata.name
            ):
                print(f"Deleting old stateful_set {stateful_set.metadata.name}")
                apps_client.delete_namespaced_stateful_set(
                    stateful_set.metadata.name, stateful_set.metadata.namespace
                )


@main.command("era-clean")
@click.option(
    "--cluster",
    type=click.Choice([c.value for c in Cluster]),
    default=Cluster.ALL.value,
    help="Cluster to run the command on",
)
def clean_previous_era_resources(cluster: str) -> None:
    """
    Clean up previous era resources from the given cluster
    """
    # delete the previous era's resources

    cluster = Cluster(cluster)
    clean_previous_era_secrets(cluster, CURRENT_ERA)
    clean_previous_era_pvc(cluster, CURRENT_ERA)
    clean_previous_era_stateful_set(cluster, CURRENT_ERA)


@main.command("show-max-resources")
@click.option(
    "--cluster",
    type=click.Choice([c.value for c in Cluster]),
    default=Cluster.ALL.value,
    help="Cluster to run the command on",
)
def show_max_resources(cluster: str) -> None:
    """
    Show the maximum resources that can be used for a node. This assumes that most of your compute resources are used for nodes on each k8s worker, and that the rest of the compute
    is either on other machines, or is resrved for daemonsets.
    """
    cluster = Cluster(cluster)
    for available_cluster in CLUSTERS:
        if cluster != available_cluster and cluster != Cluster.ALL:
            continue
        apps_client = client.AppsV1Api(kube_clients()[available_cluster])
        daemonsets = apps_client.list_daemon_set_for_all_namespaces()
        sum_all_memory_requests = 0
        sum_all_memory_limits = 0
        sum_all_cpu_requests = 0
        sum_all_cpu_limits = 0
        for daemonset in daemonsets.items:
            try:
                sum_all_memory_requests += int(
                    daemonset.spec.template.spec.containers[0]
                    .resources.requests["memory"]
                    .replace("Mi", "")
                )
                sum_all_cpu_requests += int(
                    daemonset.spec.template.spec.containers[0]
                    .resources.requests["cpu"]
                    .replace("m", "")
                )
                sum_all_memory_limits += int(
                    daemonset.spec.template.spec.containers[0]
                    .resources.limits["memory"]
                    .replace("Mi", "")
                )
                sum_all_cpu_limits += int(
                    daemonset.spec.template.spec.containers[0]
                    .resources.limits["cpu"]
                    .replace("m", "")
                )
            except (KeyError, TypeError):
                print("No resource info for daemonset")
        print(
            f"Total memory requests: {sum_all_memory_requests}Mi, Total memory limits: {sum_all_memory_limits}Mi"
        )
        print(
            f"Total cpu requests: {sum_all_cpu_requests}m, Total cpu limits: {sum_all_cpu_limits}m"
        )


if __name__ == "__main__":
    main()
