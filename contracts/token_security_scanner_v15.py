# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *
import json


LIB_PREFIXES = ["@", "hardhat/", "forge-std/", "ds-test/", "node_modules/", "lib/"]
RISK_WORDS = [
    "mint", "burn", "pause", "freeze", "blacklist", "blocklist", "upgrade",
    "seize", "withdraw", "sweep", "rescue", "setfee", "settax", "setowner",
    "transferownership", "grantrole", "revokerole", "setadmin", "destroy", "kill",
]
SAFE_MODS = [
    "nonreentrant", "whennotpaused", "whenpaused", "initializer",
    "reinitializer", "onlyinitializing",
]
KEYWORDS = [
    "external", "public", "internal", "private", "view", "pure", "payable",
    "virtual", "override",
]
FLAG_TERMS = ["selfdestruct", "delegatecall", "tx.origin", "assembly"]
UPGRADE_MARKERS = [
    "uupsupgradeable.sol", "transparentupgradeableproxy.sol",
    "beaconproxy.sol", "initializable.sol",
]
ACCESS_TOKENS = [
    "msg.sender==", "==msg.sender", "msg.sender!=", "!=msg.sender",
    "_msgsender()==", "==_msgsender()", "_msgsender()!=", "!=_msgsender()",
    "hasrole(", "_checkrole(", "onlyrole", "onlyowner", "_checkowner(",
    "isowner(", "require(owner", "onlyadmin", "onlygovernance",
]
CAND_WORDS = {
    "unrestricted_mint": ["mint", "issue", "increasesupply"],
    "blacklist_or_freeze": ["blacklist", "blocklist", "denylist", "freeze", "blockaddress", "blockuser"],
    "pause_transfers": ["pause"],
    "upgrade_without_timelock": ["upgrade", "setimplementation", "setfacet", "diamondcut",
                                 "changeimplementation", "setlogic"],
}
INIT_MODS = ["initializer", "reinitializer", "onlyinitializing"]
MAP_BUDGET = 8000
SNIPPET_LIMIT = 600
SNIPPET_BUDGET = 8000


def _is_library_path(name: str) -> bool:
    low = name.lower()
    for prefix in LIB_PREFIXES:
        if low.startswith(prefix):
            return True
    return "node_modules/" in low


def _is_ident(ch: str) -> bool:
    return ch.isalnum() or ch == "_" or ch == "$"


def _compact(text: str) -> str:
    return " ".join(text.split())


def _strip_comments(src: str) -> str:
    out = []
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            j = src.find("\n", i)
            if j == -1:
                break
            i = j
            continue
        if c == "/" and nxt == "*":
            j = src.find("*/", i + 2)
            if j == -1:
                break
            out.append(" ")
            i = j + 2
            continue
        if c == '"' or c == "'":
            q = c
            out.append(c)
            i += 1
            while i < n:
                d = src[i]
                i += 1
                if d == "\\" and i < n:
                    out.append("  ")
                    i += 1
                    continue
                if d == q:
                    out.append(d)
                    break
                if d == "\n":
                    out.append(d)
                    break
                out.append(" ")
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _match(s: str, i: int, o: str, c: str) -> int:
    depth = 0
    n = len(s)
    j = i
    while j < n:
        ch = s[j]
        if ch == o:
            depth += 1
        elif ch == c:
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return -1


def _parse_functions(src: str) -> list:
    funcs = []
    pos = 0
    n = len(src)
    while True:
        idx = src.find("function", pos)
        if idx == -1:
            break
        pos = idx + 8
        if idx > 0 and _is_ident(src[idx - 1]):
            continue
        k = idx + 8
        if k >= n or _is_ident(src[k]):
            continue
        while k < n and src[k].isspace():
            k += 1
        s0 = k
        while k < n and _is_ident(src[k]):
            k += 1
        name = src[s0:k]
        if name == "":
            continue
        while k < n and src[k].isspace():
            k += 1
        if k >= n or src[k] != "(":
            continue
        pe = _match(src, k, "(", ")")
        if pe == -1:
            continue
        h = pe + 1
        depth = 0
        while h < n:
            ch = src[h]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif depth == 0 and (ch == "{" or ch == ";"):
                break
            h += 1
        if h >= n:
            break
        header = src[pe + 1:h]
        body = ""
        end = h
        if src[h] == "{":
            be = _match(src, h, "{", "}")
            if be == -1:
                be = n - 1
            body = src[h + 1:be]
            end = be
        funcs.append({"name": name, "header": header, "body": body})
        pos = end + 1
    return funcs


def _has_access_check(body_lower: str) -> bool:
    for tok in ACCESS_TOKENS:
        if tok in body_lower:
            return True
    return False


def _calls_function(body_lower: str, name_lower: str) -> bool:
    for key in [name_lower + "(", "_" + name_lower + "("]:
        idx = body_lower.find(key)
        while idx != -1:
            if idx == 0 or not _is_ident(body_lower[idx - 1]):
                return True
            idx = body_lower.find(key, idx + 1)
    return False


def _analyze_header(header: str) -> dict:
    cut = header.find("returns")
    hdr = header if cut == -1 else header[:cut]
    words = []
    depth = 0
    cur = ""
    for ch in hdr:
        if ch == "(":
            if cur != "" and depth == 0:
                words.append(cur)
            cur = ""
            depth += 1
        elif ch == ")":
            depth -= 1
            cur = ""
        elif depth == 0 and _is_ident(ch):
            cur += ch
        else:
            if cur != "" and depth == 0:
                words.append(cur)
            cur = ""
    if cur != "":
        words.append(cur)

    vis = "unknown"
    mut = "nonpayable"
    mods = []
    for w in words:
        low = w.lower()
        if low in ["external", "public", "internal", "private"]:
            if vis == "unknown":
                vis = low
        elif low in ["view", "pure", "payable"]:
            mut = low
        elif low in KEYWORDS:
            pass
        else:
            mods.append(w)

    privileged = False
    for m in mods:
        low = m.lower()
        if low in SAFE_MODS:
            continue
        if (low.startswith("only") or "role" in low or "auth" in low
                or "admin" in low or "owner" in low):
            privileged = True
    return {"vis": vis, "mut": mut, "mods": mods, "privileged": privileged}


def _build_review(sources: dict) -> dict:
    names = sorted(list(sources.keys()))
    project_files = 0
    library_files = 0
    project_chars = 0
    markers = []
    map_lines = []
    map_len = 0
    map_truncated = False
    snippets = []
    snippets_len = 0
    snippets_truncated = False
    risky = []
    total_funcs = 0
    public_nonview = 0
    view_funcs = 0
    flags = {}
    for term in FLAG_TERMS:
        flags[term] = 0
    pause_gated = []
    pause_ctrl = []
    recs = []

    for nm in names:
        low = nm.lower()
        for mk in UPGRADE_MARKERS:
            if low.endswith(mk):
                markers.append(mk)
        if _is_library_path(nm):
            library_files += 1
            continue
        project_files += 1
        entry = sources[nm]
        if isinstance(entry, dict):
            content = str(entry.get("content", ""))
        else:
            content = str(entry)
        project_chars += len(content)
        clean = _strip_comments(content)
        for term in FLAG_TERMS:
            flags[term] += clean.count(term)
        base = nm.split("/")[-1]
        for fn in _parse_functions(clean):
            total_funcs += 1
            info = _analyze_header(fn["header"])
            body_sp = _compact(fn["body"]).lower()
            bodyc = body_sp.replace(" ", "")
            recs.append({
                "name": fn["name"],
                "pub": info["vis"] in ["external", "public"] and info["mut"] not in ["view", "pure"],
                "gated": bool(info["privileged"]) or _has_access_check(bodyc),
                "body": body_sp[:3000],
                "src": _compact(fn["body"])[:220],
                "pay": info["mut"] == "payable",
                "init": any(m.lower() in INIT_MODS for m in info["mods"]),
                "low": ("delegatecall" in bodyc or "selfdestruct" in bodyc or "assembly" in bodyc),
            })
            if info["vis"] not in ["external", "public"]:
                continue
            if info["mut"] in ["view", "pure"]:
                view_funcs += 1
                continue
            public_nonview += 1
            lmods = [m.lower() for m in info["mods"]]
            if "whennotpaused" in lmods or "whenpaused" in lmods:
                if fn["name"] not in pause_gated:
                    pause_gated.append(fn["name"])
            if fn["name"].lower() in ["pause", "unpause", "setpaused", "togglepause"]:
                if fn["name"] not in pause_ctrl:
                    pause_ctrl.append(fn["name"])
            line = (base + ":" + fn["name"] + "[" + info["vis"] + ","
                    + info["mut"] + "|" + ",".join(info["mods"]) + "]")
            if map_len + len(line) + 1 <= MAP_BUDGET:
                map_lines.append(line)
                map_len += len(line) + 1
            else:
                map_truncated = True
            lname = fn["name"].lower()
            name_risky = False
            for rw in RISK_WORDS:
                if rw in lname:
                    name_risky = True
            if name_risky or info["privileged"]:
                risky.append(base + ":" + fn["name"])
                snip = (base + ":" + fn["name"] + " " + _compact(fn["header"])
                        + " {" + _compact(fn["body"])[:SNIPPET_LIMIT] + "}")
                if snippets_len + len(snip) + 1 <= SNIPPET_BUDGET:
                    snippets.append(snip)
                    snippets_len += len(snip) + 1
                else:
                    snippets_truncated = True

    gated_set = set()
    for r in recs:
        if r["gated"]:
            gated_set.add(r["name"])
    for _round in range(3):
        grew = False
        for r in recs:
            if r["gated"]:
                continue
            for g in list(gated_set):
                if len(g) >= 4 and g != r["name"] and _calls_function(r["body"], g.lower()):
                    r["gated"] = True
                    gated_set.add(r["name"])
                    grew = True
                    break
        if not grew:
            break
    open_fns = []
    gated_fns = []
    for r in recs:
        if not r["pub"]:
            continue
        if r["gated"]:
            if r["name"] not in gated_fns:
                gated_fns.append(r["name"])
        else:
            if r["name"] not in open_fns:
                open_fns.append(r["name"])
    for nm in list(gated_fns):
        if nm in open_fns:
            gated_fns.remove(nm)

    access = {}
    access_fns = {}
    open_evidence = {}
    for cat in RISK_CATEGORIES:
        open_names = []
        gated_names = []
        evidence = []
        for r in recs:
            if not r["pub"] or r["init"]:
                continue
            if cat == "hidden_privileged_calls":
                hit = r["low"]
            else:
                if cat == "unrestricted_mint" and r["pay"]:
                    continue
                ln = r["name"].lower()
                hit = False
                for w in CAND_WORDS.get(cat, []):
                    if w in ln:
                        hit = True
            if not hit:
                continue
            if r["gated"]:
                if r["name"] not in gated_names:
                    gated_names.append(r["name"])
            else:
                if r["name"] not in open_names:
                    open_names.append(r["name"])
                    if len(evidence) < 3:
                        evidence.append({"fn": r["name"], "code": r["src"]})
        open_evidence[cat] = evidence
        if len(open_names) > 0:
            access[cat] = "open"
            access_fns[cat] = open_names[:6]
        elif len(gated_names) > 0:
            access[cat] = "gated"
            access_fns[cat] = gated_names[:6]
        else:
            access[cat] = "none"
            access_fns[cat] = []
    payable_fns = []
    for r in recs:
        if r["pub"] and r["pay"] and r["name"] not in payable_fns:
            payable_fns.append(r["name"])

    return {
        "project_files": project_files,
        "library_files": library_files,
        "project_chars": project_chars,
        "access": access,
        "access_fns": access_fns,
        "open_evidence": open_evidence,
        "payable_fns": payable_fns[:40],
        "open_fns": open_fns[:150],
        "gated_fns": gated_fns[:150],
        "functions_total": total_funcs,
        "functions_public_nonview": public_nonview,
        "functions_view": view_funcs,
        "risky": risky,
        "flags": flags,
        "pause_gated": pause_gated[:12],
        "pause_gated_count": len(pause_gated),
        "pause_ctrl": pause_ctrl[:6],
        "upgrade_markers": sorted(list(set(markers))),
        "map": "\n".join(map_lines),
        "map_truncated": map_truncated,
        "snippets": "\n".join(snippets),
        "snippets_truncated": snippets_truncated,
    }


def _extract_report(text: str) -> str:
    """Laporan ringkas hasil ekstraksi untuk diuji di Studio."""
    try:
        data = json.loads(text)
    except Exception:
        return json.dumps({"error": "not_json"}, sort_keys=True)
    sources = data.get("sources") if isinstance(data, dict) else None
    if not isinstance(sources, dict) or len(sources) == 0:
        return json.dumps({"error": "no_sources"}, sort_keys=True)
    rev = _build_review(sources)
    report = {
        "project_files": rev["project_files"],
        "library_files": rev["library_files"],
        "project_chars": rev["project_chars"],
        "functions_total": rev["functions_total"],
        "functions_public_nonview": rev["functions_public_nonview"],
        "functions_view": rev["functions_view"],
        "risky_count": len(rev["risky"]),
        "risky_names": rev["risky"][:25],
        "flags": rev["flags"],
        "upgrade_markers": rev["upgrade_markers"],
        "map_len": len(rev["map"]),
        "map_truncated": rev["map_truncated"],
        "snippets_len": len(rev["snippets"]),
        "snippets_truncated": rev["snippets_truncated"],
        "map_preview": rev["map"][:500],
    }
    return json.dumps(report, sort_keys=True)


SOURCIFY_BASE = "https://sourcify.dev/server/v2/contract"


def _sourcify_url(chain_id: int, address: str) -> str:
    return (SOURCIFY_BASE + "/" + str(chain_id) + "/" + address
            + "?fields=sources,proxyResolution")


def _fetch_json(url: str) -> dict:
    """Ambil URL, decode, coba parse JSON. Tidak pernah melempar exception
    ke pemanggil; hasil selalu dict dengan minimal kunci 'ok'."""
    try:
        res = gl.nondet.web.get(url)
        body = res.body.decode("utf-8", errors="replace")
    except Exception:
        return {"ok": False, "reason": "fetch_error"}
    try:
        data = json.loads(body)
    except Exception:
        return {"ok": False, "reason": "not_json"}
    if not isinstance(data, dict):
        return {"ok": False, "reason": "not_dict"}
    return {"ok": True, "data": data}


def _proxy_info(data: dict) -> dict:
    pr = data.get("proxyResolution")
    info = {"is_proxy": False, "proxy_type": "", "impl": ""}
    if isinstance(pr, dict):
        info["is_proxy"] = bool(pr.get("isProxy", False))
        info["proxy_type"] = str(pr.get("proxyType", ""))
        impls = pr.get("implementations")
        if isinstance(impls, list):
            for item in impls:
                if isinstance(item, dict) and "address" in item:
                    info["impl"] = str(item["address"])
                    break
    return info


def _analyze_address(chain_id: int, address: str) -> dict:
    """Pipa deterministik lengkap untuk satu alamat: fetch -> deteksi proxy
    -> (bila proxy) fetch implementasi -> ekstraksi kode. Tidak memanggil LLM.
    Selalu mengembalikan dict, tidak pernah melempar exception."""
    result = {
        "chain_id": chain_id,
        "input_address": address,
        "source": "sourcify",
        "verified": False,
        "is_proxy": False,
        "proxy_type": "",
        "analyzed_address": address,
        "review": None,
        "reason": "",
    }

    r1 = _fetch_json(_sourcify_url(chain_id, address))
    if not r1["ok"]:
        result["reason"] = r1["reason"]
        return result

    data1 = r1["data"]
    proxy = _proxy_info(data1)
    result["is_proxy"] = proxy["is_proxy"]
    result["proxy_type"] = proxy["proxy_type"]

    sources1 = data1.get("sources")
    has_sources1 = isinstance(sources1, dict) and len(sources1) > 0

    target_data = data1
    target_sources = sources1
    has_target_sources = has_sources1

    if proxy["is_proxy"] and proxy["impl"] != "":
        result["analyzed_address"] = proxy["impl"]
        r2 = _fetch_json(_sourcify_url(chain_id, proxy["impl"]))
        if r2["ok"]:
            data2 = r2["data"]
            sources2 = data2.get("sources")
            has_sources2 = isinstance(sources2, dict) and len(sources2) > 0
            if has_sources2:
                target_data = data2
                target_sources = sources2
                has_target_sources = True
            else:
                has_target_sources = False
        else:
            has_target_sources = False

    if not has_target_sources:
        result["reason"] = "no_sources"
        return result

    result["verified"] = True
    result["review"] = _shape_review(_build_review(target_sources))
    return result


def _shape_review(rev: dict) -> dict:
    """Ubah hasil mentah _build_review jadi bentuk ringkas untuk disimpan."""
    return {
        "project_files": rev["project_files"],
        "library_files": rev["library_files"],
        "project_chars": rev["project_chars"],
        "functions_total": rev["functions_total"],
        "functions_public_nonview": rev["functions_public_nonview"],
        "functions_view": rev["functions_view"],
        "risky_count": len(rev["risky"]),
        "risky_names": rev["risky"][:25],
        "flags": rev["flags"],
        "access": rev["access"],
        "access_fns": rev["access_fns"],
        "open_evidence": rev["open_evidence"],
        "payable_fns": rev["payable_fns"],
        "open_fns": rev["open_fns"],
        "gated_fns": rev["gated_fns"],
        "pause_gated": rev["pause_gated"],
        "pause_gated_count": rev["pause_gated_count"],
        "pause_ctrl": rev["pause_ctrl"],
        "upgrade_markers": rev["upgrade_markers"],
        "map": rev["map"],
        "map_truncated": rev["map_truncated"],
        "snippets": rev["snippets"],
        "snippets_truncated": rev["snippets_truncated"],
    }


RISK_CATEGORIES = [
    "unrestricted_mint",
    "blacklist_or_freeze",
    "pause_transfers",
    "upgrade_without_timelock",
    "hidden_privileged_calls",
]

CATEGORY_QUESTIONS = {
    "unrestricted_mint": (
        "Is there a function that lets some address mint new tokens or "
        "increase the token supply? Answer YES if the capability exists, even "
        "if it is restricted to a role or limited by a rate limit; whether it "
        "is restricted is judged separately."
    ),
    "blacklist_or_freeze": (
        "Is there a function that lets a privileged address block, blacklist, "
        "or freeze a specific user's tokens or address?"
    ),
    "pause_transfers": (
        "Is there a function that lets a privileged address pause or otherwise "
        "halt all token transfers for every holder?"
    ),
    "upgrade_without_timelock": (
        "Is the contract upgradeable (proxy pattern) with no timelock or delay "
        "mechanism visible in the provided code, meaning a privileged address "
        "could change the logic immediately?"
    ),
    "hidden_privileged_calls": (
        "Does a privileged function make a low-level external call "
        "(delegatecall, call, or inline assembly) whose target or effect is "
        "not clearly restricted, which could be used to bypass the contract's "
        "normal rules?"
    ),
}


def _build_llm_prompt(review: dict, is_proxy: bool, upgrade_markers: list) -> str:
    parts = []
    parts.append("You are a smart contract security reviewer.")
    parts.append(
        "Below is a function map of a token contract (all external/public "
        "state-changing functions, with visibility and modifiers), followed "
        "by full snippets of the functions flagged as potentially privileged "
        "or risky by an automated filter."
    )
    parts.append("is_proxy: " + str(is_proxy))
    parts.append("upgrade_markers: " + json.dumps(upgrade_markers))
    parts.append("assembly_flag_count: " + str(review["flags"].get("assembly", 0)))
    parts.append("delegatecall_flag_count: " + str(review["flags"].get("delegatecall", 0)))
    parts.append("pause_gated_functions: " + json.dumps(review.get("pause_gated", [])))
    parts.append("pause_control_functions: " + json.dumps(review.get("pause_ctrl", [])))
    parts.append("map_truncated: " + str(review.get("map_truncated", False)))
    parts.append("snippets_truncated: " + str(review.get("snippets_truncated", False)))
    parts.append("--- FUNCTION MAP ---")
    parts.append(review["map"] if review["map"] != "" else "(none)")
    parts.append("--- FLAGGED FUNCTION SNIPPETS ---")
    parts.append(review["snippets"] if review["snippets"] != "" else "(none)")
    parts.append("--- QUESTIONS ---")
    for cat in RISK_CATEGORIES:
        parts.append(cat + ": " + CATEGORY_QUESTIONS[cat])
    parts.append(
        "Reply with ONLY a JSON object, no markdown fences, no extra text. "
        "For each of the 5 categories above, include a key with an object "
        "{\"answer\": \"YES\" or \"NO\" or \"UNCLEAR\", \"function\": "
        "\"<function name from the map/snippets, or empty string>\", "
        "\"reason\": \"<at most 15 words explaining the answer>\"}. "
        "You MUST read the function map and snippets carefully before "
        "answering each category. Use these definitions: YES means a "
        "function in the map or snippets clearly provides that capability. "
        "NO means no function in the map or snippets provides that "
        "capability - this INCLUDES the case where no function related to "
        "the category appears at all (for example, a contract with no mint "
        "function has no unrestricted mint, so answer NO). UNCLEAR is "
        "reserved ONLY for incomplete or ambiguous evidence: the map or "
        "snippets are marked truncated above, or a relevant function is "
        "present but its restrictions cannot be determined from the code "
        "shown. UNCLEAR is NOT a safe default; if the shown code is "
        "complete and no function provides the capability, answer NO. "
        "When you answer YES, cite that function by name. Judge only whether "
        "each capability EXISTS; whether it is access-restricted is checked "
        "separately, so never claim in a reason that a function has no "
        "restrictions or no caps - just state what the function does."
    )
    return "\n".join(parts)


LLM_TASK = (
    "Follow the security-reviewer instructions contained in the input "
    "exactly. Evaluate the token smart contract's function map and flagged "
    "function snippets given in the input against the 5 fixed security "
    "categories (unrestricted minting, blacklist/freeze ability, transfer "
    "pausing, upgrade without timelock, hidden privileged external calls), "
    "and reply with ONLY the JSON object the input describes: for each "
    "category an answer of YES, NO, or UNCLEAR, a function name, and a "
    "short reason, based only on the code shown in the input."
)

LLM_CRITERIA = (
    "You are an independent security auditor reviewing another auditor's "
    "(the leader's) claim. Do not simply accept the leader's JSON at face "
    "value. For each of the 5 categories, check whether the leader's "
    "YES/NO/UNCLEAR conclusion is actually supported by the function map "
    "and snippets shown - especially watch for the leader lazily answering "
    "UNCLEAR when a clearly relevant function IS present in the map or "
    "snippets; that is a real flaw, not an acceptable answer. "
    "A valid response is a JSON object with exactly the 5 required category "
    "keys (unrestricted_mint, blacklist_or_freeze, pause_transfers, "
    "upgrade_without_timelock, hidden_privileged_calls), each holding an "
    "object with an \"answer\" field equal to YES, NO, or UNCLEAR and a "
    "\"function\" field naming the relevant function when answer is YES, "
    "plus a short \"reason\" field (the wording of the reason itself is not "
    "grounds for rejection). "
    "Accept the leader's response for a category if its conclusion is a "
    "reasonable reading of the function map and snippets shown, even if "
    "you might have phrased the reasoning differently or would have named "
    "a slightly different but related function - reasonable disagreement "
    "on borderline judgment calls should be accepted, not rejected. Only "
    "reject the response if, for at least one category, the conclusion is "
    "clearly contradicted by the code, cites a function that does not "
    "match the code shown, or answers UNCLEAR even though the shown code "
    "is complete (not marked truncated) - in that case the correct answer "
    "is YES when a relevant function is present, and NO when no function "
    "provides the capability. Answering NO because no related function "
    "exists is correct and must be accepted."
)


def _empty_findings() -> dict:
    out = {}
    for cat in RISK_CATEGORIES:
        out[cat] = {"answer": "UNCLEAR", "function": "", "reason": ""}
    return out


def _parse_llm_findings_checked(raw: str) -> tuple:
    """Parsing defensif atas jawaban LLM. Mengembalikan (findings, parse_ok).
    parse_ok False bila JSON gagal diparse, bukan dict, ada kategori hilang,
    atau ada nilai answer tidak valid. Field reason opsional dan tidak
    mempengaruhi parse_ok. Tidak pernah melempar exception; kategori yang
    tidak valid/tidak ada diisi UNCLEAR."""
    findings = _empty_findings()
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(cleaned)
    except Exception:
        return findings, False
    if not isinstance(data, dict):
        return findings, False
    ok = True
    for cat in RISK_CATEGORIES:
        entry = data.get(cat)
        if not isinstance(entry, dict):
            ok = False
            continue
        ans = str(entry.get("answer", "UNCLEAR")).strip().upper()
        if ans not in ["YES", "NO", "UNCLEAR"]:
            ans = "UNCLEAR"
            ok = False
        fn = entry.get("function", "")
        if not isinstance(fn, str):
            fn = ""
        rs = entry.get("reason", "")
        if not isinstance(rs, str):
            rs = ""
        findings[cat] = {"answer": ans, "function": fn[:200], "reason": rs[:160]}
    return findings, ok


def _parse_llm_findings(raw: str) -> dict:
    return _parse_llm_findings_checked(raw)[0]


def _reconcile_findings(findings: dict, review: dict) -> dict:
    """Selaraskan jawaban LLM dengan bukti deterministik dari kode.
    Hanya mengubah NO menjadi YES (pause) atau UNCLEAR (low-level), tidak
    pernah menurunkan temuan. Entri yang diubah diberi adjusted=True."""
    if not isinstance(review, dict):
        return findings
    pause = findings.get("pause_transfers", {})
    gated = review.get("pause_gated", [])
    ctrl = review.get("pause_ctrl", [])
    if pause.get("answer") != "YES" and (len(gated) > 0 or len(ctrl) > 0):
        if len(ctrl) > 0:
            fname = ctrl[0]
            why = "A pause control function exists in the code."
        else:
            fname = gated[0]
            why = "Functions are gated by a pause switch (" + str(review.get("pause_gated_count", len(gated))) + " found)."
        findings["pause_transfers"] = {
            "answer": "YES", "function": fname, "reason": why, "adjusted": True,
        }
    mint = findings.get("unrestricted_mint", {})
    if mint.get("answer") == "YES":
        acc = review.get("access", {}).get("unrestricted_mint", "none")
        cited = str(mint.get("function", ""))
        if acc == "none" and cited != "" and cited in review.get("payable_fns", []):
            findings["unrestricted_mint"] = {
                "answer": "NO", "function": "",
                "reason": "The cited function only credits value sent with it (a deposit or wrap), not a free mint.",
                "adjusted": True,
            }
    low = findings.get("hidden_privileged_calls", {})
    flags = review.get("flags", {})
    parts = []
    for term in FLAG_TERMS:
        n = flags.get(term, 0)
        if n > 0:
            parts.append(term + " " + str(n))
    if low.get("answer") == "NO" and len(parts) > 0:
        findings["hidden_privileged_calls"] = {
            "answer": "UNCLEAR", "function": "",
            "reason": "Low-level code is present (" + ", ".join(parts) + "); could not confirm it is restricted.",
            "adjusted": True,
        }
    return findings


def _is_open(cat: str, fname: str, review: dict) -> bool:
    """True bila kode membuktikan ada fungsi kategori ini tanpa pembatasan akses.
    Dinilai dari kandidat fungsi berdasarkan nama, bukan dari fungsi yang
    disebut LLM, supaya hasil tidak berubah-ubah antar run."""
    if not isinstance(review, dict):
        return False
    if review.get("project_files", 0) > 30:
        return False
    access = review.get("access", {})
    return access.get(cat) == "open"


def _compute_verdict(findings: dict, review: dict = None) -> str:
    yes_cats = []
    unclear_count = 0
    for cat in RISK_CATEGORIES:
        ans = findings.get(cat, {}).get("answer")
        if ans == "YES":
            yes_cats.append(cat)
        elif ans == "UNCLEAR":
            unclear_count += 1
    if len(yes_cats) == 0:
        if unclear_count >= 3:
            return "INCONCLUSIVE"
        return "CLEAR"
    for cat in yes_cats:
        fname = str(findings.get(cat, {}).get("function", ""))
        if _is_open(cat, fname, review):
            return "DANGER"
    if len(yes_cats) >= 2:
        return "CENTRALIZED"
    return "CAUTION"


DEFAULT_UNVERIFIED_EXPLANATION = (
    "No verified source code was found for this contract, so its actual "
    "behavior cannot be reviewed at all. Treat this as a significant risk "
    "signal on its own, independent of any other claims made about the "
    "token."
)


def _unverified_explanation(is_proxy: bool) -> str:
    text = DEFAULT_UNVERIFIED_EXPLANATION
    if is_proxy:
        text += (" This contract is also a proxy, so its real logic sits behind "
                 "another contract and cannot be inspected at all, which is more "
                 "serious than an unverified plain contract.")
    return text


def _build_unverified_prompt(chain_id: int, address: str, is_proxy: bool,
                              proxy_type: str, reason: str) -> str:
    parts = []
    parts.append("You are a smart contract security reviewer.")
    parts.append(
        "A user asked to scan a token contract, but no verified source "
        "code could be found for it."
    )
    parts.append("chain_id: " + str(chain_id))
    parts.append("address: " + address)
    parts.append("is_proxy: " + str(is_proxy))
    parts.append("proxy_type: " + (proxy_type if proxy_type != "" else "(none detected)"))
    parts.append("lookup_reason: " + reason)
    parts.append(
        "Write a short (2-3 sentence) plain-language explanation for a "
        "non-technical crypto trader of why the absence of verified "
        "source code is itself a risk signal for this specific contract, "
        "based only on the facts listed above. If is_proxy is true, "
        "specifically mention that the actual logic is hidden behind a "
        "proxy and cannot be inspected at all, which is a more serious "
        "concern than an unverified non-proxy contract. Do not invent or "
        "guess at any specific code behavior (such as claiming there is "
        "a mint function or a pause function) - no code is available to "
        "review, so do not make claims about what the code does."
    )
    parts.append(
        "Reply with ONLY a JSON object, no markdown fences, no extra "
        "text: {\"explanation\": \"<your explanation>\"}"
    )
    return "\n".join(parts)


UNVERIFIED_TASK = (
    "Explain in 2-3 plain-language sentences why the lack of verified "
    "source code is a risk signal for a specific token contract, given "
    "only its chain id, address, and whether it is a proxy."
)

UNVERIFIED_CRITERIA = (
    "A valid response is a JSON object with a single \"explanation\" key "
    "holding a 2-4 sentence plain-language explanation. Accept the "
    "response if it accurately reflects the given facts and does not "
    "fabricate details about the contract's code, since none is "
    "available to review. When is_proxy is true, the explanation should "
    "mention that the real logic is hidden behind a proxy and cannot be "
    "inspected. Reject responses that invent specific code behavior "
    "(such as claiming to have found a mint function, a pause function, "
    "or any other specific mechanism) since no code was actually "
    "available."
)


def _parse_unverified_explanation(raw: str) -> str:
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(cleaned)
    except Exception:
        return DEFAULT_UNVERIFIED_EXPLANATION
    if not isinstance(data, dict):
        return DEFAULT_UNVERIFIED_EXPLANATION
    exp = data.get("explanation", "")
    if not isinstance(exp, str) or exp.strip() == "":
        return DEFAULT_UNVERIFIED_EXPLANATION
    return exp.strip()[:600]


def _sources_from_pasted(raw_input: str) -> dict:
    """Terima input tempelan pengguna: JSON multi-file gaya Sourcify
    ({"sources": {...}} atau flat {"File.sol": "content", ...}), atau
    teks kode satu file biasa. Selalu mengembalikan dict sources
    ({filename: {"content": str}}), tidak pernah melempar exception."""
    stripped = raw_input.strip()
    if stripped == "":
        return {}
    try:
        data = json.loads(stripped)
    except Exception:
        data = None

    if isinstance(data, dict) and len(data) > 0:
        if "sources" in data and isinstance(data["sources"], dict):
            return data["sources"]
        looks_like_sources = True
        for v in data.values():
            is_str = isinstance(v, str)
            is_content_dict = isinstance(v, dict) and "content" in v
            if not (is_str or is_content_dict):
                looks_like_sources = False
                break
        if looks_like_sources:
            out = {}
            for k, v in data.items():
                out[k] = {"content": v} if isinstance(v, str) else v
            return out

    return {"pasted_code.sol": {"content": raw_input}}


# ===== module: goplus_probe_v2 (prefix gp_) =====
gp_GOPLUS_BASE ="https://api.gopluslabs.io/api/v1/token_security/"
gp_HEX_CHARS ="0123456789abcdefABCDEF"
gp_ELEVATED_BP =3000 # top holder (wallet) >= 30%
gp_HIGH_BP =5000 # top holder (wallet) >= 50%


def gp__valid_evm_address (address :str )->bool :
    if not isinstance (address ,str )or len (address )!=42 :
        return False 
    if not address .startswith ("0x"):
        return False 
    for ch in address [2 :]:
        if ch not in gp_HEX_CHARS :
            return False 
    return True 


def gp__report_url (chain_id :int ,address :str )->str :
    return gp_GOPLUS_BASE +str (chain_id )+"?contract_addresses="+address .lower ()


def gp__tri (value )->str :
    """GoPlus memakai string "1"/"0". Selain itu dianggap tidak diketahui."""
    if value =="1"or value ==1 or value is True :
        return "yes"
    if value =="0"or value ==0 or value is False :
        return "no"
    return "unknown"


def gp__to_float (value ):
    """Kembalikan float atau None. Menolak bool dan string non-angka."""
    if isinstance (value ,bool ):
        return None 
    if isinstance (value ,(int ,float )):
        return float (value )
    if isinstance (value ,str ):
        s =value .strip ()
        if s =="":
            return None 
        try :
            return float (s )
        except Exception :
            return None 
    return None 


def gp__holder_bucket (value )->str :
    n =gp__to_float (value )
    if n is None or n <0 :
        return "unknown"
    if n <100 :
        return "<100"
    if n <1000 :
        return "100-1k"
    if n <10000 :
        return "1k-10k"
    if n <100000 :
        return "10k-100k"
    return ">100k"


def gp__bp_bucket (bp :int )->str :
    """Ember 10 persen dari basis point: 0-10%, 10-20%, ..., 90%+."""
    if bp <0 :
        bp =0 
    pct =bp //100 
    if pct >=90 :
        return "90%+"
    low =(pct //10 )*10 
    return str (low )+"-"+str (low +10 )+"%"


def gp__fraction_bucket (value )->str :
    """Pecahan GoPlus (0.26 = 26 persen) -> ember 10 persen. Di luar 0..1 -> unknown."""
    f =gp__to_float (value )
    if f is None or f <0 or f >1 :
        return "unknown"
    return gp__bp_bucket (int (round (f *10000 )))


def gp__holder_rows (holders )->list :
    rows =[]
    if not isinstance (holders ,list ):
        return rows 
    for h in holders [:10 ]:
        if not isinstance (h ,dict ):
            continue 
        p =gp__to_float (h .get ("percent"))
        if p is None or p <0 or p >1 :
            continue 
        tag =h .get ("tag")
        rows .append ({
        "bp":int (round (p *10000 )),
        "contract":gp__tri (h .get ("is_contract"))=="yes",
        "locked":gp__tri (h .get ("is_locked"))=="yes",
        "labeled":isinstance (tag ,str )and tag !="",
        })
    return rows 


def gp__analyze_holders (holders )->dict :
    rows =gp__holder_rows (holders )
    if len (rows )==0 :
        return {"top10_bucket":"unknown","wallet_top_bucket":"unknown",
        "locked_bucket":"unknown","contract_unlocked_bucket":"unknown",
        "wallet_concentration":"unknown",
        "holders_listed":0 ,"holders_excluded":0 ,"labeled_holders":0 }
    all_bp =0 
    locked_bp =0 
    contract_bp =0 
    excluded_n =0 
    labeled =0 
    for r in rows :
        all_bp +=r ["bp"]
        if r ["locked"]:
            locked_bp +=r ["bp"]
            excluded_n +=1 
        elif r ["contract"]:
            contract_bp +=r ["bp"]
            excluded_n +=1 
        if r ["labeled"]:
            labeled +=1 
    wallet_bp =all_bp -locked_bp -contract_bp 
    if wallet_bp >=gp_HIGH_BP :
        level ="HIGH"
    elif wallet_bp >=gp_ELEVATED_BP :
        level ="ELEVATED"
    else :
        level ="LOW"
    return {
    "top10_bucket":gp__bp_bucket (all_bp ),
    "wallet_top_bucket":gp__bp_bucket (wallet_bp ),
    "locked_bucket":gp__bp_bucket (locked_bp ),
    "contract_unlocked_bucket":gp__bp_bucket (contract_bp ),
    "wallet_concentration":level ,
    "holders_listed":len (rows ),
    "holders_excluded":excluded_n ,
    "labeled_holders":labeled ,
    }


def gp__symbol (value )->str :
    """Hanya untuk tampilan: huruf/angka/tanda baca sederhana, maksimal 16 karakter."""
    if not isinstance (value ,str ):
        return ""
    out =""
    for ch in value [:16 ]:
        if ch .isprintable ():
            out +=ch 
    return out 


def gp__cex_status (value )->dict :
    """GoPlus tidak mengembalikan is_in_cex bila token tidak ditemukan di daftar CEX-nya."""
    if isinstance (value ,dict )and gp__tri (value .get ("listed"))=="yes":
        names =value .get ("cex_list")
        n =len (names )if isinstance (names ,list )else 0 
        return {"cex_listed":"yes","cex_count":"3+"if n >=3 else ("1-2"if n >=1 else "0")}
    return {"cex_listed":"no_info","cex_count":"0"}


def gp__tax_bucket (value )->str :
    """GoPlus memberi pajak sebagai pecahan (0.05 = 5 persen)."""
    f =gp__to_float (value )
    if f is None or f <0 :
        return "unknown"
    if f ==0 :
        return "none"
    if f <=0.05 :
        return "low"
    return "high"


def gp__extract_goplus (body_text :str ,address :str )->dict :
    """Ambil hanya field yang sudah dikelompokkan dari respons GoPlus.
    Tidak pernah melempar exception; selalu mengembalikan dict dengan 'ok'."""
    try :
        data =json .loads (body_text )
    except Exception :
        return {"ok":False ,"reason":"not_json"}
    if not isinstance (data ,dict ):
        return {"ok":False ,"reason":"not_dict"}
    if data .get ("code")!=1 :
        return {"ok":False ,"reason":"api_error"}
    result =data .get ("result")
    if not isinstance (result ,dict )or len (result )==0 :
        return {"ok":False ,"reason":"no_data"}

    entry =result .get (address .lower ())
    if not isinstance (entry ,dict ):
        entry =None 
        for k in sorted (result .keys ()):
            if isinstance (k ,str )and k .lower ()==address .lower ()and isinstance (result [k ],dict ):
                entry =result [k ]
                break 
    if entry is None or len (entry )==0 :
        return {"ok":False ,"reason":"no_data"}

    out ={
    "ok":True ,
    "source":"goplus",
    "symbol":gp__symbol (entry .get ("token_symbol")),
    "trust_list":gp__tri (entry .get ("trust_list")),
    "holder_bucket":gp__holder_bucket (entry .get ("holder_count")),
    "honeypot":gp__tri (entry .get ("is_honeypot")),
    "buy_tax":gp__tax_bucket (entry .get ("buy_tax")),
    "sell_tax":gp__tax_bucket (entry .get ("sell_tax")),
    "tax_modifiable":gp__tri (entry .get ("slippage_modifiable")),
    "in_dex":gp__tri (entry .get ("is_in_dex")),
    "open_source":gp__tri (entry .get ("is_open_source")),
    "mintable":gp__tri (entry .get ("is_mintable")),
    "blacklist":gp__tri (entry .get ("is_blacklisted")),
    "pausable":gp__tri (entry .get ("transfer_pausable")),
    "owner_can_reclaim":gp__tri (entry .get ("can_take_back_ownership")),
    "hidden_owner":gp__tri (entry .get ("hidden_owner")),
    "proxy":gp__tri (entry .get ("is_proxy")),
    "owner_bucket":gp__fraction_bucket (entry .get ("owner_percent")),
    "creator_bucket":gp__fraction_bucket (entry .get ("creator_percent")),
    }
    out .update (gp__cex_status (entry .get ("is_in_cex")))
    out .update (gp__analyze_holders (entry .get ("holders")))
    return out 


def gp__fetch_goplus (chain_id :int ,address :str )->dict :
    if isinstance (chain_id ,bool )or not isinstance (chain_id ,int )or chain_id <1 :
        return {"ok":False ,"reason":"bad_chain"}
    if not gp__valid_evm_address (address ):
        return {"ok":False ,"reason":"bad_address"}
    try :
        res =gl .nondet .web .get (gp__report_url (chain_id ,address ))
        body =res .body .decode ("utf-8",errors ="replace")
    except Exception :
        return {"ok":False ,"reason":"fetch_error"}
    return gp__extract_goplus (body ,address )


# ===== module: coingecko_probe (prefix cg_) =====
cg_CG_BASE ="https://api.coingecko.com/api/v3/coins/"
cg_CG_QUERY ="?localization=false&tickers=true&market_data=false&community_data=false&developer_data=false&sparkline=false"
cg_PLATFORMS =["ethereum","base","binance-smart-chain","arbitrum-one","polygon-pos","optimistic-ethereum","solana"]
cg_HEX_CHARS ="0123456789abcdefABCDEF"
cg_BASE58_CHARS ="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
cg_MAX_TICKERS =200 


def cg__valid_address (platform :str ,address :str )->bool :
    if not isinstance (address ,str ):
        return False 
    if platform =="solana":
        if len (address )<32 or len (address )>44 :
            return False 
        for ch in address :
            if ch not in cg_BASE58_CHARS :
                return False 
        return True 
    if len (address )!=42 or not address .startswith ("0x"):
        return False 
    for ch in address [2 :]:
        if ch not in cg_HEX_CHARS :
            return False 
    return True 


def cg__is_num (value )->bool :
    return isinstance (value ,(int ,float ))and not isinstance (value ,bool )


def cg__rank_bucket (rank )->str :
    if not cg__is_num (rank )or rank <1 :
        return "unranked"
    if rank <=100 :
        return "top100"
    if rank <=500 :
        return "top500"
    if rank <=2000 :
        return "top2000"
    return "below2000"


def cg__exchange_bucket (n :int )->str :
    if n <=0 :
        return "0"
    if n <5 :
        return "1-4"
    if n <15 :
        return "5-14"
    return "15+"


def cg__clean_text (value ,limit :int )->str :
    if isinstance (value ,str ):
        out =""
        for ch in value [:limit ]:
            if ch .isprintable ():
                out +=ch 
        return out 
    return ""


def cg__exchange_names (tickers )->int :
    names =[]
    if isinstance (tickers ,list ):
        for t in tickers [:cg_MAX_TICKERS ]:
            if not isinstance (t ,dict ):
                continue 
            market =t .get ("market")
            if isinstance (market ,dict )and isinstance (market .get ("name"),str )and market ["name"]!="":
                if market ["name"]not in names :
                    names .append (market ["name"])
    return len (names )


def cg__has_notice (data :dict )->bool :
    for key in ("public_notice",):
        v =data .get (key )
        if isinstance (v ,str )and v .strip ()!="":
            return True 
    notices =data .get ("additional_notices")
    return isinstance (notices ,list )and len (notices )>0 


def cg__summarize (data :dict ,platform :str ,address :str )->dict :
    platforms =data .get ("platforms")
    listed =False 
    if isinstance (platforms ,dict ):
        for k in sorted (platforms .keys ()):
            v =platforms [k ]
            if k ==platform and isinstance (v ,str )and v .lower ()==address .lower ():
                listed =True 
    cats =data .get ("categories")
    stable =False 
    if isinstance (cats ,list ):
        for c in cats :
            if isinstance (c ,str )and "stablecoin"in c .lower ():
                stable =True 
    return {
    "ok":True ,
    "found":True ,
    "address_matches_platform":listed ,
    "symbol":cg__clean_text (data .get ("symbol"),16 ),
    "rank_bucket":cg__rank_bucket (data .get ("market_cap_rank")),
    "exchanges_bucket":cg__exchange_bucket (cg__exchange_names (data .get ("tickers"))),
    "stablecoin_category":stable ,
    "has_notice":cg__has_notice (data ),
    }


def cg__fetch_probe (platform :str ,address :str )->dict :
    if platform not in cg_PLATFORMS :
        return {"ok":False ,"reason":"bad_platform"}
    if not cg__valid_address (platform ,address ):
        return {"ok":False ,"reason":"bad_address"}
    addr =address if platform =="solana"else address .lower ()
    try :
        res =gl .nondet .web .get (cg_CG_BASE +platform +"/contract/"+addr +cg_CG_QUERY )
    except Exception :
        return {"ok":False ,"reason":"fetch_error"}
    status =getattr (res ,"status",None )
    if not isinstance (status ,int )or isinstance (status ,bool ):
        status =0 
    if status ==404 :
        return {"ok":True ,"found":False }
    if status !=200 :
        return {"ok":False ,"reason":"http","status":status }
    try :
        data =json .loads (res .body .decode ("utf-8",errors ="replace"))
    except Exception :
        return {"ok":False ,"reason":"bad_body"}
    if not isinstance (data ,dict ):
        return {"ok":False ,"reason":"bad_body"}
    return cg__summarize (data ,platform ,addr )


# ===== module: market_sources_probe (prefix ms_) =====
ms_JUPITER_URL ="https://lite-api.jup.ag/tokens/v2/search?query="
ms_DEX_ORDERS_URL ="https://api.dexscreener.com/orders/v1/solana/"
ms_RUGCHECK_URL ="https://api.rugcheck.xyz/v1/tokens/"
ms_BASE58_CHARS ="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
ms_DIGITS ="0123456789"
ms_MAX_STR =64 
ms_MAX_TAGS =8 
ms_PAID_TYPES =["communityTakeover","tokenAd","tokenProfile","trendingBarAd"]


def ms__valid_mint (value )->bool :
    if not isinstance (value ,str )or len (value )<32 or len (value )>44 :
        return False 
    for ch in value :
        if ch not in ms_BASE58_CHARS :
            return False 
    return True 


def ms__clean_text (value ,limit :int )->str :
    if isinstance (value ,str ):
        cleaned =""
        for ch in value [:limit ]:
            if ch .isprintable ():
                cleaned +=ch 
        return cleaned 
    return ""


def ms__is_num (value )->bool :
    return isinstance (value ,(int ,float ))and not isinstance (value ,bool )


def ms__date_only (value ):
    if not isinstance (value ,str )or len (value )<10 :
        return None 
    head =value [:10 ]
    for i in range (10 ):
        ch =head [i ]
        if i in (4 ,7 ):
            if ch !="-":
                return None 
        elif ch not in ms_DIGITS :
            return None 
    return head 


def ms__bucket10 (pct )->str :
    if not ms__is_num (pct )or pct <0 or pct >100 :
        return "unknown"
    low =int (pct //10 )*10 
    if low >=100 :
        return "100"
    return str (low )+"-"+str (low +10 )


def ms__holders_bucket (count )->str :
    if not ms__is_num (count )or count <0 :
        return "unknown"
    if count <100 :
        return "<100"
    if count <500 :
        return "100-499"
    if count <2000 :
        return "500-1999"
    if count <10000 :
        return "2000-9999"
    return "10000+"


def ms__organic_bucket (score )->str :
    if not ms__is_num (score )or score <0 :
        return "unknown"
    if score <50 :
        return "<50"
    if score <80 :
        return "50-79"
    return "80+"


def ms__bool_or_none (value ):
    if isinstance (value ,bool ):
        return value 
    return None 


def ms__http_json (url :str ):
    """Kembalikan (data, reason, status). Teks error tidak ikut disimpan."""
    try :
        res =gl .nondet .web .get (url )
    except Exception as exc :
        return None ,"exception",0 
    status =getattr (res ,"status",None )
    if not isinstance (status ,int )or isinstance (status ,bool ):
        status =0 
    if status !=200 :
        return None ,"http",status 
    try :
        data =json .loads (res .body .decode ("utf-8",errors ="replace"))
    except Exception :
        return None ,"bad_body",status 
    return data ,None ,status 


def ms__fail (reason ,status )->dict :
    out ={"ok":False ,"reason":reason }
    if reason =="http":
        out ["status"]=status 
    return out 


def ms__jupiter_summary (data ,mint :str )->dict :
    items =data if isinstance (data ,list )else []
    entry =None 
    for item in items :
        if isinstance (item ,dict )and item .get ("id")==mint :
            entry =item 
            break 
    if entry is None :
        return {"ok":True ,"found":False }
    tags =[]
    raw_tags =entry .get ("tags")
    if isinstance (raw_tags ,list ):
        for t in raw_tags :
            if isinstance (t ,str )and t !="":
                label =ms__clean_text (t ,32 )
                if label not in tags :
                    tags .append (label )
    tags .sort ()
    audit =entry .get ("audit")if isinstance (entry .get ("audit"),dict )else {}
    label =entry .get ("organicScoreLabel")
    first_pool =entry .get ("firstPool")if isinstance (entry .get ("firstPool"),dict )else {}
    launchpad =entry .get ("launchpad")
    return {
    "ok":True ,
    "found":True ,
    "is_verified":ms__bool_or_none (entry .get ("isVerified")),
    "tags":tags [:ms_MAX_TAGS ],
    "organic_bucket":ms__organic_bucket (entry .get ("organicScore")),
    "organic_label":ms__clean_text (label ,16 )if isinstance (label ,str )else None ,
    "holders_bucket":ms__holders_bucket (entry .get ("holderCount")),
    "mint_authority_disabled":ms__bool_or_none (audit .get ("mintAuthorityDisabled")),
    "freeze_authority_disabled":ms__bool_or_none (audit .get ("freezeAuthorityDisabled")),
    "top_holders_bucket":ms__bucket10 (audit .get ("topHoldersPercentage")),
    "launchpad":ms__clean_text (launchpad ,ms_MAX_STR )if isinstance (launchpad ,str )and launchpad !=""else None ,
    "first_pool_date":ms__date_only (first_pool .get ("createdAt")),
    }


def ms__orders_summary (data )->dict :
    if isinstance (data ,dict )and isinstance (data .get ("orders"),list ):
        orders =data ["orders"]
    elif isinstance (data ,list ):
        orders =data 
    else :
        orders =[]
    approved =[]
    for item in orders :
        if not isinstance (item ,dict ):
            continue 
        kind =item .get ("type")
        if item .get ("status")=="approved"and isinstance (kind ,str )and kind in ms_PAID_TYPES :
            if kind not in approved :
                approved .append (kind )
    approved .sort ()
    return {"ok":True ,"dex_paid":len (approved )>0 ,"approved_types":approved }


def ms__describe_authority (value )->str :
    if value is None :
        return "null"
    if isinstance (value ,str ):
        if value =="":
            return "empty_string"
        return "str:"+ms__clean_text (value ,ms_MAX_STR )
    if isinstance (value ,bool ):
        return "bool:"+str (value )
    return "type:"+type (value ).__name__ 


def ms__rugcheck_summary (report )->dict :
    if not isinstance (report ,dict ):
        return {"ok":False ,"reason":"bad_body"}
    token =report .get ("token")if isinstance (report .get ("token"),dict )else {}
    return {
    "ok":True ,
    "mint_top":ms__describe_authority (report .get ("mintAuthority")),
    "freeze_top":ms__describe_authority (report .get ("freezeAuthority")),
    "mint_token":ms__describe_authority (token .get ("mintAuthority")),
    "freeze_token":ms__describe_authority (token .get ("freezeAuthority")),
    }


def ms__fetch_probe (mint :str )->dict :
    if not ms__valid_mint (mint ):
        return {"ok":False ,"reason":"bad_mint"}
    out ={"ok":True }

    data ,reason ,status =ms__http_json (ms_JUPITER_URL +mint )
    out ["jupiter"]=ms__jupiter_summary (data ,mint )if reason is None else ms__fail (reason ,status )

    data ,reason ,status =ms__http_json (ms_DEX_ORDERS_URL +mint )
    out ["dexscreener"]=ms__orders_summary (data )if reason is None else ms__fail (reason ,status )

    data ,reason ,status =ms__http_json (ms_RUGCHECK_URL +mint +"/report")
    out ["rugcheck_authority"]=ms__rugcheck_summary (data )if reason is None else ms__fail (reason ,status )
    return out 


# ===== module: solana_structure_probe (prefix ss_) =====
ss_RUGCHECK_BASE ="https://api.rugcheck.xyz/v1/tokens/"
ss_BASE58_CHARS ="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
ss_DIGITS ="0123456789"

# Alamat yang menandakan token dibakar / tidak bisa dipakai: bukan holder nyata.
ss_BURN_ADDRESSES =[
"1nc1nerator11111111111111111111111111111111",
"11111111111111111111111111111111",
]

ss_MAX_STR =64 
ss_MAX_TOP =20 # RugCheck mengembalikan 20 holder teratas
ss_TOP_N =10 
ss_ELEVATED_BP =3000 # top-10 >= 30%
ss_HIGH_BP =5000 # top-10 >= 50%


def ss__valid_mint (value )->bool :
    if not isinstance (value ,str )or len (value )<32 or len (value )>44 :
        return False 
    for ch in value :
        if ch not in ss_BASE58_CHARS :
            return False 
    return True 


def ss__clean_text (value ,limit :int )->str :
    if isinstance (value ,str ):
        cleaned =""
        for ch in value [:limit ]:
            if ch .isprintable ():
                cleaned +=ch 
        return cleaned 
    return ""


def ss__is_num (value )->bool :
    return isinstance (value ,(int ,float ))and not isinstance (value ,bool )


def ss__pct_to_bp (value )->int :
    """Persen (mis. 49.2303) -> basis point bulat (4923). Negatif/aneh -> 0."""
    if not ss__is_num (value )or value <0 or value >100 :
        return 0 
    return int (round (value *100 ))


def ss__bucket10 (bp :int )->str :
    """Ember lebar 10%: 0-10, 10-20, ..., 90-100."""
    if bp <0 :
        bp =0 
    low =(bp //1000 )*10 
    if low >=100 :
        return "100"
    return str (low )+"-"+str (low +10 )


def ss__holders_bucket (count )->str :
    if not ss__is_num (count )or count <0 :
        return "unknown"
    if count <100 :
        return "<100"
    if count <500 :
        return "100-499"
    if count <2000 :
        return "500-1999"
    if count <10000 :
        return "2000-9999"
    return "10000+"


def ss__count_bucket (n :int )->str :
    if n <=0 :
        return "0"
    if n <=2 :
        return "1-2"
    return "3+"


def ss__lp_bucket (pct )->str :
    if not ss__is_num (pct ):
        return "unknown"
    if pct <10 :
        return "0-10"
    if pct <50 :
        return "10-50"
    if pct <90 :
        return "50-90"
    return "90+"


def ss__date_only (value ):
    """'2026-06-16T21:05:50.3Z' -> '2026-06-16'; selain itu None."""
    if not isinstance (value ,str )or len (value )<10 :
        return None 
    head =value [:10 ]
    for i in range (10 ):
        ch =head [i ]
        if i in (4 ,7 ):
            if ch !="-":
                return None 
        elif ch not in ss_DIGITS :
            return None 
    return head 


def ss__str_or_none (value ):
    if isinstance (value ,str )and value !="":
        return ss__clean_text (value ,ss_MAX_STR )
    return None 


def ss__excluded_set (report :dict ,creator )->set :
    """Akun yang bukan holder nyata: burn, pool/likuiditas, locker."""
    out =set ()
    for addr in ss_BURN_ADDRESSES :
        out .add (addr )
    markets =report .get ("markets")
    if isinstance (markets ,list ):
        for market in markets :
            if not isinstance (market ,dict ):
                continue 
            for key in ("pubkey","liquidityA","liquidityB"):
                v =market .get (key )
                if isinstance (v ,str )and v !="":
                    out .add (v )
            for key in ("liquidityAAccount","liquidityBAccount"):
                acc =market .get (key )
                if isinstance (acc ,dict )and isinstance (acc .get ("owner"),str ):
                    out .add (acc ["owner"])
    lockers =report .get ("lockers")
    if isinstance (lockers ,dict ):
        for key in lockers .keys ():
            if isinstance (key ,str ):
                out .add (key )
            item =lockers [key ]
            if isinstance (item ,dict ):
                for sub in ("owner","tokenAccount","programID"):
                    v =item .get (sub )
                    if isinstance (v ,str )and v !="":
                        out .add (v )
    owners =report .get ("lockerOwners")
    if isinstance (owners ,dict ):
        for key in owners .keys ():
            if isinstance (key ,str ):
                out .add (key )
    if isinstance (creator ,str ):
        out .discard (creator )# kreator tidak pernah dikecualikan
    return out 


def ss__holder_rows (report :dict )->list :
    rows =[]
    holders =report .get ("topHolders")
    if not isinstance (holders ,list ):
        return rows 
    for item in holders [:ss_MAX_TOP ]:
        if not isinstance (item ,dict ):
            continue 
        rows .append ({
        "address":item .get ("address")if isinstance (item .get ("address"),str )else "",
        "owner":item .get ("owner")if isinstance (item .get ("owner"),str )else "",
        "bp":ss__pct_to_bp (item .get ("pct")),
        "insider":item .get ("insider")is True ,
        })
    return rows 


def ss__analyze_holders (report :dict ,creator )->dict :
    excluded =ss__excluded_set (report ,creator )
    rows =ss__holder_rows (report )
    kept =[]
    excluded_count =0 
    for row in rows :
        if row ["address"]in excluded or row ["owner"]in excluded :
            excluded_count +=1 
        else :
            kept .append (row )
    top =kept [:ss_TOP_N ]
    top_bp =0 
    insider_bp =0 
    insider_n =0 
    creator_bp =0 
    for row in top :
        top_bp +=row ["bp"]
    for row in kept :
        if row ["insider"]:
            insider_bp +=row ["bp"]
            insider_n +=1 
        if isinstance (creator ,str )and creator !=""and (row ["address"]==creator or row ["owner"]==creator ):
            creator_bp +=row ["bp"]
    if top_bp >=ss_HIGH_BP :
        level ="HIGH"
    elif top_bp >=ss_ELEVATED_BP :
        level ="ELEVATED"
    else :
        level ="LOW"
    return {
    "top10_bucket":ss__bucket10 (top_bp ),
    "concentration":level ,
    "excluded_holders":excluded_count ,
    "listed_holders":len (rows ),
    "creator_bucket":ss__bucket10 (creator_bp )if creator_bp >0 else "0",
    "insider_holders":insider_n ,
    "insider_bucket":ss__bucket10 (insider_bp )if insider_bp >0 else "0",
    }


ss_MAX_MARKETS_SCAN =1000 


def ss__market_usd (lp ):
    """Nilai likuiditas satu pool dalam USD (sisi token + sisi quote); None bila tidak ada."""
    if not isinstance (lp ,dict ):
        return None 
    base =lp .get ("baseUSD")
    quote =lp .get ("quoteUSD")
    if not ss__is_num (base )or not ss__is_num (quote )or base <0 or quote <0 :
        return None 
    return float (base )+float (quote )


def ss__lock_known (lp )->bool :
    """Pool yang punya token LP (lpTotalSupply > 0) dan angka kunci dalam USD.
    Pool tanpa token LP (misalnya likuiditas terkonsentrasi) tidak bisa dinilai."""
    supply =lp .get ("lpTotalSupply")
    locked =lp .get ("lpLockedUSD")
    return ss__is_num (supply )and supply >0 and ss__is_num (locked )and locked >=0 


def ss__lp_and_markets (report :dict )->dict :
    types =[]
    total =0.0 
    known =0.0 
    locked =0.0 
    markets =report .get ("markets")
    if isinstance (markets ,list ):
        for market in markets [:ss_MAX_MARKETS_SCAN ]:
            if not isinstance (market ,dict ):
                continue 
            mt =market .get ("marketType")
            if isinstance (mt ,str )and mt !="":
                label =ss__clean_text (mt ,40 )
                if label not in types :
                    types .append (label )
            lp =market .get ("lp")
            usd =ss__market_usd (lp )
            if usd is None :
                continue 
            total +=usd 
            if ss__lock_known (lp ):
                known +=usd 
                locked +=min (float (lp ["lpLockedUSD"]),usd )
    types .sort ()
    locked_pct =locked *100.0 /known if known >0 else None 
    coverage_pct =known *100.0 /total if total >0 else None 
    return {"market_types":types [:6 ],"lp_locked_bucket":ss__lp_bucket (locked_pct ),
    "lp_coverage_bucket":ss__lp_bucket (coverage_pct )}


def ss__networks (report :dict )->str :
    nets =report .get ("insiderNetworks")
    if isinstance (nets ,list ):
        return ss__count_bucket (len (nets ))
    return "0"


def ss__summarize (report :dict )->dict :
    creator =report .get ("creator")if isinstance (report .get ("creator"),str )else None 
    token =report .get ("token")if isinstance (report .get ("token"),dict )else {}
    meta =report .get ("tokenMeta")if isinstance (report .get ("tokenMeta"),dict )else {}
    launchpad =report .get ("launchpad")if isinstance (report .get ("launchpad"),dict )else None 

    profile ={
    "launchpad":ss__str_or_none (launchpad .get ("name"))if launchpad else None ,
    "launchpad_platform":ss__str_or_none (launchpad .get ("platform"))if launchpad else None ,
    "deploy_platform":ss__str_or_none (report .get ("deployPlatform")),
    "detected_date":ss__date_only (report .get ("detectedAt")),
    }
    update_auth =meta .get ("updateAuthority")
    authorities ={
    "mint_authority_present":report .get ("mintAuthority")is not None or token .get ("mintAuthority")is not None ,
    "freeze_authority_present":report .get ("freezeAuthority")is not None or token .get ("freezeAuthority")is not None ,
    "metadata_mutable":meta .get ("mutable")is True ,
    "update_authority_burned":isinstance (update_auth ,str )and update_auth in ss_BURN_ADDRESSES ,
    }
    structure =ss__analyze_holders (report ,creator )
    structure ["holders_bucket"]=ss__holders_bucket (report .get ("totalHolders"))
    structure ["insider_networks"]=ss__networks (report )
    structure .update (ss__lp_and_markets (report ))
    return {"profile":profile ,"authorities":authorities ,"structure":structure ,
    "rugged":report .get ("rugged")is True }


def ss__fetch_probe (mint :str )->dict :
    if not ss__valid_mint (mint ):
        return {"ok":False ,"reason":"bad_mint"}
    try :
        res =gl .nondet .web .get (ss_RUGCHECK_BASE +mint +"/report")
    except Exception as exc :
        return {"ok":False ,"reason":"exception","error":type (exc ).__name__ }
    status =getattr (res ,"status",None )
    if not isinstance (status ,int )or isinstance (status ,bool ):
        status =0 
    if status !=200 :
        return {"ok":False ,"reason":"http","status":status }
    try :
        report =json .loads (res .body .decode ("utf-8",errors ="replace"))
    except Exception :
        return {"ok":False ,"reason":"bad_body","status":status }
    if not isinstance (report ,dict ):
        return {"ok":False ,"reason":"bad_body","status":status }
    echoed =report .get ("mint")
    if isinstance (echoed ,str )and echoed !=mint :
        return {"ok":False ,"reason":"mint_mismatch","status":status }
    out =ss__summarize (report )
    out ["ok"]=True 
    return out 


# ===== module: age_probe (prefix ag_) =====
ag_RPC_URL ="https://rpc.mainnet.chain.robinhood.com"
ag_EXPECTED_CHAIN_ID =4663 
ag_HEX_CHARS ="0123456789abcdefABCDEF"

# keccak256("getLaunchedToken(address)")[:4]
ag_SEL_GET_LAUNCHED_TOKEN ="0x3cf28b5a"
# keccak256("graduated()")[:4]
ag_SEL_GRADUATED ="0xe7c2b772"
# keccak256("TokenLaunched(address,address,address,address,uint256,uint256)")
ag_TOPIC_TOKEN_LAUNCHED ="0x8d4aad4953d0ca700d468f3753aa14432d1b35b43ec6409f051fb6aa43a89607"

# RPC menolak rentang > 10 juta blok; rantai ~83 juta blok (blok cepat)
ag_WINDOW_BLOCKS =9000000 
ag_MAX_WINDOWS =3 
# Batas jendela dibulatkan ke kelipatan ini supaya semua validator memakai
# rentang yang sama walau blok terbaru mereka beda beberapa blok.
ag_ANCHOR_ROUND =100000 
ag_MAX_LOGS_SHOWN =4 
ag_BLOCK_TRIES =3 


def ag__is_hex_data (value )->bool :
    if not isinstance (value ,str )or len (value )<2 or not value .startswith ("0x"):
        return False 
    for ch in value [2 :]:
        if ch not in ag_HEX_CHARS :
            return False 
    return True 


def ag__valid_evm_address (value )->bool :
    return ag__is_hex_data (value )and len (value )==42 


def ag__hex_to_int (value )->int :
    if not ag__is_hex_data (value )or len (value )==2 :
        return -1 
    return int (value ,16 )


def ag__to_hex (n :int )->str :
    return "0x"+format (n ,"x")


def ag__clean_text (value ,limit :int )->str :
    if isinstance (value ,str ):
        cleaned =""
        for ch in value [:limit ]:
            if ch .isprintable ():
                cleaned +=ch 
        return cleaned 
    return ""


def ag__clean_err (exc )->str :
    return type (exc ).__name__ +": "+ag__clean_text (str (exc ),80 )


def ag__rpc_payload (method :str ,params :list ,rid :int )->dict :
    return {"jsonrpc":"2.0","id":rid ,"method":method ,"params":params }


def ag__headers ()->dict :
    return {"Content-Type":"application/json","Accept":"application/json"}


def ag__parse_response (res )->dict :
    """Ringkas respons JSON-RPC. Tidak pernah melempar exception."""
    status =getattr (res ,"status",None )
    has_status =isinstance (status ,int )and not isinstance (status ,bool )
    if not has_status :
        status =0 
    if has_status and status !=200 :
        return {"kind":"http","status":status }
    try :
        data =json .loads (res .body .decode ("utf-8",errors ="replace"))
    except Exception :
        return {"kind":"bad_body","status":status }
    if not isinstance (data ,dict ):
        return {"kind":"bad_body","status":status }
    err =data .get ("error")
    if isinstance (err ,dict ):
        return {"kind":"rpc_error","status":status ,"error":ag__clean_text (err .get ("message"),80 )}
    if "result"not in data or data ["result"]is None :
        return {"kind":"bad_result","status":status }
    return {"kind":"result","status":status ,"value":data ["result"]}


def ag__call (method :str ,params :list ,rid :int )->dict :
# body berupa string: terbukti diterima SDK dan RPC (rpc_probe)
    body =json .dumps (ag__rpc_payload (method ,params ,rid ))
    try :
        res =gl .nondet .web .request (ag_RPC_URL ,method ="POST",headers =ag__headers (),body =body )
    except Exception as exc :
        return {"kind":"exception","error":ag__clean_err (exc )}
    return ag__parse_response (res )


def ag__hex_result (parsed :dict )->str :
    """Nilai hex huruf kecil dari hasil, atau '' bila bukan hex."""
    if parsed .get ("kind")!="result":
        return ""
    value =parsed .get ("value")
    if not ag__is_hex_data (value ):
        return ""
    return value .lower ()


def ag__split_words (hex_result :str )->list :
    data =hex_result [2 :]
    words =[]
    index =0 
    while index <len (data ):
        words .append (data [index :index +64 ])
        index +=64 
    return words 


def ag__all_zero (words :list )->bool :
    if len (words )==0 :
        return False 
    for w in words :
        for ch in w :
            if ch !="0":
                return False 
    return True 


def ag__word_to_address (word :str )->str :
    return "0x"+word [24 :64 ]


def ag__token_topic (token :str )->str :
    return "0x"+("0"*24 )+token [2 :].lower ()


def ag__civil_from_days (z :int ):
# algoritma Howard Hinnant (tanggal Gregorian proleptik)
    z +=719468 
    era =z //146097 
    doe =z -era *146097 
    yoe =(doe -doe //1460 +doe //36524 -doe //146096 )//365 
    y =yoe +era *400 
    doy =doe -(365 *yoe +yoe //4 -yoe //100 )
    mp =(5 *doy +2 )//153 
    d =doy -(153 *mp +2 )//5 +1 
    m =mp +3 if mp <10 else mp -9 
    if m <=2 :
        y +=1 
    return y ,m ,d 


def ag__format_utc (ts :int )->str :
    days =ts //86400 
    rem =ts -days *86400 
    y ,m ,d =ag__civil_from_days (days )
    hh =rem //3600 
    mm =(rem %3600 )//60 
    ss =rem %60 
    return (
    str (y ).zfill (4 )+"-"+str (m ).zfill (2 )+"-"+str (d ).zfill (2 )
    +"T"+str (hh ).zfill (2 )+":"+str (mm ).zfill (2 )+":"+str (ss ).zfill (2 )+"Z"
    )


def ag__summarize_logs (value )->list :
    """Ubah daftar log mentah menjadi [{'topic0','block','index'}] terurut."""
    if not isinstance (value ,list ):
        return []
    items =[]
    for entry in value :
        if not isinstance (entry ,dict ):
            continue 
        topics =entry .get ("topics")
        if not isinstance (topics ,list )or len (topics )==0 or not isinstance (topics [0 ],str ):
            continue 
        block =ag__hex_to_int (entry .get ("blockNumber"))
        if block <0 :
            continue 
        index =ag__hex_to_int (entry .get ("logIndex"))
        ts =ag__hex_to_int (entry .get ("blockTimestamp"))
        items .append ({"topic0":topics [0 ].lower (),"block":block ,"index":index ,"ts":ts })
    items .sort (key =lambda it :(it ["block"],it ["index"]))
    return items 


def ag__get_logs (factory :str ,token :str ,from_block :str ,to_block :str ,rid :int )->dict :
    flt ={
    "address":factory .lower (),
    "fromBlock":from_block ,
    "toBlock":to_block ,
    "topics":[None ,ag__token_topic (token )],
    }
    return ag__call ("eth_getLogs",[flt ],rid )


def ag__find_logs (factory :str ,token :str ):
    """Cari log factory yang menyebut token dalam MAX_WINDOWS jendela mundur dari
    blok terbaru. Mengembalikan (logs, attempts); logs None bila RPC gagal.
    Teks error RPC sengaja tidak disimpan: berisi nomor blok terbaru yang berbeda
    antar validator dan membuat strict_eq gagal."""
    attempts =[]
    latest =ag__hex_to_int (ag__hex_result (ag__call ("eth_blockNumber",[],10 )))
    if latest <0 :
        attempts .append ({"range":"latest_block","kind":"unavailable"})
        return None ,attempts 
    anchor =latest -(latest %ag_ANCHOR_ROUND )

    window =0 
    while window <ag_MAX_WINDOWS :
        end =anchor -window *ag_WINDOW_BLOCKS 
        if end <0 :
            break 
        start =end -ag_WINDOW_BLOCKS +1 
        if start <0 :
            start =0 
        to_block ="latest"if window ==0 else ag__to_hex (end )
        parsed =ag__get_logs (factory ,token ,ag__to_hex (start ),to_block ,11 +window )
        kind =parsed .get ("kind","")
        name ="w"+str (window )
        if kind =="result"and isinstance (parsed .get ("value"),list ):
            logs =ag__summarize_logs (parsed ["value"])
            attempts .append ({"range":name ,"kind":"result","count":len (logs )})
            if len (logs )>0 :
                return logs ,attempts 
        else :
            attempts .append ({"range":name ,"kind":kind ,"status":parsed .get ("status",0 )})
            return None ,attempts 
        window +=1 
    return [],attempts 


def ag__pick_launch (logs :list ):
    """Pilih log peluncuran: TokenLaunched bila ada, kalau tidak yang paling awal."""
    for item in logs :
        if item ["topic0"]==ag_TOPIC_TOKEN_LAUNCHED :
            return item ,"TokenLaunched"
    if len (logs )>0 :
        return logs [0 ],"other"
    return None ,""


def ag__fetch_probe (factory :str ,token :str )->dict :
    if not ag__valid_evm_address (factory )or not ag__valid_evm_address (token ):
        return {"ok":False ,"reason":"bad_address"}

    chain =ag__call ("eth_chainId",[],1 )
    chain_hex =ag__hex_result (chain )
    if chain_hex =="":
        return {"ok":False ,"reason":"rpc_unavailable","kind":chain .get ("kind",""),"status":chain .get ("status",0 )}
    out ={"ok":True ,"chain_id":chain_hex }
    if ag__hex_to_int (chain_hex )!=ag_EXPECTED_CHAIN_ID :
        out ["chain_ok"]=False 
        return out 
    out ["chain_ok"]=True 

    calldata =ag_SEL_GET_LAUNCHED_TOKEN +("0"*24 )+token [2 :].lower ()
    struct =ag__call ("eth_call",[{"to":factory .lower (),"data":calldata },"latest"],2 )
    struct_hex =ag__hex_result (struct )
    if struct_hex =="":
        out ["launched"]="unknown"
        out ["struct_kind"]=struct .get ("kind","")
        return out 
    words =ag__split_words (struct_hex )
    if len (words )<2 or ag__all_zero (words ):
        out ["launched"]=False 
        return out 
    out ["launched"]=True 
    curve =ag__word_to_address (words [1 ])
    out ["curve"]=curve 

    grad =ag__hex_result (ag__call ("eth_call",[{"to":curve ,"data":ag_SEL_GRADUATED },"latest"],3 ))
    grad_words =ag__split_words (grad )if grad !=""else []
    if len (grad_words )==1 :
        out ["graduated"]=int (grad_words [0 ],16 )!=0 
    else :
        out ["graduated"]=None 

    logs ,attempts =ag__find_logs (factory ,token )
    out ["log_attempts"]=attempts 
    if logs is None :
        out ["launch"]="log_query_failed"
        return out 
    out ["log_count"]=len (logs )
    out ["log_topics"]=[it ["topic0"]for it in logs [:ag_MAX_LOGS_SHOWN ]]
    chosen ,event =ag__pick_launch (logs )
    if chosen is None :
    # token memang lahir dari Pons, tetapi lebih tua dari jendela yang dipindai
        out ["launch"]="older_than_window"
        return out 
    out ["launch_event"]=event 
    out ["launch_block"]=chosen ["block"]

    # timestamp: pakai blockTimestamp dari log bila ada; kalau tidak, ambil dari
    # blok (dicoba beberapa kali karena node RPC untuk blok lama bisa tidak konsisten)
    ts =chosen ["ts"]
    if ts >0 :
        out ["block_kind"]="from_log"
    else :
        ts =-1 
        kind =""
        tries =0 
        while tries <ag_BLOCK_TRIES and ts <=0 :
            blk =ag__call ("eth_getBlockByNumber",[ag__to_hex (chosen ["block"]),False ],20 +tries )
            kind =blk .get ("kind","")
            if kind =="result"and isinstance (blk .get ("value"),dict ):
                ts =ag__hex_to_int (blk ["value"].get ("timestamp"))
                if ts <=0 :
                    kind ="no_timestamp"
            tries +=1 
        out ["block_kind"]="ok"if ts >0 else kind 
    if ts <=0 :
        out ["launch"]="block_unavailable"
        return out 
    out ["launch"]="ok"
    out ["launch_ts"]=ts 
    out ["launch_utc"]=ag__format_utc (ts )
    out ["launch_date"]=ag__format_utc (ts )[:10 ]
    return out 


# ===== module: profile_module (prefix pf_) =====
# Modul profil token (fungsi murni, tanpa jaringan). Disatukan ke kontrak v15 nanti.

pf_MIN_ESTABLISHED_MONTHS =12 
pf_ESTABLISHED_HOLDERS_EVM =[">100k","10k-100k"]
pf_CG_RANKS =["top100","top500","top2000"]
pf_CG_EXCHANGES =["5-14","15+"]
pf_CG_STABLE_RANKS =["top100","top500"]

# Stablecoin resmi (alamat dari penerbit/explorer). EVM: huruf kecil. (simbol, bridged)
pf_STABLE_EVM ={
1 :{
"0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48":("USDC",False ),
"0xdac17f958d2ee523a2206206994597c13d831ec7":("USDT",False ),
"0x6c3ea9036406852006290770bedfcaba0e23a0e8":("PYUSD",False ),
"0xe343167631d89b6ffc58b88d6b7fb0228795491d":("USDG",False ),
},
8453 :{
"0x833589fcd6edb6e08f4c7c32d4f71b54bda02913":("USDC",False ),
},
42161 :{
"0xaf88d065e77c8cc2239327c5edb3a432268e5831":("USDC",False ),
"0x46850ad61c2b7d64d08c9c754f45254596696984":("PYUSD",False ),
"0x004b506865409877c9fa29bfb1eba929984b9bbc":("USDG",False ),
"0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9":("USDT0",False ),
},
137 :{
"0x3c499c542cef5e3811e1192ce70d8cc03d5c3359":("USDC",False ),
"0x99af3eea856556646c98c8b9b2548fe815240750":("PYUSD",False ),
},
10 :{
"0x0b2c639c533813f4aa9d7837caf62653d097ff85":("USDC",False ),
"0x94b008aa00579c1307b0ef2c499ad98a8ce58e58":("USDT",True ),
},
4663 :{
"0x5fc5360d0400a0fd4f2af552add042d716f1d168":("USDG",False ),
},
}
pf_STABLE_SOLANA ={
"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v":("USDC",False ),
"Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB":("USDT",False ),
"2b1kV6DkPAnxd5ixfnxCpjxmKwqjjaYmCZfHsFu24GXo":("PYUSD",False ),
"2u1tszSeqZ3qBWF3uNGPFc8TzMk2tdiwknnRMWGWjGWH":("USDG",False ),
}
pf_STABLE_SYMBOLS =["USDC","USDT","PYUSD","USDG","USDT0"]


def pf_stablecoin_match (chain ,address ):
    """(simbol, bridged) bila alamat ada di daftar resmi, selain itu None."""
    if not isinstance (address ,str ):
        return None 
    if chain =="solana":
        return pf_STABLE_SOLANA .get (address )
    if isinstance (chain ,int )and not isinstance (chain ,bool )and chain in pf_STABLE_EVM :
        return pf_STABLE_EVM [chain ].get (address .lower ())
    return None 


def pf_is_lookalike (symbol )->bool :
    return isinstance (symbol ,str )and symbol .strip ().upper ()in pf_STABLE_SYMBOLS 


def pf__date_parts (value ):
    if not isinstance (value ,str )or len (value )<10 :
        return None 
    head =value [:10 ]
    if head [4 ]!="-"or head [7 ]!="-":
        return None 
    digits =head [:4 ]+head [5 :7 ]+head [8 :10 ]
    for ch in digits :
        if ch not in "0123456789":
            return None 
    y ,m ,d =int (head [:4 ]),int (head [5 :7 ]),int (head [8 :10 ])
    if m <1 or m >12 or d <1 or d >31 :
        return None 
    return (y ,m ,d )


def pf_age_months (start_date ,today ):
    """Umur dalam bulan penuh; None bila tanggal tidak valid atau di masa depan."""
    a =pf__date_parts (start_date )
    b =pf__date_parts (today )
    if a is None or b is None :
        return None 
    months =(b [0 ]-a [0 ])*12 +(b [1 ]-a [1 ])
    if b [2 ]<a [2 ]:
        months -=1 
    if months <0 :
        return None 
    return months 


def pf__dict (value ):
    return value if isinstance (value ,dict )else {}


def pf__stable_by_data (gp ,cg )->bool :
    """Stablecoin menurut CoinGecko: kategori stablecoin, alamat cocok, peringkat dan bursa kuat."""
    if cg .get ("ok")is not True or cg .get ("found")is not True :
        return False 
    if cg .get ("address_matches_platform")is not True or cg .get ("stablecoin_category")is not True :
        return False 
    if cg .get ("rank_bucket")not in pf_CG_STABLE_RANKS or cg .get ("exchanges_bucket")not in pf_CG_EXCHANGES :
        return False 
    return gp .get ("honeypot")!="yes"


def pf__established_evm (gp ,cg )->bool :
    if gp .get ("ok")is not True :
        return False 
    reputation =gp .get ("trust_list")=="yes"or gp .get ("cex_listed")=="yes"
    if not reputation :
        reputation =(cg .get ("ok")is True and cg .get ("found")is True 
        and cg .get ("address_matches_platform")is True 
        and cg .get ("rank_bucket")in pf_CG_RANKS 
        and cg .get ("exchanges_bucket")in pf_CG_EXCHANGES )
    if not reputation :
        return False 
    if gp .get ("holder_bucket")not in pf_ESTABLISHED_HOLDERS_EVM :
        return False 
    if gp .get ("open_source")!="yes":
        return False 
    return gp .get ("honeypot")!="yes"


def pf__established_solana (jup ,months )->bool :
    if jup .get ("ok")is not True or jup .get ("found")is not True :
        return False 
    if jup .get ("is_verified")is not True or jup .get ("organic_bucket")!="80+":
        return False 
    if jup .get ("holders_bucket")!="10000+":
        return False 
    if jup .get ("mint_authority_disabled")is not True or jup .get ("freeze_authority_disabled")is not True :
        return False 
    return months is not None and months >=pf_MIN_ESTABLISHED_MONTHS 


def pf__age_text (months )->str :
    if months is None :
        return "age unknown"
    if months <1 :
        return "less than a month old"
    if months ==1 :
        return "1 month old"
    return str (months )+" months old"


def pf_classify (ctx )->dict :
    """ctx: kind ('evm'|'solana'), chain, address, symbol, today, start_date, launchpad (bool),
    gp (probe GoPlus), cg (probe CoinGecko), jup (probe Jupiter)."""
    ctx =pf__dict (ctx )
    kind =ctx .get ("kind")
    chain =ctx .get ("chain")
    months =pf_age_months (ctx .get ("start_date"),ctx .get ("today"))
    lookalike =False 

    stable =pf_stablecoin_match (chain ,ctx .get ("address"))
    if stable is not None :
        label ="Stablecoin (bridged)"if stable [1 ]else "Stablecoin"
        reason =stable [0 ]+" at an address on our verified list"
        if stable [1 ]:
            reason +="; bridged, not issued by the original issuer"
        return {"profile":"stablecoin","label":label ,"age_months":months ,
        "reasons":[reason ],"lookalike":False }
    if kind in ("evm","solana")and pf__stable_by_data (pf__dict (ctx .get ("gp")),pf__dict (ctx .get ("cg"))):
        return {"profile":"stablecoin","label":"Stablecoin","age_months":months ,
        "reasons":["Listed as a stablecoin by CoinGecko with a strong market ranking and exchange coverage"],
        "lookalike":False }
    lookalike =pf_is_lookalike (ctx .get ("symbol"))

    established =False 
    if kind =="evm":
        established =pf__established_evm (pf__dict (ctx .get ("gp")),pf__dict (ctx .get ("cg")))
    elif kind =="solana":
        established =pf__established_solana (pf__dict (ctx .get ("jup")),months )
    if established :
        return {"profile":"established","label":"Established token","age_months":months ,
        "reasons":["Reputation, holder base and contract checks all met"],"lookalike":lookalike }

    if ctx .get ("launchpad")is True and (months is None or months <pf_MIN_ESTABLISHED_MONTHS ):
        return {"profile":"launchpad","label":"Launchpad token, "+pf__age_text (months ),
        "age_months":months ,"reasons":["Launched through a token launchpad"],
        "lookalike":lookalike }

    return {"profile":"unproven","label":"Unproven token","age_months":months ,
    "reasons":["Not enough independent signals to call it established"],
    "lookalike":lookalike }


# ===== module: market_evm (prefix me_) =====
# Modul struktur pasar EVM (fungsi murni). Menggabungkan keluaran GoPlus v2, probe Pons, dan profil.

me_LEVEL_ORDER =["none","info","caution","warn","danger"]
me_SOFT_PROFILES =["stablecoin","established"]
me_CONCENTRATION_PCT =20 # creator / owner >= 20%
me_CONTRACT_HELD_PCT =50 # kontrak tidak terkunci / terkunci >= 50%


def me_bucket_floor (bucket ):
    """'40-50%' -> 40, '90%+' -> 90; selain itu None."""
    if not isinstance (bucket ,str ):
        return None 
    if bucket .endswith ("%+"):
        head =bucket [:-2 ]
    elif bucket .endswith ("%")and "-"in bucket :
        head =bucket .split ("-")[0 ]
    else :
        return None 
    if not head .isdigit ():
        return None 
    return int (head )


def me__dict (value ):
    return value if isinstance (value ,dict )else {}


def me__flag (code ,level ,text ):
    return {"code":code ,"level":level ,"text":text }


def me_worst_level (flags )->str :
    worst =0 
    for f in flags :
        lv =f .get ("level")
        if lv in me_LEVEL_ORDER and me_LEVEL_ORDER .index (lv )>worst :
            worst =me_LEVEL_ORDER .index (lv )
    return me_LEVEL_ORDER [worst ]


def me_evm_market (gp ,pons ,profile ,months )->dict :
    gp =me__dict (gp )
    pons =me__dict (pons )
    soft =profile in me_SOFT_PROFILES 
    flags =[]
    available =gp .get ("ok")is True 

    if not available :
        flags .append (me__flag ("no_market_data","info"if soft else "caution",
        "Market data was unavailable, so holder structure could not be checked"))
    else :
        if gp .get ("honeypot")=="yes":
            flags .append (me__flag ("honeypot","danger","Flagged as a honeypot by GoPlus: selling may be impossible"))
        if gp .get ("buy_tax")=="high"or gp .get ("sell_tax")=="high":
            flags .append (me__flag ("high_tax","warn","Trading tax is above 5%"))
        if gp .get ("tax_modifiable")=="yes"and not soft :
            flags .append (me__flag ("tax_modifiable","caution","The owner can change the trading tax"))

        conc =gp .get ("wallet_concentration")
        top =gp .get ("wallet_top_bucket")
        if conc =="HIGH":
            flags .append (me__flag ("concentration","info"if soft else "warn",
            "Top wallets hold "+str (top )+" of supply (contracts and locked addresses excluded)"))
        elif conc =="ELEVATED":
            flags .append (me__flag ("concentration","info"if soft else "caution",
            "Top wallets hold "+str (top )+" of supply (contracts and locked addresses excluded)"))

        creator =me_bucket_floor (gp .get ("creator_bucket"))
        if creator is not None and creator >=me_CONCENTRATION_PCT :
            flags .append (me__flag ("creator_share","info"if soft else "caution",
            "The creator wallet holds "+str (gp .get ("creator_bucket"))+" of supply"))
        owner =me_bucket_floor (gp .get ("owner_bucket"))
        if owner is not None and owner >=me_CONCENTRATION_PCT :
            flags .append (me__flag ("owner_share","info"if soft else "caution",
            "The owner address holds "+str (gp .get ("owner_bucket"))+" of supply"))

        held =me_bucket_floor (gp .get ("contract_unlocked_bucket"))
        if held is not None and held >=me_CONTRACT_HELD_PCT :
            flags .append (me__flag ("held_in_contracts","info",
            str (gp .get ("contract_unlocked_bucket"))+" of supply sits in unlocked contracts (staking, vaults, pools or treasuries); verify what they are"))
        locked =me_bucket_floor (gp .get ("locked_bucket"))
        if locked is not None and locked >=me_CONTRACT_HELD_PCT :
            flags .append (me__flag ("locked_supply","info",
            str (gp .get ("locked_bucket"))+" of supply is in locked or burn addresses"))

        holders =gp .get ("holder_bucket")
        if holders =="<100":
            flags .append (me__flag ("few_holders","info"if soft else "caution","Fewer than 100 holders"))
        elif holders =="100-1k":
            flags .append (me__flag ("small_holder_base","info","Small holder base (100 to 1,000 holders)"))

    launched =pons .get ("launched")is True 
    if launched :
        if months is not None and months <1 :
            flags .append (me__flag ("very_young","caution","Launched less than a month ago"))
        if pons .get ("graduated")is False :
            flags .append (me__flag ("not_graduated","info","Still on the launchpad curve and not yet graduated to a DEX pool"))

    return {
    "available":available ,
    "holders":gp .get ("holder_bucket")if available else "unknown",
    "concentration":gp .get ("wallet_concentration")if available else "unknown",
    "top_wallets":gp .get ("wallet_top_bucket")if available else "unknown",
    "in_contracts":gp .get ("contract_unlocked_bucket")if available else "unknown",
    "locked":gp .get ("locked_bucket")if available else "unknown",
    "launchpad":launched ,
    "graduated":pons .get ("graduated")if launched else None ,
    "flags":flags ,
    "worst":me_worst_level (flags ),
    }


# ===== module: market_solana (prefix msol_) =====
# Modul struktur pasar Solana (fungsi murni). Menggabungkan RugCheck (struktur), Jupiter, DexScreener dan profil.

msol_LEVEL_ORDER =["none","info","caution","warn","danger"]
msol_SOFT_PROFILES =["stablecoin","established"]
msol_SHARE_PCT =20 # creator >= 20%
msol_INSIDER_WARN_PCT =30 # insider >= 30%
msol_INSIDER_CAUTION_PCT =10 # insider >= 10%


def msol_bucket_floor (bucket ):
    """'40-50%' atau '40-50' -> 40; '90%+' -> 90; selain itu None."""
    if not isinstance (bucket ,str ):
        return None 
    head =""
    if bucket .endswith ("%+"):
        head =bucket [:-2 ]
    elif "-"in bucket :
        head =bucket .split ("-")[0 ]
    if not head .isdigit ():
        return None 
    return int (head )


def msol__dict (value ):
    return value if isinstance (value ,dict )else {}


def msol__flag (code ,level ,text ):
    return {"code":code ,"level":level ,"text":text }


def msol_worst_level (flags )->str :
    worst =0 
    for f in flags :
        lv =f .get ("level")
        if lv in msol_LEVEL_ORDER and msol_LEVEL_ORDER .index (lv )>worst :
            worst =msol_LEVEL_ORDER .index (lv )
    return msol_LEVEL_ORDER [worst ]


msol_HOLDER_ORDER =["<100","100-499","500-1999","2000-9999","10000+"]


def msol_best_holders (a ,b ):
    """Dua sumber bisa berbeda (RugCheck kadang kosong untuk token besar): pakai yang lebih tinggi."""
    best =None 
    for v in (a ,b ):
        if v in msol_HOLDER_ORDER and (best is None or msol_HOLDER_ORDER .index (v )>msol_HOLDER_ORDER .index (best )):
            best =v 
    return best if best is not None else "unknown"


def msol_solana_market (rc ,jup ,dex ,profile ,months )->dict :
    rc =msol__dict (rc )
    jup =msol__dict (jup )
    dex =msol__dict (dex )
    soft =profile in msol_SOFT_PROFILES 
    flags =[]
    available =rc .get ("ok")is True 
    struct =msol__dict (rc .get ("structure"))
    auth =msol__dict (rc .get ("authorities"))
    prof =msol__dict (rc .get ("profile"))

    jup_holders =jup .get ("holders_bucket")if jup .get ("ok")is True and jup .get ("found")is True else None 
    holders_eff =msol_best_holders (struct .get ("holders_bucket"),jup_holders )
    if not available :
        flags .append (msol__flag ("no_market_data","info"if soft else "caution",
        "Market data was unavailable, so holder structure could not be checked"))
    else :
        if rc .get ("rugged")is True :
            flags .append (msol__flag ("rugged","danger","RugCheck marks this token as rugged"))
        if auth .get ("mint_authority_present")is True :
            flags .append (msol__flag ("mint_authority","info"if soft else "warn",
            "The mint authority is still active: new tokens can be created"))
        if auth .get ("freeze_authority_present")is True :
            flags .append (msol__flag ("freeze_authority","info"if soft else "warn",
            "The freeze authority is still active: holder accounts can be frozen"))
        if auth .get ("metadata_mutable")is True :
            flags .append (msol__flag ("metadata_mutable","info","Token metadata can still be changed"))

        conc =struct .get ("concentration")
        top =struct .get ("top10_bucket")
        if conc =="HIGH":
            flags .append (msol__flag ("concentration","info"if soft else "warn",
            "The top 10 holders hold "+str (top )+"% of supply (pools, lockers and burn addresses excluded)"))
        elif conc =="ELEVATED":
            flags .append (msol__flag ("concentration","info"if soft else "caution",
            "The top 10 holders hold "+str (top )+"% of supply (pools, lockers and burn addresses excluded)"))

        creator =msol_bucket_floor (struct .get ("creator_bucket"))
        if creator is not None and creator >=msol_SHARE_PCT :
            flags .append (msol__flag ("creator_share","info"if soft else "caution",
            "The creator wallet holds "+str (struct .get ("creator_bucket"))+"% of supply"))

        insider =msol_bucket_floor (struct .get ("insider_bucket"))
        if insider is not None and insider >=msol_INSIDER_WARN_PCT :
            flags .append (msol__flag ("insiders","info"if soft else "warn",
            "Insider-linked wallets hold "+str (struct .get ("insider_bucket"))+"% of supply"))
        elif insider is not None and insider >=msol_INSIDER_CAUTION_PCT :
            flags .append (msol__flag ("insiders","info"if soft else "caution",
            "Insider-linked wallets hold "+str (struct .get ("insider_bucket"))+"% of supply"))
        if struct .get ("insider_networks")=="3+":
            flags .append (msol__flag ("insider_networks","info"if soft else "caution",
            "Several linked insider wallet networks were detected"))

        lp =struct .get ("lp_locked_bucket")
        partial =struct .get ("lp_coverage_bucket")in ("0-10","10-50")
        if partial :
            flags .append (msol__flag ("liquidity_lock_partial","info",
            "The lock status can only be checked for part of the liquidity (pools without LP tokens, such as concentrated-liquidity pools, cannot be checked)"))
        elif lp =="0-10":
            flags .append (msol__flag ("liquidity_unlocked","info"if soft else "caution",
            "Almost none of the liquidity is locked or burned"))
        elif lp =="10-50":
            flags .append (msol__flag ("liquidity_partly_locked","info",
            "Less than half of the liquidity is locked or burned"))

        holders =holders_eff 
        if holders =="<100":
            flags .append (msol__flag ("few_holders","info"if soft else "caution","Fewer than 100 holders"))
        elif holders =="100-499":
            flags .append (msol__flag ("small_holder_base","info","Small holder base (100 to 499 holders)"))

    if months is not None and months <1 :
        flags .append (msol__flag ("very_young","caution","Launched less than a month ago"))

    if dex .get ("ok")is True and dex .get ("dex_paid")is True :
        flags .append (msol__flag ("dex_paid","info","Paid DexScreener promotion: a marketing signal, not a safety signal"))

    if jup .get ("ok")is True and jup .get ("found")is True :
        if jup .get ("organic_bucket")=="<50":
            flags .append (msol__flag ("low_organic","info","Low organic activity score on Jupiter"))
    elif not soft :
        flags .append (msol__flag ("no_jupiter_data","info","No token data was found on Jupiter"))

    markets =struct .get ("market_types")
    launchpad =prof .get ("launchpad")
    return {
    "available":available ,
    "holders":holders_eff if available else "unknown",
    "concentration":struct .get ("concentration")if available else "unknown",
    "top10":struct .get ("top10_bucket")if available else "unknown",
    "insiders":struct .get ("insider_bucket")if available else "unknown",
    "lp_locked":struct .get ("lp_locked_bucket")if available else "unknown",
    "lp_coverage":struct .get ("lp_coverage_bucket")if available and isinstance (struct .get ("lp_coverage_bucket"),str )else "unknown",
    "markets":list (markets )if available and isinstance (markets ,list )else [],
    "launchpad":launchpad if available and isinstance (launchpad ,str )else None ,
    "dex_paid":dex .get ("ok")is True and dex .get ("dex_paid")is True ,
    "flags":flags ,
    "worst":msol_worst_level (flags ),
    }


# ===== module: compose (prefix cp_) =====
# Penyusun hasil akhir (fungsi murni): verdict kontrak + profil + bendera pasar -> hasil akhir.

cp_LEVELS =["info","caution","warn","danger"]
cp_PROFILES =["stablecoin","established","launchpad","unproven"]
cp_DISCLAIMER ="Automated analysis. Not financial advice and not a guarantee."
cp_CONTRACT_VERDICTS =["DANGER","CENTRALIZED","CAUTION","CLEAR","INCONCLUSIVE","UNVERIFIED","NOT_ANALYZED"]
cp_LOOKALIKE_TEXT ="The name resembles a major stablecoin, but this address is not on our verified list; check the address with the issuer"


def cp__dict (value ):
    return value if isinstance (value ,dict )else {}


def cp__clean_flags (market )->list :
    out =[]
    flags =cp__dict (market ).get ("flags")
    if isinstance (flags ,list ):
        for f in flags :
            if isinstance (f ,dict )and f .get ("level")in cp_LEVELS and isinstance (f .get ("text"),str ):
                out .append ({"code":str (f .get ("code","")),"level":f ["level"],"text":f ["text"]})
    return out 


def cp__headline (verdict ,profile ,label ,has_danger ,attention ,code_unavailable =False ):
    if verdict =="DANGER"or has_danger :
        return "DANGER","danger"
    if verdict =="UNVERIFIED":
        if code_unavailable :
            return "CODE NOT AVAILABLE TO ANALYZER","caution"
        return "UNVERIFIED CONTRACT","caution"
    if verdict not in cp_CONTRACT_VERDICTS or verdict in ("INCONCLUSIVE","NOT_ANALYZED"):
        return "INCONCLUSIVE","unknown"
    if profile =="stablecoin"and not attention :
        if label =="Stablecoin (bridged)":
            return "STABLECOIN (BRIDGED)","neutral"
        return "STABLECOIN","neutral"
    if verdict =="CENTRALIZED":
        return "CENTRALIZED CONTROL","caution"
    if verdict =="CAUTION"or attention :
        return "CAUTION","caution"
    if profile =="established":
        return "NO RED FLAGS FOUND","positive"
    return "NO CONTRACT RED FLAGS","neutral"


def cp__subline (headline ,profile ,label )->str :
    if headline =="CODE NOT AVAILABLE TO ANALYZER":
        return label +". The source code is not available from Sourcify, so the contract could not be reviewed here (another data source reports it as open source)."
    if headline .startswith ("STABLECOIN"):
        return label +". Address matches the issuer's official contract; the current peg is not checked."
    if headline =="NO CONTRACT RED FLAGS":
        if profile =="launchpad":
            return label +". Contract checks passed, but reputation and age are not established."
        return "Unproven token. Contract checks passed, but reputation and age are not established."
    return label +"."


def cp_compose (contract_verdict ,profile ,market ,code_unavailable =False )->dict :
    profile =cp__dict (profile )
    pname =profile .get ("profile")if profile .get ("profile")in cp_PROFILES else "unproven"
    label =profile .get ("label")if isinstance (profile .get ("label"),str )else "Unproven token"
    flags =cp__clean_flags (market )
    if profile .get ("lookalike")is True :
        flags .append ({"code":"stablecoin_lookalike","level":"caution","text":cp_LOOKALIKE_TEXT })
    has_danger =False 
    attention =False 
    for f in flags :
        if f ["level"]=="danger":
            has_danger =True 
        elif f ["level"]in ("caution","warn"):
            attention =True 
    verdict =contract_verdict 
    headline ,tone =cp__headline (verdict ,pname ,label ,has_danger ,attention ,code_unavailable is True )

    counts ={"danger":0 ,"warn":0 ,"caution":0 ,"info":0 }
    for f in flags :
        counts [f ["level"]]+=1 
    ordered =[]
    for lvl in ["danger","warn","caution"]:
        for f in flags :
            if f ["level"]==lvl :
                ordered .append (f )
    notes =[]
    for f in flags :
        if f ["level"]=="info":
            notes .append (f ["text"])
    return {
    "headline":headline ,
    "tone":tone ,
    "contract_verdict":verdict if verdict in cp_CONTRACT_VERDICTS else "INCONCLUSIVE",
    "profile":pname ,
    "profile_label":label ,
    "subline":cp__subline (headline ,pname ,label ),
    "flags":ordered ,
    "notes":notes ,
    "counts":counts ,
    "disclaimer":cp_DISCLAIMER ,
    }


# ===== v15 glue: orchestration (pure functions plus fetch helpers) =====
PONS_CHAIN_ID = 4663
PONS_FACTORY = "0x7eD598BcEf8bd9Edd8C97A195C6d13f40801EC7e"
EVM_CHAINS = [1, 8453, 56, 4663, 42161, 137, 10]
CG_PLATFORMS = {1: "ethereum", 8453: "base", 56: "binance-smart-chain", 42161: "arbitrum-one",
                137: "polygon-pos", 10: "optimistic-ethereum"}
MIN_TODAY = "2026-10-01"


def fx_valid_today(today) -> bool:
    if not isinstance(today, str) or len(today) != 10:
        return False
    if pf_age_months("2000-01-01", today) is None:
        return False
    return today >= MIN_TODAY


def fx_valid_evm_chain(chain_id) -> bool:
    return isinstance(chain_id, int) and not isinstance(chain_id, bool) and chain_id in EVM_CHAINS


def fx_cg_tolerant_ok(leader_raw, own_raw) -> bool:
    """CoinGecko is optional: accept when either side failed (rate limit, network);
    when both succeeded the bucketed fields must match exactly."""
    try:
        a = json.loads(leader_raw)
        b = json.loads(own_raw)
    except Exception:
        return False
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    if a.get("ok") is not True or b.get("ok") is not True:
        return True
    return leader_raw == own_raw


def fx_fetch_evm_market(chain_id: int, address: str) -> dict:
    out = {"gp": gp__fetch_goplus(chain_id, address), "pons": None}
    if chain_id == PONS_CHAIN_ID:
        out["pons"] = ag__fetch_probe(PONS_FACTORY, address)
    return out


def fx_fetch_solana_market(mint: str) -> dict:
    out = {"rc": ss__fetch_probe(mint)}
    data, reason, status = ms__http_json(ms_JUPITER_URL + mint)
    out["jup"] = ms__jupiter_summary(data, mint) if reason is None else ms__fail(reason, status)
    data, reason, status = ms__http_json(ms_DEX_ORDERS_URL + mint)
    out["dex"] = ms__orders_summary(data) if reason is None else ms__fail(reason, status)
    return out


def fx_cg_fetch(platform: str, address: str) -> str:
    return json.dumps(cg__fetch_probe(platform, address), sort_keys=True)


def fx_pons_start(pons) -> tuple:
    """(start_date, launchpad) from the Pons probe output."""
    if not isinstance(pons, dict) or pons.get("ok") is not True or pons.get("chain_ok") is not True:
        return None, False
    launchpad = pons.get("launched") is True
    date = pons.get("launch_date") if pons.get("launch") == "ok" else None
    return (date if isinstance(date, str) else None), launchpad


def fx_parse_cg(raw) -> dict:
    try:
        d = json.loads(raw)
    except Exception:
        return {"ok": False}
    return d if isinstance(d, dict) else {"ok": False}


BUNDLE_WIDE_FILES = 30


def fx_bundle_flag(review):
    if isinstance(review, dict) and isinstance(review.get("project_files"), int) \
            and review["project_files"] > BUNDLE_WIDE_FILES:
        return {"code": "bundle_wide", "level": "info",
                "text": "The verified source covers a multi-contract system (" + str(review["project_files"])
                        + " project files), so the analyzer cannot tell which functions belong to this token; contract findings are capped below DANGER"}
    return None


def fx_evm_final(chain_id: int, address: str, today: str, verdict: str, mk: dict, cg: dict, review=None) -> dict:
    gp = mk.get("gp") if isinstance(mk.get("gp"), dict) else {}
    pons = mk.get("pons") if isinstance(mk.get("pons"), dict) else None
    start_date, launchpad = fx_pons_start(pons)
    symbol = gp.get("symbol") if gp.get("ok") is True else ""
    if (not isinstance(symbol, str) or symbol == "") and isinstance(cg, dict):
        symbol = cg.get("symbol")
    profile = pf_classify({"kind": "evm", "chain": chain_id, "address": address, "symbol": symbol,
                           "today": today, "start_date": start_date, "launchpad": launchpad,
                           "gp": gp, "cg": cg})
    market = me_evm_market(gp, pons, profile["profile"], profile["age_months"])
    bf = fx_bundle_flag(review)
    if bf is not None and isinstance(market.get("flags"), list):
        market["flags"].append(bf)
    final = cp_compose(verdict, profile, market, gp.get("open_source") == "yes")
    return {"profile": profile, "market": market, "final": final}


def fx_solana_verdict(rc) -> str:
    if not isinstance(rc, dict) or rc.get("ok") is not True:
        return "INCONCLUSIVE"
    if rc.get("rugged") is True:
        return "DANGER"
    auth = rc.get("authorities") if isinstance(rc.get("authorities"), dict) else {}
    mint = auth.get("mint_authority_present")
    freeze = auth.get("freeze_authority_present")
    if mint is True and freeze is True:
        return "CENTRALIZED"
    if mint is True or freeze is True:
        return "CAUTION"
    if mint is False and freeze is False:
        return "CLEAR"
    return "INCONCLUSIVE"


def fx_solana_final(mint: str, today: str, mk: dict, cg: dict) -> dict:
    rc = mk.get("rc") if isinstance(mk.get("rc"), dict) else {}
    jup = mk.get("jup") if isinstance(mk.get("jup"), dict) else {}
    dex = mk.get("dex") if isinstance(mk.get("dex"), dict) else {}
    prof = rc.get("profile") if isinstance(rc.get("profile"), dict) else {}
    start_date = jup.get("first_pool_date") if jup.get("ok") is True else None
    if not isinstance(start_date, str):
        start_date = prof.get("detected_date") if isinstance(prof.get("detected_date"), str) else None
    launchpad = (jup.get("launchpad") if jup.get("ok") is True else None) or prof.get("launchpad")
    launchpad = isinstance(launchpad, str) and launchpad != ""
    symbol = cg.get("symbol") if isinstance(cg, dict) and cg.get("ok") is True else ""
    verdict = fx_solana_verdict(rc)
    profile = pf_classify({"kind": "solana", "chain": "solana", "address": mint, "symbol": symbol,
                           "today": today, "start_date": start_date, "launchpad": launchpad,
                           "jup": jup, "cg": cg})
    market = msol_solana_market(rc, jup, dex, profile["profile"], profile["age_months"])
    final = cp_compose(verdict, profile, market)
    return {"verdict": verdict, "profile": profile, "market": market, "final": final}


class TokenSecurityScanner(gl.Contract):
    scans: TreeMap[str, str]
    scan_count: str
    history: TreeMap[str, str]

    def __init__(self) -> None:
        self.scan_count = "0"

    def _scan_key(self, chain_id: int, address: str) -> str:
        return str(chain_id) + ":" + address.lower()

    def _record(self, key: str, analysis: dict) -> None:
        # Save the full result under its key, and add a short entry to the
        # history list. History entries are numbered in the order scans finish.
        self.scans[key] = json.dumps(analysis, sort_keys=True)
        seq = int(self.scan_count) + 1
        self.scan_count = str(seq)
        entry = {
            "chain_id": analysis.get("chain_id"),
            "address": str(analysis.get("input_address", "")),
            "verdict": str(analysis.get("verdict", "")),
            "source": str(analysis.get("source", "")),
        }
        self.history[str(seq).zfill(10)] = json.dumps(entry, sort_keys=True)

    def _scan_core(self, chain_id: int, address: str) -> dict:
        def do_fetch() -> str:
            analysis = _analyze_address(chain_id, address)
            return json.dumps(analysis, sort_keys=True)

        analysis = json.loads(gl.eq_principle.strict_eq(do_fetch))

        if not analysis["verified"]:
            explanation = _unverified_explanation(analysis["is_proxy"])
            analysis["verdict"] = "UNVERIFIED"
            analysis["llm_findings"] = {"explanation": explanation}
            return analysis

        review = analysis["review"]
        prompt = _build_llm_prompt(review, analysis["is_proxy"], review["upgrade_markers"])

        def get_input() -> str:
            return prompt

        raw_llm = gl.eq_principle.prompt_non_comparative(
            get_input,
            task=LLM_TASK,
            criteria=LLM_CRITERIA,
        )
        findings, parse_ok = _parse_llm_findings_checked(raw_llm)
        analysis["llm_findings"] = findings
        analysis["llm_parse_ok"] = parse_ok
        analysis["llm_raw_excerpt"] = str(raw_llm)[:300]
        findings = _reconcile_findings(findings, review)
        analysis["llm_findings"] = findings
        analysis["verdict"] = _compute_verdict(findings, review)
        return analysis

    @gl.public.write
    def scan_token(self, chain_id: int, address: str) -> None:
        analysis = self._scan_core(chain_id, address)
        self._record(self._scan_key(chain_id, address), analysis)

    def _cg_run(self, platform: str, address: str) -> str:
        def leader() -> str:
            return fx_cg_fetch(platform, address)

        def validator(res) -> bool:
            if not isinstance(res, gl.vm.Return):
                return False
            try:
                own = fx_cg_fetch(platform, address)
            except Exception:
                own = json.dumps({"ok": False})
            return fx_cg_tolerant_ok(res.calldata, own)

        return str(gl.vm.run_nondet(leader, validator))

    @gl.public.write
    def scan_token_full(self, chain_id: int, address: str, today: str) -> None:
        if not fx_valid_evm_chain(chain_id) or not gp__valid_evm_address(address) or not fx_valid_today(today):
            raise Exception("invalid input")
        analysis = self._scan_core(chain_id, address)

        def do_market() -> str:
            return json.dumps(fx_fetch_evm_market(chain_id, address), sort_keys=True)

        mk = json.loads(gl.eq_principle.strict_eq(do_market))
        cg = {"ok": False}
        platform = CG_PLATFORMS.get(chain_id)
        if platform is not None:
            cg = fx_parse_cg(self._cg_run(platform, address))
        res = fx_evm_final(chain_id, address, today, analysis["verdict"], mk, cg, analysis.get("review"))
        analysis["profile"] = res["profile"]
        analysis["market"] = res["market"]
        analysis["final"] = res["final"]
        analysis["today"] = today
        self._record(self._scan_key(chain_id, address), analysis)

    @gl.public.write
    def scan_solana_token(self, mint: str, today: str) -> None:
        if not ss__valid_mint(mint) or not fx_valid_today(today):
            raise Exception("invalid input")

        def do_market() -> str:
            return json.dumps(fx_fetch_solana_market(mint), sort_keys=True)

        mk = json.loads(gl.eq_principle.strict_eq(do_market))
        cg = fx_parse_cg(self._cg_run("solana", mint))
        res = fx_solana_final(mint, today, mk, cg)
        analysis = {
            "chain_id": "solana",
            "input_address": mint,
            "source": "solana",
            "today": today,
            "verdict": res["verdict"],
            "profile": res["profile"],
            "market": res["market"],
            "final": res["final"],
        }
        self._record("solana:" + mint, analysis)

    @gl.public.view
    def get_solana_scan(self, mint: str) -> str:
        raw = self.scans.get("solana:" + mint)
        return raw if raw is not None else "{}"

    @gl.public.view
    def get_version(self) -> str:
        return "v15"

    @gl.public.write
    def scan_pasted_code(self, chain_id: int, address: str, pasted_code: str) -> None:
        sources = _sources_from_pasted(pasted_code)
        key = self._scan_key(chain_id, address)

        if len(sources) == 0:
            analysis = {
                "chain_id": chain_id,
                "input_address": address,
                "source": "pasted",
                "verified": False,
                "is_proxy": False,
                "proxy_type": "",
                "analyzed_address": address,
                "review": None,
                "reason": "empty_paste",
                "verdict": "NOT_ANALYZED",
                "llm_findings": None,
            }
            self._record(key, analysis)
            return

        review = _shape_review(_build_review(sources))
        analysis = {
            "chain_id": chain_id,
            "input_address": address,
            "source": "pasted",
            "verified": True,
            "is_proxy": False,
            "proxy_type": "",
            "analyzed_address": address,
            "review": review,
            "reason": "",
        }

        prompt = _build_llm_prompt(review, False, review["upgrade_markers"])

        def get_input() -> str:
            return prompt

        raw_llm = gl.eq_principle.prompt_non_comparative(
            get_input,
            task=LLM_TASK,
            criteria=LLM_CRITERIA,
        )
        findings, parse_ok = _parse_llm_findings_checked(raw_llm)
        analysis["llm_findings"] = findings
        analysis["llm_parse_ok"] = parse_ok
        analysis["llm_raw_excerpt"] = str(raw_llm)[:300]
        findings = _reconcile_findings(findings, review)
        analysis["llm_findings"] = findings
        analysis["verdict"] = _compute_verdict(findings, review)

        self._record(key, analysis)

    @gl.public.view
    def get_scan(self, chain_id: int, address: str) -> str:
        key = self._scan_key(chain_id, address)
        raw = self.scans.get(key)
        return raw if raw is not None else "{}"

    @gl.public.view
    def get_scan_count(self) -> str:
        return self.scan_count

    @gl.public.view
    def get_recent_scans(self, limit: int) -> str:
        # Newest first. A token scanned several times appears once.
        if limit < 1:
            limit = 1
        if limit > 20:
            limit = 20
        out = []
        seen = set()
        n = int(self.scan_count)
        looked = 0
        i = n
        while i >= 1 and len(out) < limit and looked < 80:
            raw = self.history.get(str(i).zfill(10))
            looked += 1
            i -= 1
            if raw is None:
                continue
            entry = json.loads(raw)
            k = str(entry.get("chain_id")) + ":" + entry.get("address", "").lower()
            if k in seen:
                continue
            seen.add(k)
            out.append(entry)
        return json.dumps(out)
