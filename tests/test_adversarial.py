"""Adversarial inputs: malformed reviewer output, conflicting validators, incomplete or missing source."""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H

ns, c = H.load()

def fresh():
    c.scans.clear(); c.history.clear(); c.scan_count = "0"

def scan_raw(files, raw):
    H.routes(H.sourcify(files)); fresh()
    H.llm(); H.LLM["raw"] = raw
    c.scan_token(1, H.ADDR)
    return json.loads(c.get_scan(1, H.ADDR))

FILES = {"c.sol": H.src("function ok() public { }")}
GOOD = {k: {"answer": "NO", "function": "", "reason": "r"} for k in H.CATS}

# ---- malformed model responses: never CLEAR, always flagged
for raw in ["not json at all", "", "[]", "null", "42", '{"unrestricted_mint": "YES"}', "{" * 500,
            json.dumps({k: {"answer": "MAYBE"} for k in H.CATS}),
            json.dumps({k: GOOD[k] for k in H.CATS[:3]}),               # categories missing
            "I think this token looks safe!"]:
    r = scan_raw(FILES, raw)
    assert r["verdict"] == "INCONCLUSIVE", (raw[:30], r["verdict"])
    assert r["llm_parse_ok"] is False and "llm_parse" in r["incomplete"], raw[:30]
r = scan_raw(FILES, "```json\n" + json.dumps(GOOD) + "\n```")        # fenced but valid JSON is fine
assert r["verdict"] == "CLEAR" and r["llm_parse_ok"] is True
# a real finding survives a half-broken answer
half = dict(GOOD); half.pop("pause_transfers"); half["unrestricted_mint"] = {"answer": "YES", "function": "mint", "reason": "r"}
r = scan_raw({"c.sol": H.src("function mint(address a, uint256 n) public onlyOwner { }")}, json.dumps(half))
assert r["verdict"] == "CAUTION" and "llm_parse" in r["incomplete"] and "unclear:pause_transfers" in r["incomplete"], r

# ---- conflicting validator judgments: no consensus means nothing is stored
H.routes(H.sourcify(FILES)); fresh(); H.llm()
H.LLM["raise"] = Exception("validators could not agree")
try:
    c.scan_token(1, H.ADDR); raised = False
except Exception:
    raised = True
assert raised and c.scans == {} and c.history == {} and c.scan_count == "0"
H.LLM["raise"] = None
# CoinGecko is optional: one side failing is tolerated, two successful but different answers are not
tol = ns["fx_cg_tolerant_ok"]
A = json.dumps({"ok": True, "rank": "top100"}); B = json.dumps({"ok": True, "rank": "below2000"}); F = json.dumps({"ok": False})
assert tol(A, A) and tol(A, F) and tol(F, A) and not tol(A, B) and not tol(A, "garbage")

# ---- incomplete or missing source
def scan_with(resp=None, raw=None, proxy=False):
    H.routes(H.sourcify({}) if resp is None and raw is None else resp, sourcify_raw=raw); fresh(); H.llm()
    c.scan_token(1, H.ADDR)
    return json.loads(c.get_scan(1, H.ADDR))
r = scan_with(H.sourcify({}))
assert r["verdict"] == "UNVERIFIED" and r["verified"] is False
r = scan_with(raw=H.R(b"<html>blocked</html>", 403))                  # Sourcify unreachable is not "unverified"
assert r["verdict"] == "INCONCLUSIVE" and r["incomplete"] == ["source_lookup_failed"], r
r = scan_with(raw=H.R([1, 2, 3]))
assert r["verdict"] == "INCONCLUSIVE"
r = scan_with({"sources": {}, "proxyResolution": {"isProxy": True, "implementations": [{"address": "0x" + "9" * 40}]}})
assert r["verdict"] == "UNVERIFIED" and r["is_proxy"] is True                          # unreadable proxy implementation
# unverified source with another source saying open source: honest wording, still not safe
H.routes(H.sourcify({})); fresh(); H.llm()
c.scan_token_full(1, H.ADDR, H.TODAY)
r = json.loads(c.get_scan(1, H.ADDR))
assert r["final"]["headline"] == "CODE NOT AVAILABLE TO ANALYZER", r["final"]
H.routes(H.sourcify({}), gp_entry=dict(H.GP_OK, is_open_source="0")); fresh()
c.scan_token_full(1, H.ADDR, H.TODAY)
assert json.loads(c.get_scan(1, H.ADDR))["final"]["headline"] == "UNVERIFIED CONTRACT"

# ---- truncated code never reads as clean
many = "\n".join("function burn%d(uint256 a) public { %s }" % (i, "a = a + 1; " * 80) for i in range(30))
r = scan_raw({"c.sol": H.src(many)}, json.dumps(GOOD))
assert r["review"]["snippets_truncated"] is True or r["review"]["map_truncated"] is True, r["review"]
assert r["verdict"] == "INCONCLUSIVE" and any(x.endswith("truncated") for x in r["incomplete"]), r["verdict"]

# ---- multi-contract bundles
files = {"c%d.sol" % i: H.src("function mint(address a, uint256 n) public { }", name="C%d" % i) for i in range(40)}
r = scan_raw(files, json.dumps(dict(GOOD, unrestricted_mint={"answer": "YES", "function": "mint", "reason": "r"})))
assert r["verdict"] == "INCONCLUSIVE" and "bundle_wide" in r["incomplete"], r["verdict"]
H.routes(H.sourcify(files)); fresh(); H.llm(unrestricted_mint=("YES", "mint"))
c.scan_token_full(10, H.ADDR, H.TODAY)
r = json.loads(c.get_scan(10, H.ADDR))
assert r["final"]["headline"] == "INCONCLUSIVE" and any("multi-contract" in n for n in r["final"]["notes"]), r["final"]

# ---- input validation
for bad in [(5, H.ADDR, H.TODAY), (1, "0x123", H.TODAY), (1, H.ADDR, "2020-01-01"), (1, H.ADDR, "garbage"), (True, H.ADDR, H.TODAY)]:
    fresh()
    try:
        c.scan_token_full(*bad); ok = True
    except Exception:
        ok = False
    assert not ok and c.scans == {}, bad
print("adversarial OK")
