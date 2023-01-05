#!/usr/bin/env python3

import subprocess
from typing import List, Optional, Sequence, Tuple, TypedDict

import click
import os
import yaml
from cluster import get_validator_fullnode_hosts
from constants import CLUSTERS, KUBE_CONTEXTS, LOADTEST_POD_SPEC, LOADTEST_POD_NAME


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
                    "image": "us-west1-docker.pkg.dev/aptos-global/aptos-internal/tools:mainnet",
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
        "transaction-emitter",
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
        "--txn-expiration-time-secs=" f"{loadtestConfig['txn_expiration_time_secs']}",
    ]


def configure_loadtest(
    template: PodTemplate,
    loadtestConfig: LoadTestConfig,
) -> PodTemplate:
    pod = PodTemplate(template)
    pod["spec"]["containers"][0]["command"] = build_loadtest_command(loadtestConfig)
    return pod


def automatically_determine_targets() -> List[str]:
    """
    Automatically determine the targets to use for load testing.
    TODO: implement some target filtering
    """
    targets = []
    for cluster in CLUSTERS:
        validator_fullnode_hosts_cluster_list = get_validator_fullnode_hosts(cluster)
        for host in validator_fullnode_hosts_cluster_list:
            # targets.append(f"http://{host.validator_host}:80")
            targets.append(f"http://{host.fullnode_host}:80")

    return targets


def apply_spec(delete=False) -> None:
    """Delete the existing loadtest pod and apply the new spec. If delete=True, then just do the delete"""
    # For each cluster
    # TODO: implement some target cluster filtering
    procs: List[subprocess.Popen] = []
    for cluster in CLUSTERS:
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
        if delete:
            continue
        procs.append(
            subprocess.Popen(
                [
                    "kubectl",
                    "--context",
                    cluster_kube_config,
                    "apply",
                    "-f",
                    LOADTEST_POD_SPEC,
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

    config: LoadTestConfig = {
        "mint_key": mint_key,
        "chain_id": chain_id,
        "targets": target or automatically_determine_targets(),
        "target_tps": target_tps,
        "duration": duration,
        "mempool_backlog": mempool_backlog,
        "txn_expiration_time_secs": txn_expiration_time_secs,
    }
    spec = configure_loadtest(template, config)
    with open(LOADTEST_POD_SPEC, "w") as f:
        f.write(yaml.dump(spec))
        print(f"Wrote pod spec to {LOADTEST_POD_SPEC}")
    if apply or delete:
        apply_spec(delete=delete)
    else:
        print(yaml.dump(spec))


if __name__ == "__main__":
    main()
