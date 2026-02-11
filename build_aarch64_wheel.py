#!/usr/bin/env python3

# This script is for building  AARCH64 wheels using AWS EC2 instances.
# To generate binaries for the release follow these steps:
# 1. Update mappings for each of the Domain Libraries by adding new row to a table like this:
#         "v1.11.0": ("0.11.0", "rc1"),
# 2. Run script with following arguments for each of the supported python versions and required tag, for example:
# build_aarch64_wheel.py --key-name <YourPemKey> --use-docker --python 3.8 --branch v1.11.0-rc3


import os
import subprocess
import sys
import time
from typing import Optional, Union

import boto3


# AMI images for us-east-1, change the following based on your ~/.aws/config
os_amis = {
    "ubuntu20_04": "ami-052eac90edaa9d08f",  # login_name: ubuntu
    "ubuntu22_04": "ami-0c6c29c5125214c77",  # login_name: ubuntu
    "ubuntu24_04": "ami-0071c8c431eea0edb",  # login_name: ubuntu
    "redhat8": "ami-0698b90665a2ddcf1",  # login_name: ec2-user
}

ubuntu20_04_ami = os_amis["ubuntu24_04"]


def compute_keyfile_path(key_name: Optional[str] = None) -> tuple[str, str]:
    if key_name is None:
        key_name = os.getenv("AWS_KEY_NAME")
        if key_name is None:
            return os.getenv("SSH_KEY_PATH", ""), ""

    homedir_path = os.path.expanduser("~")
    default_path = os.path.join(homedir_path, ".ssh", f"{key_name}.pem")
    return os.getenv("SSH_KEY_PATH", default_path), key_name


ec2 = boto3.resource("ec2")


def ec2_get_instances(filter_name, filter_value):
    return ec2.instances.filter(
        Filters=[{"Name": filter_name, "Values": [filter_value]}]
    )


def ec2_instances_of_type(instance_type="t4g.2xlarge"):
    return ec2_get_instances("instance-type", instance_type)


def ec2_instances_by_id(instance_id):
    rc = list(ec2_get_instances("instance-id", instance_id))
    return rc[0] if len(rc) > 0 else None


def start_instance(
    key_name, ami=ubuntu20_04_ami, instance_type="t4g.2xlarge", ebs_size: int = 50
):
    instances = start_instances(
        key_name, count=1, ami=ami, instance_type=instance_type, ebs_size=ebs_size
    )
    return instances[0]


def start_instances(
    key_name,
    count: int = 1,
    ami=ubuntu20_04_ami,
    instance_type="t4g.2xlarge",
    ebs_size: int = 50,
) -> list:
    """Launch one or more EC2 instances.

    All instances share the ssh-allworld security group. To allow inter-node
    communication, run allow_cluster_traffic.py to add a self-referencing rule
    to that group.
    """
    instances = ec2.create_instances(
        ImageId=ami,
        InstanceType=instance_type,
        SecurityGroups=["ssh-allworld"],
        KeyName=key_name,
        MinCount=count,
        MaxCount=count,
        BlockDeviceMappings=[
            {
                "DeviceName": "/dev/sda1",
                "Ebs": {
                    "DeleteOnTermination": True,
                    "VolumeSize": ebs_size,
                    "VolumeType": "standard",
                },
            }
        ],
    )
    for inst in instances:
        print(f"Created instance {inst.id}")

    for inst in instances:
        inst.wait_until_running()

    running = [ec2_instances_by_id(inst.id) for inst in instances]
    for inst in running:
        print(
            f"Instance {inst.id} running at {inst.public_dns_name}"
            f" (private: {inst.private_ip_address})"
        )

    return running


class RemoteHost:
    addr: str
    keyfile_path: str
    login_name: str
    container_id: Optional[str] = None
    ami: Optional[str] = None

    def __init__(self, addr: str, keyfile_path: str, login_name: str = "ubuntu"):
        self.addr = addr
        self.keyfile_path = keyfile_path
        self.login_name = login_name

    def _gen_ssh_prefix(self) -> list[str]:
        return [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-i",
            self.keyfile_path,
            f"{self.login_name}@{self.addr}",
            "--",
        ]

    @staticmethod
    def _split_cmd(args: Union[str, list[str]]) -> list[str]:
        return args.split() if isinstance(args, str) else args

    def run_ssh_cmd(self, args: Union[str, list[str]]) -> None:
        subprocess.check_call(self._gen_ssh_prefix() + self._split_cmd(args))

    def check_ssh_output(self, args: Union[str, list[str]]) -> str:
        return subprocess.check_output(
            self._gen_ssh_prefix() + self._split_cmd(args)
        ).decode("utf-8")

    def scp_upload_file(self, local_file: str, remote_file: str) -> None:
        subprocess.check_call(
            [
                "scp",
                "-i",
                self.keyfile_path,
                local_file,
                f"{self.login_name}@{self.addr}:{remote_file}",
            ]
        )

    def scp_download_file(
        self, remote_file: str, local_file: Optional[str] = None
    ) -> None:
        if local_file is None:
            local_file = "."
        subprocess.check_call(
            [
                "scp",
                "-i",
                self.keyfile_path,
                f"{self.login_name}@{self.addr}:{remote_file}",
                local_file,
            ]
        )

    def start_docker(self, image="quay.io/pypa/manylinux2014_aarch64:latest") -> None:
        self.run_ssh_cmd("sudo apt-get install -y docker.io")
        self.run_ssh_cmd(f"sudo usermod -a -G docker {self.login_name}")
        self.run_ssh_cmd("sudo service docker start")
        self.run_ssh_cmd(f"docker pull {image}")
        self.container_id = self.check_ssh_output(
            f"docker run -t -d -w /root {image}"
        ).strip()

    def using_docker(self) -> bool:
        return self.container_id is not None

    def run_cmd(self, args: Union[str, list[str]]) -> None:
        if not self.using_docker():
            return self.run_ssh_cmd(args)
        assert self.container_id is not None
        docker_cmd = self._gen_ssh_prefix() + [
            "docker",
            "exec",
            "-i",
            self.container_id,
            "bash",
        ]
        p = subprocess.Popen(docker_cmd, stdin=subprocess.PIPE)
        p.communicate(
            input=" ".join(["source .bashrc && "] + self._split_cmd(args)).encode(
                "utf-8"
            )
        )
        rc = p.wait()
        if rc != 0:
            raise subprocess.CalledProcessError(rc, docker_cmd)

    def check_output(self, args: Union[str, list[str]]) -> str:
        if not self.using_docker():
            return self.check_ssh_output(args)
        assert self.container_id is not None
        docker_cmd = self._gen_ssh_prefix() + [
            "docker",
            "exec",
            "-i",
            self.container_id,
            "bash",
        ]
        p = subprocess.Popen(docker_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        (out, err) = p.communicate(
            input=" ".join(["source .bashrc && "] + self._split_cmd(args)).encode(
                "utf-8"
            )
        )
        rc = p.wait()
        if rc != 0:
            raise subprocess.CalledProcessError(rc, docker_cmd, output=out, stderr=err)
        return out.decode("utf-8")

    def upload_file(self, local_file: str, remote_file: str) -> None:
        if not self.using_docker():
            return self.scp_upload_file(local_file, remote_file)
        tmp_file = os.path.join("/tmp", os.path.basename(local_file))
        self.scp_upload_file(local_file, tmp_file)
        self.run_ssh_cmd(
            ["docker", "cp", tmp_file, f"{self.container_id}:/root/{remote_file}"]
        )
        self.run_ssh_cmd(["rm", tmp_file])

    def download_file(self, remote_file: str, local_file: Optional[str] = None) -> None:
        if not self.using_docker():
            return self.scp_download_file(remote_file, local_file)
        tmp_file = os.path.join("/tmp", os.path.basename(remote_file))
        self.run_ssh_cmd(
            ["docker", "cp", f"{self.container_id}:/root/{remote_file}", tmp_file]
        )
        self.scp_download_file(tmp_file, local_file)
        self.run_ssh_cmd(["rm", tmp_file])

    def download_wheel(
        self, remote_file: str, local_file: Optional[str] = None
    ) -> None:
        if self.using_docker() and local_file is None:
            basename = os.path.basename(remote_file)
            local_file = basename.replace(
                "-linux_aarch64.whl", "-manylinux2014_aarch64.whl"
            )
        self.download_file(remote_file, local_file)

    def list_dir(self, path: str) -> list[str]:
        return self.check_output(["ls", "-1", path]).split("\n")


def wait_for_connection(addr, port, timeout=15, attempt_cnt=5):
    import socket

    for i in range(attempt_cnt):
        try:
            with socket.create_connection((addr, port), timeout=timeout):
                return
        except (ConnectionRefusedError, socket.timeout):  # noqa: PERF203
            if i == attempt_cnt - 1:
                raise
            time.sleep(timeout)


def update_apt_repo(host: RemoteHost) -> None:
    time.sleep(5)
    host.run_cmd("sudo systemctl stop apt-daily.service || true")
    host.run_cmd("sudo systemctl stop unattended-upgrades.service || true")
    host.run_cmd(
        "while systemctl is-active --quiet apt-daily.service; do sleep 1; done"
    )
    host.run_cmd(
        "while systemctl is-active --quiet unattended-upgrades.service; do sleep 1; done"
    )
    host.run_cmd("sudo apt-get update")
    time.sleep(3)
    host.run_cmd("sudo apt-get update")


def configure_cluster_hosts(hosts: list["RemoteHost"], instances: list) -> None:
    """Set up /etc/hosts and env vars so cluster nodes can find each other.

    Each node gets:
    - /etc/hosts entries mapping node0, node1, ... to private IPs
    - NODE_RANK, WORLD_SIZE, MASTER_ADDR, MASTER_PORT env vars
    """
    for i, host in enumerate(hosts):
        for j, inst in enumerate(instances):
            host.run_ssh_cmd(
                f"echo {inst.private_ip_address} node{j} | sudo tee -a /etc/hosts"
            )
        host.run_ssh_cmd(f"echo export NODE_RANK={i} >> ~/.bashrc")
        host.run_ssh_cmd(
            f"echo export WORLD_SIZE={len(hosts)} >> ~/.bashrc"
        )
        host.run_ssh_cmd("echo export MASTER_ADDR=node0 >> ~/.bashrc")
        host.run_ssh_cmd("echo export MASTER_PORT=29500 >> ~/.bashrc")
    print(
        f"Cluster configured: {len(hosts)} nodes, "
        f"master at {instances[0].private_ip_address}"
    )


def install_condaforge(
    host: RemoteHost, suffix: str = "latest/download/Miniforge3-Linux-aarch64.sh"
) -> None:
    print("Install conda-forge")
    host.run_cmd(f"curl -OL https://github.com/conda-forge/miniforge/releases/{suffix}")
    host.run_cmd(f"sh -f {os.path.basename(suffix)} -b")
    host.run_cmd(f"rm -f {os.path.basename(suffix)}")
    if host.using_docker():
        host.run_cmd("echo 'PATH=$HOME/miniforge3/bin:$PATH'>>.bashrc")
    else:
        host.run_cmd(
            [
                "sed",
                "-i",
                "'/^# If not running interactively.*/i PATH=$HOME/miniforge3/bin:$PATH'",
                ".bashrc",
            ]
        )


def install_condaforge_python(host: RemoteHost, python_version="3.8") -> None:
    if python_version == "3.6":
        # Python-3.6 EOLed and not compatible with conda-4.11
        install_condaforge(
            host, suffix="download/4.10.3-10/Miniforge3-4.10.3-10-Linux-aarch64.sh"
        )
        host.run_cmd(f"conda install -y python={python_version} numpy pyyaml")
    else:
        install_condaforge(
            host, suffix="download/4.11.0-4/Miniforge3-4.11.0-4-Linux-aarch64.sh"
        )
        # Pytorch-1.10 or older are not compatible with setuptools=59.6 or newer
        host.run_cmd(
            f"conda install -y python={python_version} numpy pyyaml setuptools>=59.5.0"
        )


def build_OpenBLAS(host: RemoteHost, git_clone_flags: str = "") -> None:
    print("Building OpenBLAS")
    host.run_cmd(
        f"git clone https://github.com/xianyi/OpenBLAS -b v0.3.28 {git_clone_flags}"
    )
    make_flags = "NUM_THREADS=64 USE_OPENMP=1 NO_SHARED=1 DYNAMIC_ARCH=1 TARGET=ARMV8"
    host.run_cmd(
        f"pushd OpenBLAS && make {make_flags} -j8 && sudo make {make_flags} install && popd && rm -rf OpenBLAS"
    )



def checkout_repo(
    host: RemoteHost,
    *,
    branch: str = "main",
    url: str,
    git_clone_flags: str,
    mapping: dict[str, tuple[str, str]],
) -> Optional[str]:
    for prefix in mapping:
        if not branch.startswith(prefix):
            continue
        tag = f"v{mapping[prefix][0]}-{mapping[prefix][1]}"
        host.run_cmd(f"git clone {url} -b {tag} {git_clone_flags}")
        return mapping[prefix][0]

    host.run_cmd(f"git clone {url} -b {branch} {git_clone_flags}")
    return None


def configure_system(
    host: RemoteHost,
    *,
    compiler: str = "gcc-8",
    use_conda: bool = True,
    python_version: str = "3.8",
) -> None:
    if use_conda:
        install_condaforge_python(host, python_version)

    print("Configuring the system")
    if not host.using_docker():
        update_apt_repo(host)
        host.run_cmd("sudo apt-get install -y ninja-build g++ git cmake gfortran unzip")
    else:
        host.run_cmd("yum install -y sudo")
        host.run_cmd("conda install -y ninja scons")

    if not use_conda:
        host.run_cmd(
            "sudo apt-get install -y python3-dev python3-yaml python3-setuptools python3-wheel python3-pip"
        )
    host.run_cmd("pip3 install dataclasses typing-extensions")
    if not use_conda:
        print("Installing Cython + numpy from PyPy")
        host.run_cmd("sudo pip3 install Cython")
        host.run_cmd("sudo pip3 install numpy")


def get_instance_name(instance) -> Optional[str]:
    if instance.tags is None:
        return None
    for tag in instance.tags:
        if tag["Key"] == "Name":
            return tag["Value"]
    return None


def list_instances(instance_type: str) -> None:
    print(f"All instances of type {instance_type}")
    for instance in ec2_instances_of_type(instance_type):
        ifaces = instance.network_interfaces
        az = ifaces[0].subnet.availability_zone if len(ifaces) > 0 else None
        print(
            f"{instance.id} {get_instance_name(instance)} {instance.public_dns_name} {instance.state['Name']} {az}"
        )


def terminate_instances(instance_type: str) -> None:
    print(f"Terminating all instances of type {instance_type}")
    instances = list(ec2_instances_of_type(instance_type))
    for instance in instances:
        print(f"Terminating {instance.id}")
        instance.terminate()
    print("Waiting for termination to complete")
    for instance in instances:
        instance.wait_until_terminated()


def parse_arguments():
    from argparse import ArgumentParser

    parser = ArgumentParser("Builid and test AARCH64 wheels using EC2")
    parser.add_argument("--key-name", type=str)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--test-only", type=str)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--os", type=str, choices=list(os_amis.keys()))
    group.add_argument("--ami", type=str)
    parser.add_argument(
        "--python-version",
        type=str,
        choices=[f"3.{d}" for d in range(6, 12)],
        default=None,
    )
    parser.add_argument("--alloc-instance", action="store_true")
    parser.add_argument("--num-instances", type=int, default=1,
                        help="Number of instances to launch (default: 1)")
    parser.add_argument("--list-instances", action="store_true")
    parser.add_argument("--pytorch-only", action="store_true")
    parser.add_argument("--keep-running", action="store_true")
    parser.add_argument("--terminate-instances", action="store_true")
    parser.add_argument("--instance-type", type=str, default="t4g.2xlarge")
    parser.add_argument("--ebs-size", type=int, default=50)
    parser.add_argument("--branch", type=str, default="main")
    parser.add_argument("--use-docker", action="store_true")
    parser.add_argument(
        "--compiler",
        type=str,
        choices=["gcc-7", "gcc-8", "gcc-9", "clang"],
        default="gcc-8",
    )
    parser.add_argument("--use-torch-from-pypi", action="store_true")
    parser.add_argument("--pytorch-build-number", type=str, default=None)
    parser.add_argument("--disable-mkldnn", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()
    ami = (
        args.ami
        if args.ami is not None
        else os_amis[args.os]
        if args.os is not None
        else ubuntu20_04_ami
    )
    keyfile_path, key_name = compute_keyfile_path(args.key_name)

    if args.list_instances:
        list_instances(args.instance_type)
        sys.exit(0)

    if args.terminate_instances:
        terminate_instances(args.instance_type)
        sys.exit(0)

    if len(key_name) == 0:
        raise RuntimeError("""
            Cannot start build without key_name, please specify
            --key-name argument or AWS_KEY_NAME environment variable.""")
    if len(keyfile_path) == 0 or not os.path.exists(keyfile_path):
        raise RuntimeError(f"""
            Cannot find keyfile with name: [{key_name}] in path: [{keyfile_path}], please
            check `~/.ssh/` folder or manually set SSH_KEY_PATH environment variable.""")

    # Starting the instance(s)
    instances = start_instances(
        key_name,
        count=args.num_instances,
        ami=ami,
        instance_type=args.instance_type,
        ebs_size=args.ebs_size,
    )
    instance_name = f"{args.key_name}-{args.os}"
    if args.python_version is not None:
        instance_name += f"-py{args.python_version}"
    for i, inst in enumerate(instances):
        node_suffix = f"-node{i}" if len(instances) > 1 else ""
        inst.create_tags(
            DryRun=False,
            Tags=[
                {
                    "Key": "Name",
                    "Value": f"{instance_name}{node_suffix}",
                }
            ],
        )

    hosts = []
    for inst in instances:
        wait_for_connection(inst.public_dns_name, 22)
        host = RemoteHost(inst.public_dns_name, keyfile_path)
        host.ami = ami
        hosts.append(host)

    if args.use_docker:
        for host in hosts:
            update_apt_repo(host)
            host.start_docker()

    if len(instances) > 1:
        configure_cluster_hosts(hosts, instances)

    if args.alloc_instance:
        if args.python_version is None:
            sys.exit(0)
        for host in hosts:
            install_condaforge_python(host, args.python_version)
        sys.exit(0)
