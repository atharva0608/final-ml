"""
EKS Node User-Data Generation
==============================
Generates base64-encoded EKS bootstrap user-data scripts that work for both
amd64 (x86_64) and arm64 architectures.

Used by auto_rebalancer when attach_to_asg_enabled=True to produce fresh
architecture-appropriate user-data for cross-architecture Spot replacements,
instead of copying the source node's (possibly arch-specific) user-data.
"""

import base64
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def generate_eks_user_data(
    cluster_name: str,
    arch: str,
    kubernetes_version: Optional[str] = None,
    extra_kubelet_args: Optional[str] = None,
    custom_bootstrap_args: Optional[str] = None,
) -> str:
    """
    Return a base64-encoded EKS node bootstrap user-data script.

    The generated script calls /etc/eks/bootstrap.sh with architecture-aware
    node labels and configures the containerd runtime.  It is functionally
    equivalent to what EKS managed node groups inject via their launch templates.

    Args:
        cluster_name: EKS cluster name passed to bootstrap.sh.
        arch: Target node architecture — "amd64", "arm64", or "x86_64".
              "x86_64" is treated identically to "amd64".
        kubernetes_version: Optional K8s version string (e.g. "1.29").
                            Currently informational only; reserved for future
                            version-specific bootstrap logic.
        extra_kubelet_args: Optional additional --kubelet-extra-args flags
                            (space-separated, e.g. '--max-pods=110').
        custom_bootstrap_args: Optional additional arguments appended verbatim
                               after the standard bootstrap.sh invocation.

    Returns:
        Base64-encoded UTF-8 string suitable for use as EC2 UserData.
    """
    # Normalise arch label: AWS uses "x86_64" in AMI metadata but K8s node
    # labels use "amd64".  We add both forms so tooling that checks either works.
    _arch_label = "arm64" if arch == "arm64" else "amd64"

    _kubelet_args = f"--node-labels=kubernetes.io/arch={_arch_label}"
    if extra_kubelet_args:
        _kubelet_args = f"{_kubelet_args} {extra_kubelet_args.strip()}"

    _bootstrap_extra = f"    {custom_bootstrap_args.strip()}" if custom_bootstrap_args else ""
    _version_comment = f"  # kubernetes_version={kubernetes_version}" if kubernetes_version else ""

    script = f"""#!/bin/bash
set -ex
/etc/eks/bootstrap.sh {cluster_name} \\{_version_comment}
  --kubelet-extra-args '{_kubelet_args}' \\
  --use-max-pods false \\
  --container-runtime containerd{_bootstrap_extra and chr(10) + _bootstrap_extra or ''}
"""

    encoded = base64.b64encode(script.encode("utf-8")).decode("utf-8")
    logger.info(
        f"[user_data] Generated EKS user-data for cluster='{cluster_name}' "
        f"arch={_arch_label} ({len(encoded)} chars base64)"
    )
    return encoded
