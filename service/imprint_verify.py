"""imprint-verify: check an image against the Imprint registry without trusting the service.

This is a small, independent tool. It reads the image itself (Pillow), computes
the fingerprint itself (the published spec in fingerprint.py) and reads the
registry straight from Monad (web3). It never calls the Imprint API and never
trusts the server's verdict, so a lie by the service cannot make it say
"verified".

Scope, stated plainly
---------------------
This checks *content* (the perceptual fingerprint), not the hidden TrustMark
watermark. Decoding the watermark needs the TrustMark model, which this tool
deliberately does not bundle: it stays Pillow + numpy + scipy + web3. So it
cannot, on its own, read the ID out of an image. You give it the ID (``--id``)
or let it look for the closest record by content (``--scan``).

Statuses
--------
verified             content is within T_MATCH of the named record, no earlier look-alike
altered              content descends from the named record but has changed (within T_NEAR)
disputed             the named record has an earlier look-alike from a different signer
likely_match         --scan found a record within T_NEAR but not the named one / not exact
not_found            no record named or, for --scan, nothing within T_NEAR
unsupported_version  the requested fingerprint algorithm is not the supported one
error                the image, the RPC or the registry could not be read

Usage
-----
    python imprint_verify.py IMAGE.png --id 0x...        # check against a known ID
    python imprint_verify.py IMAGE.png --scan            # find the closest record by content
    python imprint_verify.py IMAGE.png --id 0x... --json # machine-readable

Exit code is 0 for verified/likely_match, 1 for altered/disputed/not_found/
unsupported_version, 2 for error, so it composes in scripts.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import fingerprint
from verdict import T_DUP, T_MATCH, T_NEAR, Record

DEFAULT_RPC = "https://testnet-rpc.monad.xyz"
DEFAULT_REGISTRY = "0xf4a792ddb0c83Bdf1Ed2E1220B197760d821396c"
DEFAULT_CHAIN_ID = 10143
PAGE = 100


class VerifyError(Exception):
    pass


# ------------------------------------------------------------------ registry
class RegistryReader:
    """A minimal, read-only registry client. No writes, no service in the loop."""

    def __init__(self, rpc: str, registry: str, chain_id: int, abi_path: Path):
        from web3 import Web3

        self.chain_id = int(chain_id)
        self._w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
        if not self._w3.is_connected():
            raise VerifyError(f"could not reach the RPC at {rpc}")
        abi = json.loads(abi_path.read_text())
        self._c = self._w3.eth.contract(address=Web3.to_checksum_address(registry), abi=abi)
        self.registry = Web3.to_checksum_address(registry)

    def _to_record(self, wid: bytes, tup) -> Record:
        signer, ts, block, fp = tup
        return Record(watermark_id="0x" + bytes(wid).hex(), fingerprint=bytes(fp).hex(),
                      signer=signer, timestamp=int(ts), block=int(block))

    def record(self, watermark_id: str) -> Record | None:
        from web3 import Web3

        wid = bytes.fromhex(watermark_id[2:] if watermark_id.startswith("0x") else watermark_id)
        tup = self._c.functions.recordOf(wid).call()
        if int(tup[1]) == 0:
            return None
        return self._to_record(wid, tup)

    def records(self, limit: int) -> list[Record]:
        n = min(int(self._c.functions.count().call()), max(0, int(limit)))
        out: list[Record] = []
        start = 0
        while start < n:
            ids, recs = self._c.functions.recordsPage(start, min(PAGE, n - start)).call()
            if not ids:
                break
            out.extend(self._to_record(wid, tup) for wid, tup in zip(ids, recs))
            start += len(ids)
        return out


# ------------------------------------------------------------------ verify
def fingerprint_image(path: str) -> str:
    from PIL import Image

    try:
        img = Image.open(path)
        img.load()
    except Exception as e:
        raise VerifyError(f"could not read {path} as an image: {e}") from e
    return fingerprint.compute(img)


def _rec_dict(r: Record | None) -> dict | None:
    if r is None:
        return None
    return {"watermark_id": r.watermark_id, "fingerprint": r.fingerprint, "signer": r.signer,
            "timestamp": r.timestamp, "block": r.block}


def _earlier_lookalike(record: Record, records: list[Record]) -> tuple[Record, int] | None:
    best = None
    for r in records:
        if r.watermark_id == record.watermark_id:
            continue
        if r.signer.lower() == record.signer.lower():
            continue
        if (r.timestamp, r.block) >= (record.timestamp, record.block):
            continue
        d = fingerprint.distance(record.fingerprint, r.fingerprint)
        if d <= T_DUP and (best is None or (r.timestamp, r.block) < (best[0].timestamp, best[0].block)):
            best = (r, d)
    return best


def verify_image(path: str, *, watermark_id: str | None = None, scan: bool = False,
                 reader: RegistryReader | None = None, max_records: int = 5000,
                 algo: str | None = None) -> dict:
    """Compute the fingerprint and decide against the chain. Returns a plain dict."""
    base = {"algorithm": fingerprint.ALGORITHM, "version": fingerprint.VERSION,
            "assurance": "content-only", "method": "scan" if scan else "id",
            "fingerprint": None, "distance": None, "record": None, "earlier": None,
            "checked": {"records_scanned": 0}}

    if algo is not None and algo != fingerprint.ALGORITHM:
        return {**base, "status": "unsupported_version",
                "message": f"requested algorithm {algo!r} is not supported "
                           f"(this build implements {fingerprint.ALGORITHM!r})"}

    if reader is None:
        return {**base, "status": "error", "message": "no registry reader configured"}

    try:
        fp = fingerprint_image(path)
    except VerifyError as e:
        return {**base, "status": "error", "message": str(e)}
    base["fingerprint"] = fp

    try:
        records = reader.records(max_records)
    except Exception as e:
        return {**base, "status": "error", "message": f"could not read the registry: {e}"}
    base["checked"]["records_scanned"] = len(records)

    def decide_against(record: Record, distance: int, named: bool) -> dict:
        earlier = _earlier_lookalike(record, records)
        if earlier is not None and distance <= T_MATCH:
            return {**base, "status": "disputed", "distance": distance, "record": _rec_dict(record),
                    "earlier": _rec_dict(earlier[0]),
                    "message": "A near-identical image was registered earlier by a different signer."}
        if distance <= T_MATCH:
            if named:
                return {**base, "status": "verified", "distance": distance, "record": _rec_dict(record),
                        "message": "Content is consistent with this record (watermark not decoded by this tool)."}
            return {**base, "status": "likely_match", "distance": distance, "record": _rec_dict(record),
                    "message": "Content is very close to this record (watermark not decoded)."}
        if named and distance <= T_NEAR:
            return {**base, "status": "altered", "distance": distance, "record": _rec_dict(record),
                    "message": "Content descends from this record but has changed (edited or cropped)."}
        if distance <= T_NEAR:
            return {**base, "status": "likely_match", "distance": distance, "record": _rec_dict(record),
                    "message": "Content is similar to this record (watermark not decoded)."}
        return {**base, "status": "not_found", "distance": distance, "record": _rec_dict(record),
                "message": "This image is not close enough to the named record."}

    if watermark_id:
        try:
            rec = reader.record(watermark_id)
        except Exception as e:
            return {**base, "status": "error", "message": f"could not read the record: {e}"}
        if rec is None:
            return {**base, "status": "not_found",
                    "message": "No record with that ID is in the registry."}
        return decide_against(rec, fingerprint.distance(fp, rec.fingerprint), named=True)

    if scan:
        best = None
        for r in records:
            d = fingerprint.distance(fp, r.fingerprint)
            if best is None or d < best[1]:
                best = (r, d)
        if best is None:
            return {**base, "status": "not_found", "message": "The registry is empty."}
        return decide_against(best[0], best[1], named=False)

    return {**base, "status": "error", "message": "pass --id or --scan"}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="imprint_verify", description="Verify an image against Imprint on Monad.")
    p.add_argument("image", help="path to the image to check")
    p.add_argument("--id", dest="watermark_id", default=None, help="the 32-byte watermark ID to check against")
    p.add_argument("--scan", action="store_true", help="find the closest record by content instead of using --id")
    p.add_argument("--rpc", default=DEFAULT_RPC, help=f"Monad RPC URL (default {DEFAULT_RPC})")
    p.add_argument("--registry", default=DEFAULT_REGISTRY, help="registry contract address")
    p.add_argument("--chain-id", type=int, default=DEFAULT_CHAIN_ID)
    p.add_argument("--abi", default=None, help="path to abi.json (default: next to this script)")
    p.add_argument("--algo", default=None, help="require a specific fingerprint algorithm id")
    p.add_argument("--max-records", type=int, default=5000, help="cap records read when scanning")
    p.add_argument("--json", action="store_true", help="print JSON")
    args = p.parse_args(argv)

    abi_path = Path(args.abi) if args.abi else Path(__file__).with_name("abi.json")
    try:
        reader = RegistryReader(args.rpc, args.registry, args.chain_id, abi_path)
    except VerifyError as e:
        result = {"status": "error", "message": str(e), "algorithm": fingerprint.ALGORITHM,
                  "version": fingerprint.VERSION, "assurance": "content-only",
                  "method": "scan" if args.scan else "id", "fingerprint": None,
                  "distance": None, "record": None, "earlier": None,
                  "checked": {"records_scanned": 0}}
        print(json.dumps(result, indent=2) if args.json else f"error: {e}")
        return 2

    result = verify_image(args.image, watermark_id=args.watermark_id, scan=args.scan,
                          reader=reader, max_records=args.max_records, algo=args.algo)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"status: {result['status']}")
        print(f"fingerprint: {result['fingerprint']}  ({result['algorithm']})")
        if result["distance"] is not None:
            print(f"distance: {result['distance']}")
        if result["record"]:
            r = result["record"]
            print(f"record: {r['watermark_id']}  signer {r['signer']}  block {r['block']}")
        print(f"note: {result['message']}")
        print("assurance: content only; this tool does not decode the hidden watermark")

    return {"verified": 0, "likely_match": 0}.get(result["status"], 2 if result["status"] == "error" else 1)


if __name__ == "__main__":
    sys.exit(main())
