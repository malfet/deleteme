"""Exercise every op that dispatches on has_mpp() and report which ones break.

Exit code encodes whether the outcome matched EXPECT, so each CI job is an
assertion rather than something a human has to eyeball in the logs.
"""

import os
import sys
import traceback

import torch


def cholesky_ex():
    if torch.linalg.cholesky_ex(torch.eye(6, device="mps")).info.item() != 0:
        raise AssertionError("cholesky_ex reported non-zero info for an identity matrix")


def multivariate_normal():
    torch.distributions.MultivariateNormal(
        torch.zeros(6, device="mps"), torch.eye(6, device="mps")
    ).sample()


def linalg_solve():
    a = torch.rand(128, 128, device="mps") + 128 * torch.eye(128, device="mps")
    torch.linalg.solve(a, torch.rand(128, 1, device="mps"))


def conv3d():
    x = torch.rand(1, 8, 16, 16, 16, device="mps")
    w = torch.rand(8, 8, 3, 3, 3, device="mps")
    torch.nn.functional.conv3d(x, w, padding=1)


def sdpa():
    q = torch.rand(1, 4, 128, 64, device="mps")
    torch.nn.functional.scaled_dot_product_attention(q, q, q)


expect = os.environ["EXPECT"]
requested = os.environ.get("PYTORCH_MPS_METAL_VERSION", "<unset>")
print(f"torch={torch.__version__} PYTORCH_MPS_METAL_VERSION={requested} EXPECT={expect}\n")

failed = []
for probe in (cholesky_ex, multivariate_normal, linalg_solve, conv3d, sdpa):
    try:
        probe()
        print(f"{probe.__name__:<22} ok")
    except Exception:
        failed.append(probe.__name__)
        print(f"{probe.__name__:<22} FAIL")
        traceback.print_exc()

print(f"\nfailed: {failed or 'none'}")
if expect == "pass" and failed:
    sys.exit(f"expected every probe to pass, but {failed} failed")
if expect == "fail" and not failed:
    sys.exit("expected the MPP failure to reproduce, but everything passed")
print(f"outcome matches EXPECT={expect}")
