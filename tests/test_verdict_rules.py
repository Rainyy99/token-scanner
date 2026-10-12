"""Verdict rules: CLEAR only when every check is settled on complete code; nothing is silently downgraded."""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H

ns, c = H.load()
compute = ns["_compute_verdict"]

def f(**ans):
    out = {k: {"answer": "NO", "function": "", "reason": ""} for k in H.CATS}
    for k, v in ans.items():
        out[k] = {"answer": v[0], "function": v[1] if len(v) > 1 else "", "reason": ""}
    return out

def rv(**kw):
    base = {"access": {k: "none" for k in H.CATS}, "project_files": 3, "map_truncated": False, "snippets_truncated": False}
    base.update(kw)
    return base

OPEN_MINT = rv(access=dict({k: "none" for k in H.CATS}, unrestricted_mint="open"))

# ---- unit rules
assert compute(f(), rv()) == "CLEAR"
assert compute(f(unrestricted_mint=("UNCLEAR",)), rv()) == "INCONCLUSIVE"            # the steward's case: one unresolved critical check
assert compute(f(upgrade_without_timelock=("UNCLEAR",)), rv()) == "INCONCLUSIVE"
assert compute(f(hidden_privileged_calls=("UNCLEAR",)), rv()) == "INCONCLUSIVE"
assert compute(f(pause_transfers=("UNCLEAR",)), rv()) == "INCONCLUSIVE"              # any unsettled check blocks CLEAR
assert compute({}, rv()) == "INCONCLUSIVE"                                            # missing answers are unsettled, not NO
assert compute(f(), rv(map_truncated=True)) == "INCONCLUSIVE"
assert compute(f(), rv(snippets_truncated=True)) == "INCONCLUSIVE"
assert compute(f(), None) == "CLEAR"
assert compute(f(unrestricted_mint=("YES", "mint")), OPEN_MINT) == "DANGER"
assert compute(f(unrestricted_mint=("YES", "mint")), rv()) == "CAUTION"
assert compute(f(unrestricted_mint=("YES", "mint"), pause_transfers=("YES", "pause")), rv()) == "CENTRALIZED"
big = dict(OPEN_MINT, project_files=56)
assert compute(f(unrestricted_mint=("YES", "mint")), big) == "INCONCLUSIVE"           # cannot attribute: never a calmer verdict
assert compute(f(unrestricted_mint=("YES", "mint")), dict(OPEN_MINT, project_files=30)) == "DANGER"
assert compute(f(unrestricted_mint=("YES", "mint")), dict(OPEN_MINT, project_files=31)) == "INCONCLUSIVE"

# ---- end to end through the contract
def scan(files, **llm_answers):
    H.routes(H.sourcify(files))
    H.llm(**llm_answers)
    c.scans.clear(); c.history.clear(); c.scan_count = "0"
    c.scan_token(1, H.ADDR)
    return json.loads(c.get_scan(1, H.ADDR))

OPEN = "function mint(address to, uint256 a) public { }"
GATED = "function mint(address to, uint256 a) public onlyOwner { }"

r = scan({"c.sol": H.src(OPEN)}, unrestricted_mint=("YES", "mint"))
assert r["verdict"] == "DANGER", r["verdict"]
r = scan({"c.sol": H.src(OPEN)})                                  # reviewer says NO, code has an open mint
assert r["verdict"] == "INCONCLUSIVE" and r["llm_findings"]["unrestricted_mint"]["answer"] == "UNCLEAR" and r["llm_findings"]["unrestricted_mint"]["adjusted"] is True, r
r = scan({"c.sol": H.src(GATED)})                                 # reviewer says NO, code has a privileged mint
assert r["verdict"] == "CAUTION" and r["llm_findings"]["unrestricted_mint"]["answer"] == "YES", r["verdict"]
r = scan({"c.sol": H.src("function blacklist(address a) public { }")}, blacklist_or_freeze=("YES", "blacklist"))
assert r["verdict"] == "DANGER"
r = scan({"c.sol": H.src("function blacklist(address a) public onlyOwner { }")})
assert r["verdict"] == "CAUTION" and r["llm_findings"]["blacklist_or_freeze"]["answer"] == "YES"
r = scan({"c.sol": H.src("function pause() public onlyOwner { }")})
assert r["verdict"] == "CAUTION" and r["llm_findings"]["pause_transfers"]["answer"] == "YES"
r = scan({"c.sol": H.src("function upgradeTo(address i) public onlyOwner { }")})   # reviewer NO, upgrade function exists
assert r["verdict"] == "INCONCLUSIVE" and "unclear:upgrade_without_timelock" in r["incomplete"], r
r = scan({"c.sol": H.src("function upgradeTo(address i) public onlyOwner { }")}, upgrade_without_timelock=("YES", "upgradeTo"))
assert r["verdict"] == "CAUTION"
r = scan({"c.sol": H.src("function run(address t, bytes memory d) public onlyOwner { t.delegatecall(d); }")})
assert r["verdict"] == "INCONCLUSIVE" and r["llm_findings"]["hidden_privileged_calls"]["answer"] == "UNCLEAR", r
r = scan({"c.sol": H.src("function ok() public { }")})
assert r["verdict"] == "CLEAR" and r["incomplete"] == [], r
print("verdict rules OK")
