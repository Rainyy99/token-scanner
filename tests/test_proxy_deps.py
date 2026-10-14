"""Complex proxies, inherited/library code and powers delegated to other contracts:
anything the analyzer cannot see blocks CLEAR, and never lowers a real finding."""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H

ns, c = H.load()
A = "0x" + "a" * 40
IMPL1, IMPL2, IMPL3, IMPL4, IMPL5 = ["0x" + str(i) * 40 for i in range(1, 6)]
CLEAN = H.src("function ok() public { }")
MINT_OPEN = H.src("function mint(address a, uint256 n) public { }")
MINT_GATED = H.src("function mint(address a, uint256 n) public onlyOwner { }")


def scan(by_addr, proxy_for=A, **llm):
    """by_addr: address -> sourcify response. Unknown addresses answer 404."""
    def fn(url):
        for addr, resp in by_addr.items():
            if addr.lower() in url.lower():
                return H.R(resp)
        return H.R({}, 404)
    H.routes(H.sourcify({}))
    H.ROUTES[0] = ("sourcify.dev", fn)
    c.scans.clear(); c.history.clear(); c.scan_count = "0"
    H.llm(**llm)
    c.scan_token(1, A)
    return json.loads(c.get_scan(1, A))


def proxy_resp(impls, files=None, ptype="EIP1967Proxy"):
    r = H.sourcify(files or {"Proxy.sol": H.src("function admin() public { }", name="Proxy")}, proxy=True)
    r["proxyResolution"] = {"isProxy": True, "proxyType": ptype, "implementations": [{"address": i} for i in impls]}
    return r


def gaps(r):
    return [x for x in r["incomplete"] if x.startswith("gap:")]


# plain contract, clean: still CLEAR (no regression)
r = scan({A: H.sourcify({"c.sol": CLEAN})})
assert r["verdict"] == "CLEAR" and r["incomplete"] == [], r

# a simple proxy with a clean implementation: upgrade authority is not visible -> not CLEAR
r = scan({A: proxy_resp([IMPL1]), IMPL1: H.sourcify({"c.sol": CLEAN})})
assert r["verdict"] == "INCONCLUSIVE" and "unclear:upgrade_without_timelock" in r["incomplete"], r
assert r["llm_findings"]["upgrade_without_timelock"]["adjusted"] is True

# proxy whose implementation cannot be resolved: only the shell was reviewed
r = scan({A: proxy_resp([])})
assert r["verdict"] == "INCONCLUSIVE" and "gap:proxy_implementation_unresolved" in gaps(r) and "gap:only_proxy_code_analyzed" in gaps(r), r

# implementation without verified source: nothing to review at all
r = scan({A: proxy_resp([IMPL1]), IMPL1: H.sourcify({})})
assert r["verdict"] == "UNVERIFIED", r

# several implementations: all are analyzed, a missing one is reported
r = scan({A: proxy_resp([IMPL1, IMPL2]), IMPL1: H.sourcify({"c.sol": CLEAN}), IMPL2: H.sourcify({})})
assert r["verdict"] == "INCONCLUSIVE" and "gap:implementation_not_verified" in gaps(r), r
r = scan({A: proxy_resp([IMPL1, IMPL2, IMPL3, IMPL4, IMPL5]), IMPL1: H.sourcify({"c.sol": CLEAN}),
          IMPL2: H.sourcify({"d.sol": CLEAN}), IMPL3: H.sourcify({"e.sol": CLEAN})})
assert "gap:many_implementations" in gaps(r) and r["verdict"] == "INCONCLUSIVE", r
r = scan({A: proxy_resp([IMPL1, IMPL2], ptype="Diamond"), IMPL1: H.sourcify({"c.sol": CLEAN}), IMPL2: H.sourcify({"d.sol": CLEAN})})
assert "gap:diamond_facets_can_change" in gaps(r), r

# a power hidden in the SECOND implementation is found
r = scan({A: proxy_resp([IMPL1, IMPL2]), IMPL1: H.sourcify({"c.sol": CLEAN}), IMPL2: H.sourcify({"d.sol": MINT_OPEN})},
         unrestricted_mint=("YES", "mint"))
assert r["verdict"] == "DANGER", r
# an upgrade function living in the proxy's own code is seen (it used to be ignored)
r = scan({A: proxy_resp([IMPL1], files={"Proxy.sol": H.src("function upgradeTo(address a) public { }", name="Proxy")}),
          IMPL1: H.sourcify({"c.sol": CLEAN})}, upgrade_without_timelock=("YES", "upgradeTo"))
assert r["verdict"] == "DANGER", r

# unvetted library code with risky functions blocks CLEAR; vendor code does not
r = scan({A: H.sourcify({"c.sol": CLEAN, "lib/custom/Minter.sol": MINT_OPEN})})
assert r["verdict"] == "INCONCLUSIVE" and "gap:library_risky_functions" in gaps(r), r
r = scan({A: H.sourcify({"c.sol": CLEAN, "@openzeppelin/contracts/Pausable.sol": H.src("function pause() public { }", name="P")})})
assert r["verdict"] == "CLEAR", r

# power delegated to another contract: the real mint sits outside the analyzed code
DELEGATED = H.src("function distribute(address a, uint256 n) public onlyOwner { controller.mint(a, n); }")
r = scan({A: H.sourcify({"c.sol": DELEGATED})})
assert r["verdict"] == "INCONCLUSIVE" and "gap:external_dependency_calls" in gaps(r), r
SELFCALL = H.src("function distribute(address a, uint256 n) public onlyOwner { super.mint(a, n); this.mint(a, n); }")
r = scan({A: H.sourcify({"c.sol": SELFCALL})})
assert "gap:external_dependency_calls" not in gaps(r), r

# gaps never lower a real finding
r = scan({A: proxy_resp([IMPL1, IMPL2]), IMPL1: H.sourcify({"c.sol": MINT_GATED}), IMPL2: H.sourcify({})},
         unrestricted_mint=("YES", "mint"))
assert r["verdict"] == "CAUTION" and gaps(r), r
r = scan({A: H.sourcify({"c.sol": MINT_OPEN, "lib/custom/Minter.sol": MINT_OPEN})}, unrestricted_mint=("YES", "mint"))
assert r["verdict"] == "DANGER", r

# the composed report never reads as clean for any gap
H.routes(H.sourcify({}))
H.ROUTES[0] = ("sourcify.dev", lambda u: H.R(proxy_resp([IMPL1]) if A.lower() in u.lower() else H.sourcify({"c.sol": CLEAN})))
c.scans.clear(); c.history.clear(); c.scan_count = "0"; H.llm()
c.scan_token_full(1, A, H.TODAY)
fin = json.loads(c.get_scan(1, A))["final"]
assert fin["headline"] not in ("NO RED FLAGS FOUND", "NO CONTRACT RED FLAGS"), fin["headline"]
print("proxy and dependency OK")
