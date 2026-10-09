"""Check what a deployed ImprintRegistry actually exposes, against the source ABI.

The recurring risk with this project is a source/deployment drift: `src/` grows a
feature (the `recordsPage` clamp, `disputeDuplicate`) that the currently deployed
address does not have. This script makes that drift objective and reproducible:
it compiles the ABI into function selectors and checks each one against the
deployed runtime bytecode.

It is read-only. It never deploys or sends anything.

Usage:
    python verify_deployment.py                       # live testnet address from the manifest
    python verify_deployment.py --address 0x...
    python verify_deployment.py --rpc ... --abi service/abi.json
Exit code is non-zero if the deployed contract is missing any source function.
"""
import argparse
import json
import sys
from pathlib import Path

from web3 import Web3

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "deployments" / "monad-testnet.json"
DEFAULT_ABI = ROOT / "service" / "abi.json"
DEFAULT_RPC = "https://testnet-rpc.monad.xyz"


def canonical(t: dict) -> str:
    ty = t["type"]
    if ty.startswith("tuple"):
        inner = "(" + ",".join(canonical(c) for c in t["components"]) + ")"
        return inner + ty[len("tuple"):]
    return ty


def signature(entry: dict) -> str:
    return f"{entry['name']}({','.join(canonical(i) for i in entry['inputs'])})"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--address", default="")
    ap.add_argument("--rpc", default=DEFAULT_RPC)
    ap.add_argument("--abi", default=str(DEFAULT_ABI))
    args = ap.parse_args()

    address = args.address
    if not address:
        address = json.loads(MANIFEST.read_text())["address"]
        print(f"address from manifest: {address}")

    abi = json.loads(Path(args.abi).read_text())
    funcs = [e for e in abi if e["type"] == "function"]

    w3 = Web3(Web3.HTTPProvider(args.rpc, request_kwargs={"timeout": 30}))
    code = w3.eth.get_code(Web3.to_checksum_address(address))
    if len(code) == 0:
        print(f"FAIL: no contract code at {address}")
        return 2

    print(f"deployed runtime size: {len(code)} bytes")
    missing = []
    for e in sorted(funcs, key=lambda x: x["name"]):
        sig = signature(e)
        sel = Web3.keccak(text=sig)[:4]
        present = bytes(sel) in bytes(code)
        print(f"  {'ok ' if present else 'MISSING'}  {sig}")
        if not present:
            missing.append(sig)

    print()
    if missing:
        print(f"DRIFT: {len(missing)} source function(s) absent from the deployed contract:")
        for m in missing:
            print(f"  - {m}")
        print("=> the deployed contract predates the current source; redeploy to close the gap.")
        return 1
    print("IN SYNC: every source function is present in the deployed contract.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
