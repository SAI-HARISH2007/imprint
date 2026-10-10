// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";

/// A probe that answers "what would a similarity check at registration time cost?"
///
/// It stores fingerprints the way the real registry does (a storage array) and, on
/// demand, scans them with the same SWAR Hamming distance used by ImprintRegistry.
/// This measures the cost a mandatory on-chain duplicate check would add to every
/// registration, instead of guessing. It is a benchmark, not part of the registry.
contract SimilarityProbe {
    bytes32[] public fps;

    function seed(uint256 k) external {
        for (uint256 i; i < k; ++i) {
            fps.push(keccak256(abi.encodePacked("fp", i)));
        }
    }

    function hamming(bytes32 a, bytes32 b) public pure returns (uint256) {
        uint256 x = uint256(a ^ b);
        return _popcount64(uint64(x)) + _popcount64(uint64(x >> 64)) + _popcount64(uint64(x >> 128))
            + _popcount64(uint64(x >> 192));
    }

    /// Count stored fingerprints within `radius` bits of `q` — the shape a mandatory
    /// on-chain near-duplicate guard would take (it has to inspect the stored set).
    function scanWithin(bytes32 q, uint256 radius) external view returns (uint256 hits) {
        uint256 n = fps.length;
        for (uint256 i; i < n; ++i) {
            if (hamming(q, fps[i]) <= radius) ++hits;
        }
    }

    /// Same SWAR popcount as ImprintRegistry, so the measured cost matches the
    /// real check's arithmetic.
    function _popcount64(uint64 x) private pure returns (uint64) {
        unchecked {
            x = x - ((x >> 1) & 0x5555555555555555);
            x = (x & 0x3333333333333333) + ((x >> 2) & 0x3333333333333333);
            x = (x + (x >> 4)) & 0x0f0f0f0f0f0f0f0f;
            return (x * 0x0101010101010101) >> 56;
        }
    }
}

contract SimilarityCostTest is Test {
    function _scanGas(uint256 k, uint256 radius) internal returns (uint256) {
        SimilarityProbe probe = new SimilarityProbe();
        probe.seed(k);
        bytes32 q = keccak256("query-fingerprint");
        uint256 start = gasleft();
        probe.scanWithin(q, radius);
        return start - gasleft();
    }

    /// The point: cost is linear in the number of stored records, so a mandatory
    /// check is O(n) gas on every registration. Compare to a registration itself
    /// (~173k gas end to end, most of it fixed), and the numbers speak for themselves.
    function test_scan_gas_is_linear_in_records() public {
        uint256 g100 = _scanGas(100, 10);
        uint256 g1000 = _scanGas(1000, 10);
        uint256 g10000 = _scanGas(10_000, 10);

        emit log_named_uint("scan within 10 bits, 100 stored records (gas)", g100);
        emit log_named_uint("scan within 10 bits, 1000 stored records (gas)", g1000);
        emit log_named_uint("scan within 10 bits, 10000 stored records (gas)", g10000);

        assertGt(g1000, g100 * 5, "should grow roughly with n");
        assertLt(g1000, g100 * 20, "should not be super-linear");
        assertGt(g10000, g1000 * 5, "should grow roughly with n");
        assertLt(g10000, g1000 * 20, "should not be super-linear");
    }
}
