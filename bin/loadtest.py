#!/usr/bin/env python3

import subprocess
from typing import List, Optional, Sequence, Tuple, TypedDict

import click
import yaml
from cluster import get_validator_fullnode_hosts
from constants import (
    CLUSTERS,
    KUBE_CONTEXTS,
    LOADTEST_POD_SPEC,
    LOADTEST_POD_NAME,
    LOADTEST_CLUSTERS,
)

REST_API_PORT = 8080


class Metadata(TypedDict):
    name: str


class Env(TypedDict):
    name: str
    value: str


class Container(TypedDict):
    name: str
    image: str
    env: Sequence[Env]
    command: Sequence[str]


class Spec(TypedDict):
    containers: Sequence[Container]


class PodTemplate(TypedDict):
    apiVersion: str
    kind: str
    metadata: Metadata
    spec: Spec


def build_pod_template() -> PodTemplate:
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": LOADTEST_POD_NAME,
        },
        "spec": {
            "restartPolicy": "Never",
            "containers": [
                {
                    "name": LOADTEST_POD_NAME,
                    "image": "aptoslabs/tools:devnet_performance",
                    "env": [
                        {
                            "name": "RUST_BACKTRACE",
                            "value": "1",
                        },
                        {
                            "name": "REUSE_ACC",
                            "value": "1",
                        },
                    ],
                    "command": [],
                    # sufficient resource utilization such that the txn-emitter
                    # is not the bottleneck
                    "resources": {
                        "requests": {
                            "cpu": "16",
                            "memory": "16Gi",
                        },
                        "limits": {
                            "cpu": "16",
                            "memory": "16Gi",
                        },
                    },
                }
            ],
        },
    }


class LoadTestConfig(TypedDict):
    mint_key: str
    chain_id: str
    targets: Sequence[str]
    target_tps: Optional[int]
    duration: int
    mempool_backlog: int
    txn_expiration_time_secs: int


def build_loadtest_command(
    loadtestConfig: LoadTestConfig,
) -> List[str]:
    return [
        "aptos-transaction-emitter",
        "emit-tx",
        f"--mint-key={loadtestConfig['mint_key']}",
        f"--chain-id={loadtestConfig['chain_id']}",
        *[f"--targets={target}" for target in loadtestConfig["targets"]],
        *[
            f"--target-tps={loadtestConfig['target_tps']}"
            if loadtestConfig["target_tps"]
            else f"--mempool-backlog={loadtestConfig['mempool_backlog']}"
        ],
        f"--duration={loadtestConfig['duration']}",
        f"--delay-after-minting=300",
        f"--expected-max-txns={20000 * loadtestConfig['duration']}",
        "--txn-expiration-time-secs=" f"{loadtestConfig['txn_expiration_time_secs']}",
        "--max-transactions-per-account=5",
        *(
            ["--transaction-type", "coin-transfer"]
            if loadtestConfig["coin_transfer"]
            else [
                "--transaction-type",
                "account-generation-large-pool",
                "create-new-resource",
                "--transaction-phases",
                "0",
                "1",
            ]
        ),
    ]


def configure_loadtest(
    template: PodTemplate,
    loadtestConfig: LoadTestConfig,
) -> PodTemplate:
    pod = PodTemplate(template)
    pod["spec"]["containers"][0]["command"] = build_loadtest_command(loadtestConfig)
    print(" ".join(pod["spec"]["containers"][0]["command"]))
    return pod


def automatically_determine_targets(clusters: List[str]) -> List[str]:
    """
    Automatically determine the targets to use for load testing.
    TODO: implement some target filtering
    """
    targets = []
    for cluster in clusters:
        validator_fullnode_hosts_cluster_list = get_validator_fullnode_hosts(cluster)
        for host in validator_fullnode_hosts_cluster_list:
            targets.append(f"http://{host.validator_host}:{REST_API_PORT}")
            # targets.append(f"http://{host.fullnode_host}:{REST_API_PORT}")

    return targets


def apply_spec(delete=False, only_asia=False) -> None:
    """Delete the existing loadtest pod and apply the new spec. If delete=True, then just do the delete"""
    # For each cluster
    # TODO: implement some target cluster filtering
    procs: List[subprocess.Popen] = []
    for cluster in CLUSTERS:
        spec_file = f"{cluster.value}_{LOADTEST_POD_SPEC}"

        print(f"Applying loadtest spec to {cluster}...")
        cluster_kube_config = KUBE_CONTEXTS[cluster]
        procs.append(
            subprocess.Popen(
                [
                    "kubectl",
                    "--context",
                    cluster_kube_config,
                    "delete",
                    "pod",
                    LOADTEST_POD_NAME,
                    "--ignore-not-found",
                    "--force",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        )
        if delete or (only_asia and cluster not in LOADTEST_CLUSTERS):
            print(f"Skipping cluster {cluster}")
            continue
        procs.append(
            subprocess.Popen(
                [
                    "kubectl",
                    "--context",
                    cluster_kube_config,
                    "apply",
                    "-f",
                    spec_file,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        )
    print("Waiting for kubectl to finish...")

    # wait for everything
    for proc in procs:
        proc.wait()
        if proc.returncode != 0:
            print(f"Error starting loadtest")
            outs, errs = proc.communicate()
            print(outs)
            print(errs)
            raise SystemExit(1)

    print("Done! Printing loadtest pod status...")
    print("$ ./bin/cluster.py kube get pods loadtest")
    print()
    subprocess.run(
        [
            "./bin/cluster.py",  # ensure this is run from project root
            "kube",
            "get",
            "pods",
            "loadtest",
        ],
    )


@click.command()
@click.argument("mint_key")
@click.argument("chain_id")
@click.argument(
    "target",
    nargs=-1,
)
@click.option(
    "--target-tps",
    type=int,
    show_default=True,
)
@click.option(
    "--duration",
    type=int,
    default=60,
    show_default=True,
)
@click.option(
    "--mempool-backlog",
    type=int,
    default=1000,
    show_default=True,
)
@click.option(
    "--txn-expiration-time-secs",
    type=int,
    default=60,
    show_default=True,
)
@click.option(
    "--apply",
    is_flag=True,
    default=False,
    show_default=True,
)
@click.option(
    "--delete",
    is_flag=True,
    default=False,
    show_default=True,
)
@click.option(
    "--coin-transfer",
    is_flag=True,
    default=False,
    show_default=True,
)
@click.option(
    "--only-asia",
    is_flag=True,
    default=False,
    show_default=True,
)
@click.option(
    "--only-within-cluster",
    is_flag=True,
    default=False,
    show_default=True,
)
def main(
    mint_key: str,
    chain_id: str,
    target_tps: Optional[int],
    duration: int,
    mempool_backlog: int,
    txn_expiration_time_secs: int,
    target: Tuple[str],
    apply: bool,
    delete: bool,
    coin_transfer: bool,
    only_asia: bool,
    only_within_cluster: bool,
) -> None:
    """
    Generate a pod spec for load testing.

    \b
    params:
        mint_key - Mint key to use for load testing
        chain_id - Chain id of the network to test
        target   - Target must be in the format of a url: http://<host>:<port>
        --apply  - Apply the generated pod spec to the cluster
        --delete - Delete the existing loadtest pods
    """
    template = build_pod_template()

    for cluster in CLUSTERS:
        config: LoadTestConfig = {
            "mint_key": mint_key,
            "chain_id": chain_id,
            "targets": target
            or automatically_determine_targets(
                [cluster] if only_within_cluster else list(CLUSTERS)
            ),
            "target_tps": target_tps,
            "duration": duration,
            "mempool_backlog": mempool_backlog,
            "txn_expiration_time_secs": txn_expiration_time_secs,
            "coin_transfer": coin_transfer,
            "delay_after_minting": 300,
        }
        spec = configure_loadtest(template, config)
        spec_file = f"{cluster.value}_{LOADTEST_POD_SPEC}"
        with open(spec_file, "w") as f:
            f.write(yaml.dump(spec))
            print(f"Wrote pod spec to {spec_file}")

    if apply or delete:
        apply_spec(delete=delete, only_asia=only_asia)
    else:
        print(yaml.dump(spec))


if __name__ == "__main__":
    main()
