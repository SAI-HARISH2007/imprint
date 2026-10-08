"""A software stand-in for a passkey, for tests and scripts.

It builds the same WebAuthn assertion a browser would, signed with a P-256 key held in memory.
The contract cannot tell the difference, which is the point: it verifies the signature.
"""
import base64
import hashlib
import json

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

P256_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


class SoftPasskey:
    def __init__(self, rp_id: str = "imprint.test"):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.rp_id = rp_id
        nums = self.key.public_key().public_numbers()
        self.qx = "0x" + nums.x.to_bytes(32, "big").hex()
        self.qy = "0x" + nums.y.to_bytes(32, "big").hex()

    def assert_challenge(self, challenge_hex: str, flags: int = 0x05) -> dict:
        challenge = bytes.fromhex(challenge_hex.removeprefix("0x"))
        client = json.dumps(
            {"type": "webauthn.get", "challenge": _b64url(challenge),
             "origin": f"https://{self.rp_id}", "crossOrigin": False},
            separators=(",", ":"),
        )
        auth_data = hashlib.sha256(self.rp_id.encode()).digest() + bytes([flags]) + (1).to_bytes(4, "big")
        signed = auth_data + hashlib.sha256(client.encode()).digest()
        r, s = decode_dss_signature(self.key.sign(signed, ec.ECDSA(hashes.SHA256())))
        if s > P256_N // 2:
            s = P256_N - s
        return {
            "r": "0x" + r.to_bytes(32, "big").hex(),
            "s": "0x" + s.to_bytes(32, "big").hex(),
            "challengeIndex": client.index('"challenge":"'),
            "typeIndex": client.index('"type":"'),
            "authenticatorData": "0x" + auth_data.hex(),
            "clientDataJSON": client,
        }
