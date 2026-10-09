// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {Base64} from "@openzeppelin/contracts/utils/Base64.sol";
import {WebAuthn} from "@openzeppelin/contracts/utils/cryptography/WebAuthn.sol";
import {ImprintRegistry} from "../src/ImprintRegistry.sol";

contract ImprintRegistryTest is Test {
    ImprintRegistry reg;

    address alice;
    uint256 alicePk;
    address bob;
    uint256 bobPk;

    bytes32 constant ID = bytes32(uint256(0xA11CE));
    bytes32 constant ID2 = bytes32(uint256(0xB0B));
    bytes32 constant FP = keccak256("fingerprint-1");

    uint256 constant P256_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551;

    event Registered(bytes32 indexed watermarkId, address indexed signer, bytes32 fingerprint, uint64 timestamp);
    event PasskeyUsed(address indexed signer, bytes32 qx, bytes32 qy);
    event RecordDisputed(
        bytes32 indexed earlier, bytes32 indexed later, uint256 distance, address indexed by, uint64 timestamp
    );

    function setUp() public {
        reg = new ImprintRegistry();
        (alice, alicePk) = makeAddrAndKey("alice");
        (bob, bobPk) = makeAddrAndKey("bob");
        vm.warp(1_800_000_000);
    }

    // ---------------------------------------------------------------- helpers

    function _sign(uint256 pk, ImprintRegistry r, bytes32 id, bytes32 fp) internal view returns (bytes memory) {
        (uint8 v, bytes32 rr, bytes32 ss) = vm.sign(pk, r.challengeFor(id, fp));
        return abi.encodePacked(rr, ss, v);
    }

    function _assertion(uint256 pk, bytes32 challenge, bytes1 flags)
        internal
        view
        returns (WebAuthn.WebAuthnAuth memory auth)
    {
        string memory prefix = '{"type":"webauthn.get",';
        string memory json = string.concat(
            prefix,
            '"challenge":"',
            Base64.encodeURL(abi.encodePacked(challenge)),
            '","origin":"https://imprint.test","crossOrigin":false}'
        );
        bytes memory authData = abi.encodePacked(keccak256("imprint.test"), flags, bytes4(0));
        bytes32 digest = sha256(abi.encodePacked(authData, sha256(bytes(json))));
        (bytes32 r, bytes32 s) = vm.signP256(pk, digest);
        if (uint256(s) > P256_N / 2) s = bytes32(P256_N - uint256(s));
        auth = WebAuthn.WebAuthnAuth({
            r: r,
            s: s,
            challengeIndex: bytes(prefix).length,
            typeIndex: 1,
            authenticatorData: authData,
            clientDataJSON: json
        });
    }

    // ---------------------------------------------------------------- Ethereum-key path

    function test_registerSigned_storesRecordAndEmits() public {
        bytes memory sig = _sign(alicePk, reg, ID, FP);
        vm.expectEmit(true, true, false, true);
        emit Registered(ID, alice, FP, uint64(block.timestamp));
        reg.registerSigned(ID, FP, alice, sig);

        ImprintRegistry.Record memory r = reg.recordOf(ID);
        assertEq(r.signer, alice);
        assertEq(r.fingerprint, FP);
        assertEq(r.timestamp, block.timestamp);
        assertEq(r.blockNumber, block.number);
        assertTrue(reg.exists(ID));
    }

    function test_anyoneCanRelayASignedRegistration() public {
        bytes memory sig = _sign(alicePk, reg, ID, FP);
        vm.prank(address(0xBEEF));
        reg.registerSigned(ID, FP, alice, sig);
        assertEq(reg.recordOf(ID).signer, alice);
    }

    function test_duplicateIdReverts() public {
        reg.registerSigned(ID, FP, alice, _sign(alicePk, reg, ID, FP));
        bytes32 fp2 = keccak256("other");
        bytes memory sig2 = _sign(bobPk, reg, ID, fp2);
        vm.expectRevert(abi.encodeWithSelector(ImprintRegistry.AlreadyRegistered.selector, ID));
        reg.registerSigned(ID, fp2, bob, sig2);
        // the original record is untouched
        assertEq(reg.recordOf(ID).signer, alice);
    }

    function test_cannotClaimIdInSomeoneElsesName() public {
        bytes memory bobSig = _sign(bobPk, reg, ID, FP);
        vm.expectRevert(ImprintRegistry.BadSignature.selector);
        reg.registerSigned(ID, FP, alice, bobSig); // claims alice signed it
    }

    function test_signatureDoesNotCoverADifferentFingerprint() public {
        bytes memory sig = _sign(alicePk, reg, ID, FP);
        vm.expectRevert(ImprintRegistry.BadSignature.selector);
        reg.registerSigned(ID, keccak256("tampered"), alice, sig);
    }

    function test_signatureDoesNotCoverADifferentId() public {
        bytes memory sig = _sign(alicePk, reg, ID, FP);
        vm.expectRevert(ImprintRegistry.BadSignature.selector);
        reg.registerSigned(bytes32(uint256(0xB0B)), FP, alice, sig);
    }

    function test_signatureIsBoundToThisContract() public {
        ImprintRegistry other = new ImprintRegistry();
        bytes memory sigForOther = _sign(alicePk, other, ID, FP);
        vm.expectRevert(ImprintRegistry.BadSignature.selector);
        reg.registerSigned(ID, FP, alice, sigForOther);
    }

    function test_signatureIsBoundToThisChain() public {
        bytes memory sig = _sign(alicePk, reg, ID, FP);
        vm.chainId(block.chainid + 1);
        vm.expectRevert(ImprintRegistry.BadSignature.selector);
        reg.registerSigned(ID, FP, alice, sig);
    }

    function test_zeroIdReverts() public {
        bytes memory sig = _sign(alicePk, reg, bytes32(0), FP);
        vm.expectRevert(ImprintRegistry.ZeroId.selector);
        reg.registerSigned(bytes32(0), FP, alice, sig);
    }

    function test_zeroAddressSignerReverts() public {
        vm.expectRevert(ImprintRegistry.BadSignature.selector);
        reg.registerSigned(ID, FP, address(0), new bytes(65));
    }

    function test_garbageSignatureReverts() public {
        vm.expectRevert(ImprintRegistry.BadSignature.selector);
        reg.registerSigned(ID, FP, alice, hex"1234");
    }

    function test_unregisteredIdReadsEmpty() public view {
        assertFalse(reg.exists(ID));
        ImprintRegistry.Record memory r = reg.recordOf(ID);
        assertEq(r.timestamp, 0);
        assertEq(r.signer, address(0));
    }

    function test_enumerateRegistryWithPlainCalls() public {
        assertEq(reg.count(), 0);
        for (uint256 i = 1; i <= 5; i++) {
            bytes32 id = bytes32(i);
            bytes32 fp = keccak256(abi.encode(i));
            reg.registerSigned(id, fp, alice, _sign(alicePk, reg, id, fp));
            vm.roll(block.number + 1);
        }
        assertEq(reg.count(), 5);

        (bytes32[] memory ids, ImprintRegistry.Record[] memory recs) = reg.recordsPage(1, 3);
        assertEq(ids.length, 3);
        assertEq(ids[0], bytes32(uint256(2)));
        assertEq(ids[2], bytes32(uint256(4)));
        assertEq(recs[0].fingerprint, keccak256(abi.encode(uint256(2))));
        assertEq(recs[0].signer, alice);
        assertEq(recs[1].blockNumber, recs[0].blockNumber + 1);

        // a page that runs past the end is clipped, and an offset past the end is empty
        (ids,) = reg.recordsPage(3, 100);
        assertEq(ids.length, 2);
        (ids, recs) = reg.recordsPage(5, 10);
        assertEq(ids.length, 0);
        assertEq(recs.length, 0);
    }

    function test_recordsPageClampsHugeLimitsAndZero() public {
        for (uint256 i = 1; i <= 3; i++) {
            bytes32 id = bytes32(i);
            bytes32 fp = keccak256(abi.encode(i));
            reg.registerSigned(id, fp, alice, _sign(alicePk, reg, id, fp));
        }

        // a limit that would overflow offset + limit must clip, not panic
        (bytes32[] memory ids, ImprintRegistry.Record[] memory recs) =
            reg.recordsPage(1, type(uint256).max);
        assertEq(ids.length, 2);
        assertEq(recs.length, 2);
        assertEq(ids[0], bytes32(uint256(2)));

        // limit 0 is an empty page
        (ids, recs) = reg.recordsPage(0, 0);
        assertEq(ids.length, 0);
        assertEq(recs.length, 0);

        // offset == count is empty
        (ids, recs) = reg.recordsPage(3, 10);
        assertEq(ids.length, 0);
        assertEq(recs.length, 0);

        // an absurd offset is empty, never a panic
        (ids, recs) = reg.recordsPage(type(uint256).max, 10);
        assertEq(ids.length, 0);
        assertEq(recs.length, 0);
    }

    function test_failedRegistrationDoesNotChangeCount() public {
        reg.registerSigned(ID, FP, alice, _sign(alicePk, reg, ID, FP));
        bytes memory sig = _sign(bobPk, reg, ID, FP);
        vm.expectRevert(abi.encodeWithSelector(ImprintRegistry.AlreadyRegistered.selector, ID));
        reg.registerSigned(ID, FP, bob, sig);
        assertEq(reg.count(), 1);
    }

    function testFuzz_eachIdRegistersOnce(bytes32 id, bytes32 fp) public {
        vm.assume(id != bytes32(0));
        reg.registerSigned(id, fp, alice, _sign(alicePk, reg, id, fp));
        assertEq(reg.recordOf(id).fingerprint, fp);
        bytes memory sig = _sign(alicePk, reg, id, fp);
        vm.expectRevert(abi.encodeWithSelector(ImprintRegistry.AlreadyRegistered.selector, id));
        reg.registerSigned(id, fp, alice, sig);
    }

    // ---------------------------------------------------------------- disputes

    function _registerLater(bytes32 id, bytes32 fp, uint256 pk, address who) internal {
        vm.roll(block.number + 1);
        reg.registerSigned(id, fp, who, _sign(pk, reg, id, fp));
    }

    function test_hammingDistance() public view {
        assertEq(reg.hammingDistance(bytes32(0), bytes32(0)), 0);
        assertEq(reg.hammingDistance(bytes32(0), bytes32(type(uint256).max)), 256);
        assertEq(reg.hammingDistance(FP, bytes32(uint256(FP) ^ 1)), 1);
        assertEq(reg.hammingDistance(FP, bytes32(uint256(FP) ^ 0xFFFF)), 16);
    }

    function test_disputeDuplicate_flagsSimilarLaterRecord() public {
        bytes32 fpNear = bytes32(uint256(FP) ^ 3); // distance 2
        reg.registerSigned(ID, FP, alice, _sign(alicePk, reg, ID, FP));
        _registerLater(ID2, fpNear, bobPk, bob);

        assertFalse(reg.isDisputed(ID2));
        vm.expectEmit(true, true, true, true);
        emit RecordDisputed(ID, ID2, 2, address(0xDEAD), uint64(block.timestamp));
        vm.prank(address(0xDEAD));
        reg.disputeDuplicate(ID, ID2);

        assertTrue(reg.isDisputed(ID2));
        assertFalse(reg.isDisputed(ID)); // the earlier record is not flagged
        ImprintRegistry.Dispute memory d = reg.disputeOf(ID2);
        assertEq(d.earlier, ID);
        assertEq(d.later, ID2);
        assertEq(uint256(d.distance), 2);
        assertEq(d.by, address(0xDEAD));
        // non-destructive: both records are untouched
        assertEq(reg.recordOf(ID).signer, alice);
        assertEq(reg.recordOf(ID2).signer, bob);
        assertEq(reg.count(), 2);
    }

    function test_dispute_rejectsFarApart() public {
        reg.registerSigned(ID, FP, alice, _sign(alicePk, reg, ID, FP));
        bytes32 fpFar = bytes32(uint256(FP) ^ type(uint256).max); // distance 256
        _registerLater(ID2, fpFar, bobPk, bob);
        vm.expectRevert(abi.encodeWithSelector(ImprintRegistry.NotSimilar.selector, uint256(256), uint256(10)));
        reg.disputeDuplicate(ID, ID2);
        assertFalse(reg.isDisputed(ID2));
    }

    function test_dispute_rejectsUnknownRecord() public {
        reg.registerSigned(ID, FP, alice, _sign(alicePk, reg, ID, FP));
        vm.expectRevert(abi.encodeWithSelector(ImprintRegistry.UnknownRecord.selector, ID2));
        reg.disputeDuplicate(ID, ID2);
        vm.expectRevert(abi.encodeWithSelector(ImprintRegistry.UnknownRecord.selector, bytes32(uint256(0xC0FFEE))));
        reg.disputeDuplicate(ID, bytes32(uint256(0xC0FFEE)));
    }

    function test_dispute_rejectsNotEarlier() public {
        bytes32 fpNear = bytes32(uint256(FP) ^ 3);
        reg.registerSigned(ID, FP, alice, _sign(alicePk, reg, ID, FP));
        _registerLater(ID2, fpNear, bobPk, bob);
        // the later record cannot be named as the earlier one
        vm.expectRevert(abi.encodeWithSelector(ImprintRegistry.NotEarlier.selector, ID2, ID));
        reg.disputeDuplicate(ID2, ID);
        // a record cannot dispute itself
        vm.expectRevert(abi.encodeWithSelector(ImprintRegistry.NotEarlier.selector, ID, ID));
        reg.disputeDuplicate(ID, ID);
    }

    function test_dispute_isIdempotentPerLaterRecord() public {
        bytes32 fpNear = bytes32(uint256(FP) ^ 3);
        reg.registerSigned(ID, FP, alice, _sign(alicePk, reg, ID, FP));
        _registerLater(ID2, fpNear, bobPk, bob);
        reg.disputeDuplicate(ID, ID2);
        vm.expectRevert(abi.encodeWithSelector(ImprintRegistry.AlreadyDisputed.selector, ID2));
        reg.disputeDuplicate(ID, ID2);
    }

    // ---------------------------------------------------------------- passkey path

    function test_registerPasskey_storesRecordUnderPasskeySigner() public {
        uint256 pk = uint256(keccak256("passkey-1"));
        (uint256 x, uint256 y) = vm.publicKeyP256(pk);
        WebAuthn.WebAuthnAuth memory auth = _assertion(pk, reg.challengeFor(ID, FP), 0x05);

        address expected = reg.passkeySigner(bytes32(x), bytes32(y));
        vm.expectEmit(true, true, false, true);
        emit Registered(ID, expected, FP, uint64(block.timestamp));
        vm.expectEmit(true, false, false, true);
        emit PasskeyUsed(expected, bytes32(x), bytes32(y));
        reg.registerPasskey(ID, FP, auth, bytes32(x), bytes32(y));

        assertEq(reg.recordOf(ID).signer, expected);
    }

    function test_registerPasskey_wrongChallengeReverts() public {
        uint256 pk = uint256(keccak256("passkey-1"));
        (uint256 x, uint256 y) = vm.publicKeyP256(pk);
        // assertion was made for a different fingerprint
        WebAuthn.WebAuthnAuth memory auth = _assertion(pk, reg.challengeFor(ID, keccak256("other")), 0x05);
        vm.expectRevert(ImprintRegistry.BadSignature.selector);
        reg.registerPasskey(ID, FP, auth, bytes32(x), bytes32(y));
    }

    function test_registerPasskey_wrongKeyReverts() public {
        uint256 pk = uint256(keccak256("passkey-1"));
        (uint256 x2, uint256 y2) = vm.publicKeyP256(uint256(keccak256("passkey-2")));
        WebAuthn.WebAuthnAuth memory auth = _assertion(pk, reg.challengeFor(ID, FP), 0x05);
        vm.expectRevert(ImprintRegistry.BadSignature.selector);
        reg.registerPasskey(ID, FP, auth, bytes32(x2), bytes32(y2));
    }

    function test_registerPasskey_requiresUserVerification() public {
        uint256 pk = uint256(keccak256("passkey-1"));
        (uint256 x, uint256 y) = vm.publicKeyP256(pk);
        WebAuthn.WebAuthnAuth memory auth = _assertion(pk, reg.challengeFor(ID, FP), 0x01); // present, not verified
        vm.expectRevert(ImprintRegistry.BadSignature.selector);
        reg.registerPasskey(ID, FP, auth, bytes32(x), bytes32(y));
    }

    function test_registerPasskey_duplicateIdReverts() public {
        uint256 pk = uint256(keccak256("passkey-1"));
        (uint256 x, uint256 y) = vm.publicKeyP256(pk);
        reg.registerPasskey(ID, FP, _assertion(pk, reg.challengeFor(ID, FP), 0x05), bytes32(x), bytes32(y));

        uint256 pk2 = uint256(keccak256("passkey-2"));
        (uint256 x2, uint256 y2) = vm.publicKeyP256(pk2);
        WebAuthn.WebAuthnAuth memory auth2 = _assertion(pk2, reg.challengeFor(ID, FP), 0x05);
        vm.expectRevert(abi.encodeWithSelector(ImprintRegistry.AlreadyRegistered.selector, ID));
        reg.registerPasskey(ID, FP, auth2, bytes32(x2), bytes32(y2));
    }
}
