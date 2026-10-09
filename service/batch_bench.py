"""Cost and speed of registering on Monad testnet, measured, not estimated.

Part A: N registrations through the real product path (mark, passkey assertion, relay), one after
        another. Each uses a distinct synthetic image so the registry is not filled with duplicates.
Part B: a burst of M registrations sent at once from one key (EIP-712 path, consecutive nonces),
        to see how many land per block and how long the whole burst takes.

Run from service/:  python batch_bench.py [N] [M]
Writes results/batch_bench.json (in phase1/results).
"""
import base64
import io
import json
import statistics
import sys
import time
from pathlib import Path

import requests
from eth_account import Account
from eth_account.messages import encode_typed_data
from PIL import Image

import chain
from softpasskey import SoftPasskey
import urllib.request

import os
API = os.getenv("IMPRINT_BENCH_API", "http://localhost:8000")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 60
M = int(sys.argv[2]) if len(sys.argv) > 2 else 20
OUT = Path(__file__).parent.parent / "phase1" / "results" / "batch_bench.json"

w3 = chain.w3()
c = chain.contract()
acct = chain._relayer_account()


def bal():
    return w3.eth.get_balance(acct.address) / 1e18


BENCH_IMG = Path(__file__).parent.parent / "phase1" / "images_bench"
BENCH_IMG.mkdir(exist_ok=True)


def bench_image(i: int) -> Image.Image:
    """A distinct real photo per registration, so the registry is not filled with look-alikes."""
    p = BENCH_IMG / f"bench_{i:03d}.png"
    if not p.exists():
        data = urllib.request.urlopen(f"https://picsum.photos/seed/imprintB{i}/640/480", timeout=60).read()
        Image.open(io.BytesIO(data)).convert("RGB").save(p)
    return Image.open(p).convert("RGB")


def png_bytes(img):
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


# ---------------------------------------------------------------- part A
print(f"relayer {acct.address} balance {bal():.3f} MON, registry count {chain.count()}")
pk = SoftPasskey("imprint-bench")
rows = []
b0 = bal()
t_all = time.time()
for i in range(N):
    img = bench_image(i)
    t0 = time.time()
    m = requests.post(f"{API}/mark", files={"file": (f"b{i}.png", png_bytes(img), "image/png")}).json()
    t_mark = time.time() - t0
    ch = requests.get(f"{API}/challenge", params={"watermark_id": m["watermark_id"], "fingerprint": "0x" + m["fingerprint"]}).json()["challenge"]
    t1 = time.time()
    r = requests.post(f"{API}/register", json={"watermark_id": m["watermark_id"], "fingerprint": "0x" + m["fingerprint"],
                                               "auth": pk.assert_challenge(ch), "qx": pk.qx, "qy": pk.qy})
    t_reg = time.time() - t1
    if r.status_code == 409:
        print(f"  {i}: skipped, looks like an earlier registration")
        continue
    if r.status_code != 200:
        print("register failed:", r.status_code, r.text[:200])
        break
    j = r.json()
    rc = w3.eth.get_transaction_receipt(j["tx_hash"])
    cost = rc["gasUsed"] * rc["effectiveGasPrice"] / 1e18
    rows.append({"i": i, "mark_s": round(t_mark, 2), "register_s": round(t_reg, 2), "chain_s": j["seconds"],
                 "gas": rc["gasUsed"], "gwei": rc["effectiveGasPrice"] / 1e9, "cost_mon": cost, "block": j["block"]})
    if i % 10 == 0:
        print(f"  {i}: mark {t_mark:.2f}s, register {t_reg:.2f}s (chain {j['seconds']}s), {rc['gasUsed']} gas, {cost:.4f} MON", flush=True)
a_total = time.time() - t_all
a_spent = b0 - bal()
print(f"part A: {len(rows)} registrations in {a_total:.0f}s, spent {a_spent:.3f} MON")

# ---------------------------------------------------------------- part B
prior = json.loads(OUT.read_text()) if OUT.exists() else {}
if M == 0 and "part_b" in prior:
    part_b = prior["part_b"]
    print("part B: reused earlier result")
else:
    part_b = None
if part_b is None:
    domain = {"name": "ImprintRegistry", "version": "1", "chainId": chain.CHAIN_ID, "verifyingContract": c.address}
    types = {"Register": [{"name": "watermarkId", "type": "bytes32"}, {"name": "fingerprint", "type": "bytes32"}]}
    nonce = w3.eth.get_transaction_count(acct.address, "pending")
    gas_price = w3.eth.gas_price
    signed = []
    for k in range(M):
        wid = (0xB0_0000 + int(time.time()) * 1000 + k).to_bytes(32, "big")
        fp = (0xF0 + k).to_bytes(32, "big")
        sig = Account.sign_typed_data(acct.key, domain, types, {"watermarkId": wid, "fingerprint": fp}).signature
        fn = c.functions.registerSigned(wid, fp, acct.address, sig)
        tx = fn.build_transaction({"from": acct.address, "nonce": nonce + k, "gas": 200_000, "gasPrice": gas_price, "chainId": chain.CHAIN_ID})
        signed.append(acct.sign_transaction(tx))
    b1 = bal()
    t0 = time.time()
    hashes = [w3.eth.send_raw_transaction(s.raw_transaction) for s in signed]
    t_sent = time.time() - t0
    receipts = [w3.eth.wait_for_transaction_receipt(h, timeout=120, poll_latency=0.25) for h in hashes]
    t_burst = time.time() - t0
    blocks = sorted({r["blockNumber"] for r in receipts})
    ok = sum(1 for r in receipts if r["status"] == 1)
    b_spent = b1 - bal()
    print(f"part B: {ok}/{M} landed, sent in {t_sent:.2f}s, all confirmed in {t_burst:.2f}s, across {len(blocks)} block(s) {blocks[0]}..{blocks[-1]}, spent {b_spent:.3f} MON")

    part_b = {"m": M, "landed": ok, "sent_s": round(t_sent, 2), "confirmed_s": round(t_burst, 2), "blocks": len(blocks), "first_block": blocks[0], "last_block": blocks[-1], "spent_mon": round(b_spent, 4)}

res = {
    "contract": c.address, "chain_id": chain.CHAIN_ID,
    "part_a": {
        "n": len(rows), "total_s": round(a_total, 1), "spent_mon": round(a_spent, 4),
        "register_s_median": statistics.median(r["register_s"] for r in rows),
        "register_s_p90": sorted(r["register_s"] for r in rows)[int(0.9 * len(rows)) - 1],
        "chain_s_median": statistics.median(r["chain_s"] for r in rows),
        "mark_s_median": statistics.median(r["mark_s"] for r in rows),
        "gas_median": statistics.median(r["gas"] for r in rows),
        "gwei_median": statistics.median(r["gwei"] for r in rows),
        "cost_mon_median": statistics.median(r["cost_mon"] for r in rows),
        "rows": rows,
    },
    "part_b": part_b,
    "balance_after_mon": round(bal(), 3),
}
OUT.write_text(json.dumps(res, indent=1))
print("written", OUT)
