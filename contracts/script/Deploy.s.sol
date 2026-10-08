// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {ImprintRegistry} from "../src/ImprintRegistry.sol";

contract Deploy is Script {
    function run() external returns (ImprintRegistry reg) {
        vm.startBroadcast();
        reg = new ImprintRegistry();
        vm.stopBroadcast();
        console.log("ImprintRegistry:", address(reg));
    }
}
