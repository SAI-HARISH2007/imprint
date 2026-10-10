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
        uint64 blockNumber;  // block of registration, so the transaction can be found with a one-block log query
        bytes32 fingerprint; // 256-bit perceptual hash of the marked image
    }

    bytes32 public constant REGISTER_TYPEHASH =
        keccak256("Register(bytes32 watermarkId,bytes32 fingerprint)");

    /// @notice The largest fingerprint Hamming distance accepted as a duplicate dispute.
    ///         10 bits matches the service's T_DUP guard. Anyone may dispute; the chain
    ///         only checks the two records exist, are ordered, and are close enough.
    uint256 public constant DISPUTE_MAX_DISTANCE = 10;

    struct Dispute {
        bytes32 earlier;   // the record that was registered first
        bytes32 later;     // the record disputed as a look-alike
        uint16 distance;   // fingerprint Hamming distance at dispute time
        address by;        // who raised the dispute (a public good; gas only)
        uint64 timestamp;  // block.timestamp of the dispute
    }

    mapping(bytes32 => Record) private _records;
    bytes32[] private _ids; // every registered ID, in order, so anyone can enumerate the registry with plain calls

    mapping(bytes32 => bytes32) private _disputedBy;      // later id -> earlier id (0 means not disputed)
    mapping(bytes32 => Dispute) private _disputes;        // later id -> dispute details

    event Registered(
        bytes32 indexed watermarkId, address indexed signer, bytes32 fingerprint, uint64 timestamp
    );
    /// Emitted next to Registered for passkey registrations so verifiers can show the public key.
    event PasskeyUsed(address indexed signer, bytes32 qx, bytes32 qy);
    /// Emitted when a record is publicly disputed as a near-duplicate of an earlier one.
    event RecordDisputed(
        bytes32 indexed earlier, bytes32 indexed later, uint256 distance, address indexed by, uint64 timestamp
    );

    error ZeroId();
    error AlreadyRegistered(bytes32 watermarkId);
    error BadSignature();
    error UnknownRecord(bytes32 watermarkId);
    error NotEarlier(bytes32 earlier, bytes32 later);
    error AlreadyDisputed(bytes32 later);
    error NotSimilar(uint256 distance, uint256 maxDistance);

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

    // ---------------------------------------------------------------- disputes

    /// @notice Flag `laterId` as a near-duplicate of an `earlierId` registered before it.
    ///         Permissionless and non-destructive: it neither deletes nor edits either record,
    ///         it only records a public, queryable claim that they look alike. Many of these
    ///         can be raised against one record, but each later id can be disputed once, so a
    ///         single spammer cannot bury a record under repeated disputes. The contract does
    ///         not try to settle authorship; it makes the closeness visible to everyone.
    function disputeDuplicate(bytes32 earlierId, bytes32 laterId) external {
        Record memory e = _records[earlierId];
        Record memory l = _records[laterId];
        if (e.timestamp == 0) revert UnknownRecord(earlierId);
        if (l.timestamp == 0) revert UnknownRecord(laterId);
        if (earlierId == laterId) revert NotEarlier(earlierId, laterId);
        if (e.blockNumber >= l.blockNumber) revert NotEarlier(earlierId, laterId);
        if (_disputedBy[laterId] != bytes32(0)) revert AlreadyDisputed(laterId);

        uint256 d = hammingDistance(e.fingerprint, l.fingerprint);
        if (d > DISPUTE_MAX_DISTANCE) revert NotSimilar(d, DISPUTE_MAX_DISTANCE);

        _disputedBy[laterId] = earlierId;
        _disputes[laterId] = Dispute(earlierId, laterId, uint16(d), msg.sender, uint64(block.timestamp));
        emit RecordDisputed(earlierId, laterId, d, msg.sender, uint64(block.timestamp));
    }

    // ---------------------------------------------------------------- views

    /// @notice Hamming distance between two fingerprints (the 256-bit XOR popcount).
    function hammingDistance(bytes32 a, bytes32 b) public pure returns (uint256) {
        uint256 x = uint256(a ^ b);
        return uint256(_popcount64(uint64(x))) + uint256(_popcount64(uint64(x >> 64)))
            + uint256(_popcount64(uint64(x >> 128))) + uint256(_popcount64(uint64(x >> 192)));
    }

    function isDisputed(bytes32 watermarkId) external view returns (bool) {
        return _disputedBy[watermarkId] != bytes32(0);
    }

    function disputeOf(bytes32 watermarkId) external view returns (Dispute memory) {
        return _disputes[watermarkId];
    }

    function recordOf(bytes32 watermarkId) external view returns (Record memory) {
        return _records[watermarkId];
    }

    function exists(bytes32 watermarkId) external view returns (bool) {
        return _records[watermarkId].timestamp != 0;
    }

    /// @notice Number of registrations.
    function count() external view returns (uint256) {
        return _ids.length;
    }

    /// @notice A page of registrations in registration order. No indexer or event scan needed.
    function recordsPage(uint256 offset, uint256 limit)
        external
        view
        returns (bytes32[] memory ids, Record[] memory recs)
    {
        uint256 n = _ids.length;
        if (offset >= n) return (new bytes32[](0), new Record[](0));
        // Clamp without computing offset + limit, which would overflow for a huge limit.
        uint256 end = limit < n - offset ? offset + limit : n;
        ids = new bytes32[](end - offset);
        recs = new Record[](end - offset);
        for (uint256 i = offset; i < end; i++) {
            ids[i - offset] = _ids[i];
            recs[i - offset] = _records[_ids[i]];
        }
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

    /// @dev Population count of a 64-bit word (Hacker's Delight, SWAR). The shifts and the
    ///      final multiply rely on wrapping 64-bit arithmetic, so they run unchecked.
    function _popcount64(uint64 x) private pure returns (uint64) {
        unchecked {
            x = x - ((x >> 1) & 0x5555555555555555);
            x = (x & 0x3333333333333333) + ((x >> 2) & 0x3333333333333333);
            x = (x + (x >> 4)) & 0x0f0f0f0f0f0f0f0f;
            return (x * 0x0101010101010101) >> 56;
        }
    }

    function _store(bytes32 watermarkId, bytes32 fingerprint, address signer) private {
        if (watermarkId == bytes32(0)) revert ZeroId();
        if (_records[watermarkId].timestamp != 0) revert AlreadyRegistered(watermarkId);
        uint64 ts = uint64(block.timestamp);
        _records[watermarkId] = Record(signer, ts, uint64(block.number), fingerprint);
        _ids.push(watermarkId);
        emit Registered(watermarkId, signer, fingerprint, ts);
    }
}
