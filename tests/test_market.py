"""Market-side analysis: honeypot, high tax, rugged tokens and liquidity risk are flagged;
data that is unavailable is reported as not verified and never reads as safe."""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H

ns, c = H.load()
POSITIVE = ("NO RED FLAGS FOUND", "NO CONTRACT RED FLAGS")

# ------------------------------------------------------------------ EVM
def evm(gp=None, down=False, files=None):
    H.routes(H.sourcify(files or {"c.sol": H.src("function ok() public { }")}), gp_entry=gp, gp_down=down)
    c.scans.clear(); c.history.clear(); c.scan_count = "0"; H.llm()
    c.scan_token_full(1, H.ADDR, H.TODAY)
    r = json.loads(c.get_scan(1, H.ADDR))
    return r, r["final"], {f["code"]: f["level"] for f in r["final"]["flags"]}, [n for n in r["final"]["notes"]]

G = H.GP_OK
r, fin, fl, _ = evm(G)
assert fin["headline"] == "NO CONTRACT RED FLAGS" and fl == {}                      # baseline: complete data, clean contract
r, fin, fl, _ = evm(dict(G, is_honeypot="1"))                                         # known honeypot
assert fin["headline"] == "DANGER" and fl["honeypot"] == "danger"
r, fin, fl, _ = evm(dict(G, is_honeypot="1", token_symbol="USDC", trust_list="1", holder_count="500000"))   # even a trusted-looking token
assert fin["headline"] == "DANGER"
for kw in [dict(buy_tax="0.25"), dict(sell_tax="0.4"), dict(buy_tax="0.06")]:        # high tax
    r, fin, fl, _ = evm(dict(G, **kw))
    assert fin["headline"] == "CAUTION" and fl["high_tax"] == "warn", (kw, fin["headline"])
r, fin, fl, _ = evm(dict(G, buy_tax="0.05", sell_tax="0.05"))
assert "high_tax" not in fl
r, fin, fl, _ = evm(dict(G, slippage_modifiable="1"))                                 # tax can be changed by the owner
assert fl["tax_modifiable"] == "caution" and fin["headline"] == "CAUTION"
# unknown is not safe
r, fin, fl, _ = evm(dict(G, is_honeypot=None))
assert fl["honeypot_unverified"] == "caution" and fin["headline"] == "CAUTION"
r, fin, fl, _ = evm(dict(G, buy_tax=None))
assert fl["tax_unverified"] == "caution" and fin["headline"] == "CAUTION"
# liquidity risk
r, fin, fl, _ = evm(dict(G, is_in_dex="0"))
assert fl["no_dex_pool"] == "caution" and fin["headline"] == "CAUTION"
r, fin, fl, _ = evm(dict(G, holders=[{"address": "0x" + "b" * 40, "percent": "0.7", "is_contract": 0, "is_locked": 0, "tag": ""}]))
assert fl["concentration"] == "warn" and fin["headline"] == "CAUTION"
# data source down
for kw in [dict(down=True), dict(gp={})]:
    r, fin, fl, notes = evm(**kw)
    assert r["market"]["available"] is False and fl["no_market_data"] == "caution", kw
    assert fin["headline"] not in POSITIVE and fin["headline"] == "CAUTION", fin["headline"]
    assert "not verified" in fin["flags"][0]["text"]
# a dangerous contract with market data down is still DANGER
r, fin, fl, _ = evm(down=True, files={"c.sol": H.src("function mint(address a, uint256 n) public { }")})
c.scans.clear(); H.routes(H.sourcify({"c.sol": H.src("function mint(address a, uint256 n) public { }")}), gp_down=True)
H.llm(unrestricted_mint=("YES", "mint")); c.scan_token_full(1, H.ADDR, H.TODAY)
assert json.loads(c.get_scan(1, H.ADDR))["final"]["headline"] == "DANGER"

# ------------------------------------------------------------------ Solana
MINT = "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"
def sol(rc=None, jup=None, dex=None, cg=None):
    base_struct = {"holders_bucket": "2000-9999", "concentration": "LOW", "top10_bucket": "10-20", "creator_bucket": "0-10",
                   "insider_bucket": "0-10", "insider_networks": "0", "lp_locked_bucket": "50-90", "lp_coverage_bucket": "90+",
                   "market_types": ["raydium"]}
    base = {"ok": True, "rugged": False,
            "authorities": {"mint_authority_present": False, "freeze_authority_present": False, "metadata_mutable": False},
            "structure": base_struct, "profile": {"launchpad": None, "detected_date": "2026-01-01"}}
    if rc is not None and rc.get("ok") is False:
        base = rc
    elif rc:
        for k, v in rc.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                base[k] = dict(base[k], **v)
            else:
                base[k] = v
    mk = {"rc": base, "jup": jup if jup is not None else {"ok": False}, "dex": dex if dex is not None else {"ok": False}}
    res = ns["fx_solana_final"](MINT, H.TODAY, mk, cg if cg is not None else {"ok": False})
    return res, res["final"], {f["code"]: f["level"] for f in res["final"]["flags"]}

res, fin, fl = sol()
assert res["verdict"] == "CLEAR" and fin["headline"] == "NO CONTRACT RED FLAGS" and fl == {}
res, fin, fl = sol({"rugged": True})                                                  # rugged
assert res["verdict"] == "DANGER" and fin["headline"] == "DANGER" and fl["rugged"] == "danger"
res, fin, fl = sol({"authorities": {"mint_authority_present": True, "freeze_authority_present": True}})
assert fin["headline"] == "DANGER" or fin["headline"] == "CENTRALIZED CONTROL" or fin["headline"] == "CAUTION"
assert res["verdict"] == "CENTRALIZED" and fl["mint_authority"] == "warn" and fl["freeze_authority"] == "warn"
res, fin, fl = sol({"authorities": {"mint_authority_present": True}})
assert res["verdict"] == "CAUTION" and fin["headline"] == "CAUTION"
res, fin, fl = sol({"structure": {"concentration": "HIGH", "top10_bucket": "70-80"}})
assert fl["concentration"] == "warn" and fin["headline"] == "CAUTION"
res, fin, fl = sol({"structure": {"insider_bucket": "40-50"}})
assert fl["insiders"] == "warn" and fin["headline"] == "CAUTION"
# liquidity risk
res, fin, fl = sol({"structure": {"lp_locked_bucket": "0-10", "lp_coverage_bucket": "90+"}})
assert fl["liquidity_unlocked"] == "caution" and fin["headline"] == "CAUTION"
res, fin, fl = sol({"structure": {"market_types": []}})
assert fl["no_pool"] == "caution" and fin["headline"] == "CAUTION"
res, fin, fl = sol({"structure": {"lp_locked_bucket": "unknown", "lp_coverage_bucket": "unknown"}})
assert any("lock status could not be verified" in n for n in fin["notes"]) and fin["headline"] not in ("DANGER",)
res, fin, fl = sol({"structure": {"holders_bucket": "unknown"}})
assert any("Holder count could not be verified" in n for n in fin["notes"])
# data source down: never positive
res, fin, fl = sol({"ok": False, "reason": "http"})
assert res["verdict"] == "INCONCLUSIVE" and fin["headline"] == "INCONCLUSIVE" and fl["no_market_data"] == "caution", fin
assert res["market"]["available"] is False
res, fin, fl = sol(jup={"ok": False, "reason": "http", "status": 503}, dex={"ok": False, "reason": "http", "status": 429})
assert res["market"]["dex_paid"] is False and fin["headline"] not in ("DANGER",) and any("Jupiter" in n for n in fin["notes"])        # secondary sources down: reported, no crash
res, fin, fl = sol(dex={"ok": True, "dex_paid": True})
assert res["market"]["dex_paid"] is True and fin["headline"] == "NO CONTRACT RED FLAGS"  # neutral label

# mutated inputs must never crash
for junk in [None, "x", 5, [], {"rc": 7}, {"rc": None, "jup": "z", "dex": []}]:
    out = ns["fx_solana_final"](MINT, H.TODAY, junk if isinstance(junk, dict) else {}, junk)
    assert out["final"]["headline"] in ("INCONCLUSIVE", "CAUTION"), out["final"]["headline"]
print("market OK")
