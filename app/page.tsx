"use client";

import { useState, useRef, useEffect } from "react";
import ResultCard, { type ScanResult } from "./ResultCard";
import { POPULAR_CHAINS, chainLabel, type ChainOption } from "@/lib/chains";

type PollResult =
  | { status: "pending"; statusName?: string }
  | { status: "failed"; reason: string; detail: string }
  | { status: "done"; result: unknown };

type StoredScan = { txHash: string; submittedAt: number };
type HistoryItem = { chain_id: number; address: string; verdict: string; source: string };

const VERDICT_COLOR: Record<string, string> = {
  DANGER: "#b23a2e",
  CENTRALIZED: "#3f6682",
  CAUTION: "#b8832e",
  CLEAR: "#2e6b55",
};

function shortAddr(a: string): string {
  return a.length > 14 ? a.slice(0, 6) + "…" + a.slice(-4) : a;
}

const STALE_MS = 15 * 60 * 1000; // 15 minutes
const ADDRESS_RE = /^0x[a-fA-F0-9]{40}$/;

function scanKey(chainId: number, address: string): string {
  return `scan:${chainId}:${address.toLowerCase()}`;
}

function getStoredScan(chainId: number, address: string): StoredScan | null {
  try {
    const raw = localStorage.getItem(scanKey(chainId, address));
    if (!raw) return null;
    const parsed: StoredScan = JSON.parse(raw);
    if (Date.now() - parsed.submittedAt > STALE_MS) {
      localStorage.removeItem(scanKey(chainId, address));
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function setStoredScan(chainId: number, address: string, txHash: string) {
  try {
    const entry: StoredScan = { txHash, submittedAt: Date.now() };
    localStorage.setItem(scanKey(chainId, address), JSON.stringify(entry));
  } catch {
    // localStorage unavailable (e.g. private mode) — dedup just won't work, non-fatal.
  }
}

function clearStoredScan(chainId: number, address: string) {
  try {
    localStorage.removeItem(scanKey(chainId, address));
  } catch {
    // ignore
  }
}

export default function Home() {
  const [chainSel, setChainSel] = useState("auto"); // "auto" | chain id | "other"
  const [customChain, setCustomChain] = useState("");
  const [address, setAddress] = useState("");
  const [pastedCode, setPastedCode] = useState("");
  const [phase, setPhase] = useState<"idle" | "detecting" | "choose" | "submitting" | "polling" | "done" | "error">("idle");
  const [message, setMessage] = useState<string>("");
  const [result, setResult] = useState<unknown>(null);
  const [picker, setPicker] = useState<ChainOption[] | null>(null);
  const [alsoOn, setAlsoOn] = useState<ChainOption[]>([]);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const resultRef = useRef<HTMLDivElement | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);

  async function loadHistory() {
    try {
      const res = await fetch("/api/history");
      const data = await res.json();
      setHistory(Array.isArray(data.scans) ? data.scans : []);
    } catch {
      // history is optional; ignore failures
    }
  }

  useEffect(() => {
    loadHistory();
  }, []);

  useEffect(() => {
    if (phase === "done" && resultRef.current) {
      resultRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [phase, result]);

  async function openHistory(item: HistoryItem) {
    stopPolling();
    setPicker(null);
    setAlsoOn([]);
    setResult(null);
    setPhase("detecting");
    setMessage("Opening saved scan...");
    try {
      const res = await fetch(`/api/history?chainId=${item.chain_id}&address=${item.address}`);
      const data = await res.json();
      if (!res.ok || !data.result) {
        setPhase("error");
        setMessage(data.message || "Could not load this scan.");
        return;
      }
      setResult(data.result);
      setPhase("done");
    } catch (err) {
      setPhase("error");
      setMessage(String(err));
    }
  }

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  function startPolling(txHash: string, chainIdNum: number, addr: string) {
    setPhase("polling");
    setMessage("Waiting for validator consensus...");
    const startedAt = Date.now();

    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/api/scan/status?hash=${txHash}&chainId=${chainIdNum}&address=${addr}`);
        const data: PollResult = await res.json();

        if (data.status === "pending") {
          if (Date.now() - startedAt > 75000) {
            setMessage(
              "Still working. Large, multi-file or proxy contracts take longer and are more likely to fail validator consensus."
            );
          } else {
            setMessage("Waiting for validator consensus" + (data.statusName ? ` (${data.statusName})` : "..."));
          }
          return;
        }
        stopPolling();
        clearStoredScan(chainIdNum, addr);
        if (data.status === "failed") {
          setPhase("error");
          setMessage(
            data.reason === "undetermined"
              ? "Validators could not reach consensus on this scan. This is more common with large or proxy contracts. Try again, or paste the contract's source code directly in the field above."
              : data.detail
          );
          return;
        }
        if (data.status === "done") {
          setPhase("done");
          setResult(data.result);
          loadHistory();
        }
      } catch (err) {
        stopPolling();
        clearStoredScan(chainIdNum, addr);
        setPhase("error");
        setMessage(String(err));
      }
    }, 3000);
  }

  async function runScan(chainIdNum: number, others: ChainOption[]) {
    setPicker(null);
    setAlsoOn(others);

    // If a scan for this exact token is already in flight (e.g. the user
    // refreshed the page and clicked Scan again), resume polling it
    // instead of submitting a brand new transaction.
    const existing = getStoredScan(chainIdNum, address);
    if (existing) {
      startPolling(existing.txHash, chainIdNum, address);
      return;
    }

    setPhase("submitting");
    setMessage("Submitting scan...");

    let txHash: string;
    try {
      const res = await fetch("/api/scan/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chainId: chainIdNum,
          address,
          pastedCode: pastedCode.trim() === "" ? undefined : pastedCode,
        }),
      });
      const data = await res.json();
      if (!res.ok || !data.txHash) {
        setPhase("error");
        setMessage(data.message || "Failed to submit scan.");
        return;
      }
      txHash = data.txHash;
    } catch (err) {
      setPhase("error");
      setMessage(String(err));
      return;
    }

    setStoredScan(chainIdNum, address, txHash);
    startPolling(txHash, chainIdNum, address);
  }

  async function handleScan(e: React.FormEvent) {
    e.preventDefault();
    stopPolling();
    setResult(null);
    setPicker(null);
    setAlsoOn([]);

    const addr = address.trim();
    if (!ADDRESS_RE.test(addr)) {
      setPhase("error");
      setMessage("Enter a valid token address (0x followed by 40 hex characters).");
      return;
    }
    if (addr !== address) setAddress(addr);

    // Chain picked by hand: scan it directly.
    if (chainSel !== "auto") {
      const idNum = chainSel === "other" ? Number(customChain) : Number(chainSel);
      if (!Number.isInteger(idNum) || idNum <= 0) {
        setPhase("error");
        setMessage("Enter a valid chain ID (a positive whole number).");
        return;
      }
      await runScan(idNum, []);
      return;
    }

    // Auto-detect: ask Sourcify where this address is verified.
    setPhase("detecting");
    setMessage("Detecting chain...");
    let found: ChainOption[] = [];
    try {
      const res = await fetch(`/api/chains?address=${addr}`);
      const data = await res.json();
      if (!res.ok) {
        setPhase("error");
        setMessage("Could not detect the chain right now. Pick a chain from the list and try again.");
        return;
      }
      found = Array.isArray(data.chains) ? data.chains : [];
    } catch {
      setPhase("error");
      setMessage("Could not detect the chain right now. Pick a chain from the list and try again.");
      return;
    }

    if (found.length === 0) {
      setPhase("error");
      setMessage(
        pastedCode.trim() === ""
          ? "No verified source found for this address on any chain. Pick a chain from the list, or paste the source code."
          : "Chain not detected. Pick the chain this contract is on, then scan again."
      );
      return;
    }
    if (found.length === 1) {
      await runScan(found[0].id, []);
      return;
    }
    setPicker(found);
    setPhase("choose");
    setMessage("");
  }

  async function chooseChain(c: ChainOption) {
    stopPolling();
    await runScan(
      c.id,
      (picker || []).filter((x) => x.id !== c.id)
    );
  }

  const busy = phase === "detecting" || phase === "submitting" || phase === "polling";

  return (
    <main className="ts-page">
      <h1 className="ts-title">Token Security Scanner</h1>
      <p className="ts-lede">
        Paste a token address. Reviewers read its verified source code and report which powers
        its owner holds: minting, freezing, pausing and upgrading.
      </p>

      <form className="ts-form" onSubmit={handleScan}>
        <div className="ts-field">
          <label className="ts-label" htmlFor="address">
            Token address
          </label>
          <input
            id="address"
            className="ts-input"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="0x..."
            autoComplete="off"
            autoCapitalize="off"
            spellCheck={false}
          />
        </div>

        <div className="ts-field">
          <label className="ts-label" htmlFor="chain">
            Chain <span>(optional)</span>
          </label>
          <select
            id="chain"
            className="ts-select"
            value={chainSel}
            onChange={(e) => setChainSel(e.target.value)}
          >
            <option value="auto">Auto-detect (recommended)</option>
            {POPULAR_CHAINS.map((c) => (
              <option key={c.id} value={String(c.id)}>
                {c.name} · {c.id}
              </option>
            ))}
            <option value="other">Other (enter chain ID)…</option>
          </select>
          {chainSel === "other" && (
            <input
              className="ts-input"
              value={customChain}
              onChange={(e) => setCustomChain(e.target.value)}
              inputMode="numeric"
              placeholder="Chain ID, e.g. 59144"
              aria-label="Chain ID"
            />
          )}
          <p className="ts-hint">Leave on Auto-detect and the scanner finds the chain from the address.</p>
        </div>

        <div className="ts-field">
          <label className="ts-label" htmlFor="code">
            Source code <span>(optional)</span>
          </label>
          <textarea
            id="code"
            className="ts-textarea"
            value={pastedCode}
            onChange={(e) => setPastedCode(e.target.value)}
            placeholder="Only needed if the contract is not verified on Sourcify."
            spellCheck={false}
          />
        </div>

        <button type="submit" className="ts-submit" disabled={busy}>
          {busy ? "Scanning..." : "Scan token"}
        </button>

        <p className="ts-note">
          Large, multi-file or proxy contracts take longer and sometimes fail validator consensus.
          If that happens, paste the contract&apos;s source code directly.
        </p>
      </form>

      {phase === "choose" && picker && (
        <div className="ts-choose">
          <p>This address is verified on several chains. Which one do you want to scan?</p>
          <div className="ts-chips">
            {picker.map((c) => (
              <button key={c.id} type="button" className="ts-chip" onClick={() => chooseChain(c)}>
                {chainLabel(c.id)}
              </button>
            ))}
          </div>
        </div>
      )}

      {message && (phase === "detecting" || phase === "submitting" || phase === "polling") && (
        <p className="ts-status" role="status">
          <span className="ts-dots" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          {message}
        </p>
      )}

      {message && phase === "error" && (
        <p className="ts-error" role="alert">
          {message}
        </p>
      )}

      <div ref={resultRef}>
        {phase === "done" && result !== null && (
          <ResultCard result={result as ScanResult} alsoOn={alsoOn} />
        )}
      </div>

      {history.length > 0 && (
        <section className="ts-history" aria-label="Recent scans">
          <h2 className="ts-history-title">Recent scans</h2>
          <ul className="ts-history-list">
            {history.map((h) => (
              <li key={h.chain_id + ":" + h.address.toLowerCase()}>
                <button type="button" className="ts-history-row" onClick={() => openHistory(h)} disabled={busy}>
                  <span
                    className="ts-history-verdict"
                    style={{ background: VERDICT_COLOR[h.verdict] || "#5b5e66" }}
                  >
                    {h.verdict === "UNVERIFIED" ? "Unverified" : h.verdict.charAt(0) + h.verdict.slice(1).toLowerCase()}
                  </span>
                  <span className="ts-history-addr">{shortAddr(h.address)}</span>
                  <span className="ts-history-chain">{chainLabel(h.chain_id)}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
