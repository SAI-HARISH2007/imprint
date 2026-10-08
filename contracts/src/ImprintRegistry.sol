// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {WebAuthn} from "@openzeppelin/contracts/utils/cryptography/WebAuthn.sol";

/// @title ImprintRegistry
/// @notice A public, append-only record of "this watermark ID and this image fingerprint were
///         registered by this signer at this block time". First registration of an ID wins.
///
/// A registration always carries a signature, so nobody can claim an ID in someone else's name,
/// and anyone (for example a relayer paying gas) can submit it. Two signature types are accepted:
///   - a passkey (WebAuthn, P-256), verified through Monad's P-256 precompile at 0x0100
///   - an ordinary Ethereum key (EIP-712), for developers and as a fallback
///
/// The contract does not judge whether two images look alike. That check lives in the verifier,
/// which reads these records and flags any record that has a near-identical earlier one.
/// There is no owner, no upgrade path, no fee and no pause.
contract ImprintRegistry is EIP712 {
    struct Record {
        address signer;      // Ethereum address, or an ID derived from the passkey public key
        uint64 timestamp;    // block.timestamp at registration
        bytes32 fingerprint; // 256-bit perceptual hash of the marked image
    }

    bytes32 public constant REGISTER_TYPEHASH =
        keccak256("Register(bytes32 watermarkId,bytes32 fingerprint)");

    mapping(bytes32 => Record) private _records;

    event Registered(
        bytes32 indexed watermarkId, address indexed signer, bytes32 fingerprint, uint64 timestamp
    );
    /// Emitted next to Registered for passkey registrations so verifiers can show the public key.
    event PasskeyUsed(address indexed signer, bytes32 qx, bytes32 qy);

    error ZeroId();
    error AlreadyRegistered(bytes32 watermarkId);
    error BadSignature();

    constructor() EIP712("ImprintRegistry", "1") {}

    // ---------------------------------------------------------------- registration

    /// @notice Register with an EIP-712 signature from `signer` over (watermarkId, fingerprint).
    function registerSigned(bytes32 watermarkId, bytes32 fingerprint, address signer, bytes calldata signature)
        external
    {
        (address recovered, ECDSA.RecoverError err,) =
            ECDSA.tryRecoverCalldata(challengeFor(watermarkId, fingerprint), signature);
        if (err != ECDSA.RecoverError.NoError || recovered != signer || signer == address(0)) {
            revert BadSignature();
        }
        _store(watermarkId, fingerprint, signer);
    }

    /// @notice Register with a passkey assertion. The browser must have been asked to sign
    ///         `challengeFor(watermarkId, fingerprint)` as the WebAuthn challenge.
    function registerPasskey(
        bytes32 watermarkId,
        bytes32 fingerprint,
        WebAuthn.WebAuthnAuth calldata auth,
        bytes32 qx,
        bytes32 qy
    ) external {
        bytes memory challenge = abi.encodePacked(challengeFor(watermarkId, fingerprint));
        if (!WebAuthn.verify(challenge, auth, qx, qy)) revert BadSignature();
        address signer = passkeySigner(qx, qy);
        _store(watermarkId, fingerprint, signer);
        emit PasskeyUsed(signer, qx, qy);
    }

    // ---------------------------------------------------------------- views

    function recordOf(bytes32 watermarkId) external view returns (Record memory) {
        return _records[watermarkId];
    }

    function exists(bytes32 watermarkId) external view returns (bool) {
        return _records[watermarkId].timestamp != 0;
    }

    /// @notice The 32-byte value a signer must sign (EIP-712 digest, bound to this chain and contract).
    function challengeFor(bytes32 watermarkId, bytes32 fingerprint) public view returns (bytes32) {
        return _hashTypedDataV4(keccak256(abi.encode(REGISTER_TYPEHASH, watermarkId, fingerprint)));
    }

    /// @notice The signer ID recorded for a passkey public key.
    function passkeySigner(bytes32 qx, bytes32 qy) public pure returns (address) {
        return address(uint160(uint256(keccak256(abi.encode(qx, qy)))));
    }

    // ---------------------------------------------------------------- internals

    function _store(bytes32 watermarkId, bytes32 fingerprint, address signer) private {
        if (watermarkId == bytes32(0)) revert ZeroId();
        if (_records[watermarkId].timestamp != 0) revert AlreadyRegistered(watermarkId);
        uint64 ts = uint64(block.timestamp);
        _records[watermarkId] = Record(signer, ts, fingerprint);
        emit Registered(watermarkId, signer, fingerprint, ts);
    }
}
