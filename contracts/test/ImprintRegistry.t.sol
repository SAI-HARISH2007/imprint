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
    bytes32 constant FP = keccak256("fingerprint-1");

    uint256 constant P256_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551;

    event Registered(bytes32 indexed watermarkId, address indexed signer, bytes32 fingerprint, uint64 timestamp);
    event PasskeyUsed(address indexed signer, bytes32 qx, bytes32 qy);

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

    function testFuzz_eachIdRegistersOnce(bytes32 id, bytes32 fp) public {
        vm.assume(id != bytes32(0));
        reg.registerSigned(id, fp, alice, _sign(alicePk, reg, id, fp));
        assertEq(reg.recordOf(id).fingerprint, fp);
        bytes memory sig = _sign(alicePk, reg, id, fp);
        vm.expectRevert(abi.encodeWithSelector(ImprintRegistry.AlreadyRegistered.selector, id));
        reg.registerSigned(id, fp, alice, sig);
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
