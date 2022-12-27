#!/usr/bin/env python3

import subprocess
from typing import List, Optional, Sequence, Tuple, TypedDict

import click
import yaml
from cluster import get_validator_fullnode_hosts
from constants import CLUSTERS


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
            "name": "loadtest",
        },
        "spec": {
            "containers": [
                {
                    "name": "loadtest",
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
            targets.append(f"http://{host.validator_host}:80")
            targets.append(f"http://{host.fullnode_host}:80")

    return targets


def apply_spec(spec: PodTemplate) -> None:
    subprocess.run(["kubectl", "delete", "pod", spec["metadata"]["name"]])
    yaml_spec = yaml.dump(spec).encode()
    subprocess.run(["kubectl", "apply", "-f", "-"], input=yaml_spec)


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
def main(
    mint_key: str,
    chain_id: str,
    target_tps: Optional[int],
    duration: int,
    mempool_backlog: int,
    txn_expiration_time_secs: int,
    target: Tuple[str],
    apply: bool,
) -> None:
    """
    Generate a pod spec for load testing.

    \b
    params:
        mint_key - Mint key to use for load testing
        chain_id - Chain id of the network to test
        target   - Target must be in the format of a url: http://<host>:<port>
        --apply  - Apply the generated pod spec to the cluster
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
    if apply:
        apply_spec(spec)
    else:
        print(yaml.dump(spec))


if __name__ == "__main__":
    main()
