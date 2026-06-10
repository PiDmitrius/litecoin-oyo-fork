#!/usr/bin/env python3
# Copyright (c) 2026 OYO
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test OYO RPC extensions: oyo-version, oyo-backupwallet, oyo-restorewallet, oyo-deletewallet."""

from test_framework.authproxy import AuthServiceProxy
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import assert_equal, assert_raises_rpc_error


def oyo_rpc(rpc_proxy, method, *args):
    """Call an RPC method with dashes in name (Python attrs can't have dashes)."""
    proxy = AuthServiceProxy(rpc_proxy._AuthServiceProxy__service_url,
                             method,
                             connection=rpc_proxy._AuthServiceProxy__conn)
    return proxy(*args)


class OyoRPCTest(BitcoinTestFramework):
    def set_test_params(self):
        self.num_nodes = 2
        self.extra_args = [[], ["-nooyo"]]

    def run_test(self):
        node = self.nodes[0]
        vanilla_node = self.nodes[1]

        self.log.info("Test -nooyo hides OYO RPC extensions")
        help_text = vanilla_node.help()
        for method in ["oyo-version", "oyo-backupwallet", "oyo-restorewallet", "oyo-deletewallet", "oyo-send"]:
            assert method not in help_text
            assert_raises_rpc_error(-32601, "Method not found", oyo_rpc, vanilla_node.rpc, method)

        self.log.info("Test -nooyo keeps regular wallet RPCs usable")
        vanilla_node.createwallet("nooyo-basic")
        nooyo_wallet = vanilla_node.get_wallet_rpc("nooyo-basic")
        mining_addr = nooyo_wallet.getnewaddress()
        vanilla_node.generatetoaddress(101, mining_addr)
        assert nooyo_wallet.getbalance() > 0
        txid = nooyo_wallet.sendtoaddress(nooyo_wallet.getnewaddress(), 1)
        assert_equal(len(txid), 64)

        self.log.info("Test -nooyo keeps blank-wallet MWEB seed behavior")
        vanilla_node.createwallet(wallet_name="nooyo-blank", blank=True)
        blank_wallet = vanilla_node.get_wallet_rpc("nooyo-blank")
        blank_wallet.sethdseed()
        assert blank_wallet.getnewaddress(address_type="mweb").startswith("tmweb")

        self.log.info("Test oyo-version")
        result = oyo_rpc(node.rpc, "oyo-version")
        assert result["version"] >= 3
        assert "oyo-backupwallet" in result["features"]
        assert "oyo-restorewallet" in result["features"]
        assert "oyo-deletewallet" in result["features"]

        self.log.info("Test oyo-backupwallet + oyo-restorewallet roundtrip")
        # Create source wallet with some activity
        node.createwallet("oyo-test-src")
        src_wallet = node.get_wallet_rpc("oyo-test-src")
        addr = src_wallet.getnewaddress("test-label")
        node.generatetoaddress(10, addr)

        # Get source info before unload
        src_info = src_wallet.getwalletinfo()
        src_hdseedid = src_info["hdseedid"]
        src_txcount = src_info["txcount"]
        src_keypoolsize = src_info["keypoolsize"]
        self.log.info(f"  Source: hdseedid={src_hdseedid}, txcount={src_txcount}, keypool={src_keypoolsize}")

        # Unload source
        node.unloadwallet("oyo-test-src")

        # Backup
        backup = oyo_rpc(node.rpc, "oyo-backupwallet", "oyo-test-src")
        assert "data" in backup
        assert backup["size"] > 0
        self.log.info(f"  Backup size: {backup['size']} bytes")

        # Restore as new wallet
        restore = oyo_rpc(node.rpc, "oyo-restorewallet", "oyo-test-restored", backup["data"])
        assert_equal(restore["name"], "oyo-test-restored")
        assert_equal(restore["size"], backup["size"])

        # Load restored wallet and verify
        node.loadwallet("oyo-test-restored")
        restored_wallet = node.get_wallet_rpc("oyo-test-restored")
        restored_info = restored_wallet.getwalletinfo()

        assert_equal(restored_info["hdseedid"], src_hdseedid)
        assert_equal(restored_info["txcount"], src_txcount)
        self.log.info(f"  Restored: hdseedid={restored_info['hdseedid']}, txcount={restored_info['txcount']}")

        # Verify address is accessible
        addr_info = restored_wallet.getaddressinfo(addr)
        assert addr_info["ismine"], f"Address {addr} should be mine in restored wallet"

        # Cleanup
        node.unloadwallet("oyo-test-restored")

        self.log.info("Test oyo-deletewallet")
        # Delete restored wallet
        delete_result = oyo_rpc(node.rpc, "oyo-deletewallet", "oyo-test-restored")
        assert_equal(delete_result["deleted"], "oyo-test-restored")

        # Verify it's gone from listwalletdir
        wallet_dir = node.listwalletdir()
        wallet_names = [w["name"] for w in wallet_dir["wallets"]]
        assert "oyo-test-restored" not in wallet_names

        self.log.info("Test oyo-backupwallet fails on loaded wallet")
        node.loadwallet("oyo-test-src")
        try:
            oyo_rpc(node.rpc, "oyo-backupwallet", "oyo-test-src")
            assert False, "Should fail on loaded wallet"
        except Exception:
            pass

        self.log.info("Test oyo-restorewallet fails if wallet exists")
        node.unloadwallet("oyo-test-src")
        try:
            oyo_rpc(node.rpc, "oyo-restorewallet", "oyo-test-src", backup["data"])
            assert False, "Should fail if wallet already exists"
        except Exception:
            pass

        # Final cleanup
        node.loadwallet("oyo-test-src")
        node.unloadwallet("oyo-test-src")
        oyo_rpc(node.rpc, "oyo-deletewallet", "oyo-test-src")

        self.log.info("All OYO RPC tests passed!")


if __name__ == '__main__':
    OyoRPCTest().main()
