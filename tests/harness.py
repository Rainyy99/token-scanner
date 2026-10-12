"""Offline harness: runs the contract file with GenLayer, Sourcify, GoPlus and the LLM mocked.
Nothing here touches the network."""
import json, os, sys, types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACT = os.path.join(ROOT, "contracts", "token_security_scanner_v16.py")

ROUTES = []          # (url substring, factory(url) -> response)
LLM = {"raw": "{}", "raise": None}
VALIDATOR_LOG = []
HOOK = {"fake": None}
CATS = ["unrestricted_mint", "blacklist_or_freeze", "pause_transfers", "upgrade_without_timelock", "hidden_privileged_calls"]


def R(obj, status=200):
    body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
    return types.SimpleNamespace(status=status, body=body)


def get(url, **kw):
    for sub, fn in ROUTES:
        if sub in url:
            return fn(url)
    return types.SimpleNamespace(status=404, body=b"{}")


class Return:
    def __init__(self, c):
        self.calldata = c


def run_nondet(leader, validator):
    r = leader()
    fake = HOOK["fake"]
    VALIDATOR_LOG.append(validator(fake if fake is not None else Return(r)))
    HOOK["fake"] = None
    return r


def prompt_non_comparative(get_input, task, criteria):
    get_input()
    if LLM["raise"] is not None:
        raise LLM["raise"]
    return LLM["raw"]


class _TM:
    def __class_getitem__(cls, item):
        return dict


class _C:
    pass


def _d(f):
    return f


_gl = types.SimpleNamespace(
    Contract=_C, public=types.SimpleNamespace(write=_d, view=_d),
    nondet=types.SimpleNamespace(web=types.SimpleNamespace(get=get, request=get)),
    eq_principle=types.SimpleNamespace(strict_eq=lambda f: f(), prompt_non_comparative=prompt_non_comparative),
    vm=types.SimpleNamespace(run_nondet=run_nondet, Return=Return))
_m = types.ModuleType("genlayer")
_m.gl = _gl
_m.TreeMap = _TM
sys.modules["genlayer"] = _m


def load(path=CONTRACT):
    ns = {}
    exec(compile(open(path).read(), path, "exec"), ns)
    c = ns["TokenSecurityScanner"]()
    c.scans = {}
    c.history = {}
    c.scan_count = "0"
    return ns, c


def llm(**answers):
    """Set the mocked reviewer answer. Unlisted categories answer NO."""
    out = {c: {"answer": "NO", "function": "", "reason": "r"} for c in CATS}
    for cat, val in answers.items():
        ans, fn = val if isinstance(val, tuple) else (val, "")
        out[cat] = {"answer": ans, "function": fn, "reason": "r"}
    LLM["raw"] = json.dumps(out)
    LLM["raise"] = None


def src(*funcs, name="T"):
    body = "\n".join("  " + f for f in funcs)
    return "pragma solidity ^0.8.0;\ncontract " + name + " {\n  address owner;\n" + body + "\n}\n"


def sourcify(files, proxy=False):
    return {"sources": {k: {"content": v} for k, v in files.items()}, "proxyResolution": {"isProxy": proxy}}


GP_OK = {"token_symbol": "T", "trust_list": "0", "holder_count": "300", "is_open_source": "1", "is_honeypot": "0",
         "buy_tax": "0", "sell_tax": "0", "is_in_dex": "1",
         "holders": [{"address": "0x" + "a" * 40, "percent": "0.02", "is_contract": 0, "is_locked": 0, "tag": ""}]}


def routes(sourcify_resp=None, gp_entry=None, sourcify_raw=None, gp_down=False):
    ROUTES.clear()
    if sourcify_raw is not None:
        ROUTES.append(("sourcify.dev", lambda u: sourcify_raw))
    else:
        ROUTES.append(("sourcify.dev", lambda u: R(sourcify_resp if sourcify_resp is not None else {})))
    entry = gp_entry if gp_entry is not None else GP_OK
    if gp_down:
        ROUTES.append(("gopluslabs", lambda u: R(b"<html>blocked</html>", 403)))
    else:
        ROUTES.append(("gopluslabs", lambda u: R({"code": 1, "result": {u.split("contract_addresses=")[1].lower(): entry}})))
    ROUTES.append(("coingecko", lambda u: R({}, 404)))


ADDR = "0x" + "4" * 40
TODAY = "2026-10-12"
