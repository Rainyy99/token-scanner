"use client";

import { useState, useRef } from "react";
import ResultCard, { type ScanResult } from "./ResultCard";
import { POPULAR_CHAINS, chainLabel, type ChainOption } from "@/lib/chains";

type PollResult =
  | { status: "pending"; statusName?: string }
  | { status: "failed"; reason: string; detail: string }
  | { status: "done"; result: unknown };

type StoredScan = { txHash: string; submittedAt: number };

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
    <main style={{ maxWidth: 640, margin: "0 auto", padding: 24, fontFamily: "monospace" }}>
      <h1>Token Security Scanner</h1>
      <form onSubmit={handleScan}>
        <div>
          <label htmlFor="chain">
            Chain <span style={{ opacity: 0.6 }}>(optional)</span>
          </label>
          <br />
          <select
            id="chain"
            value={chainSel}
            onChange={(e) => setChainSel(e.target.value)}
            style={{ width: "100%" }}
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
              value={customChain}
              onChange={(e) => setCustomChain(e.target.value)}
              inputMode="numeric"
              placeholder="Chain ID, e.g. 59144"
              style={{ width: "100%", marginTop: 6 }}
            />
          )}
          <div style={{ fontSize: 12, opacity: 0.65, marginTop: 4 }}>
            Leave on Auto-detect and just paste the token address.
          </div>
        </div>
        <div style={{ marginTop: 8 }}>
          <label>Token address</label>
          <br />
          <input
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="0x..."
            style={{ width: "100%" }}
          />
        </div>
        <div style={{ marginTop: 8 }}>
          <label>Pasted source code (optional)</label>
          <br />
          <textarea
            value={pastedCode}
            onChange={(e) => setPastedCode(e.target.value)}
            rows={6}
            style={{ width: "100%" }}
          />
        </div>
        <button type="submit" disabled={busy} style={{ marginTop: 12 }}>
          {busy ? "Scanning..." : "Scan"}
        </button>
      </form>

      <p style={{ marginTop: 12, fontSize: 13, opacity: 0.7 }}>
        Note: large, multi-file or proxy contracts can take longer and sometimes fail validator consensus.
        If that happens, paste the contract&apos;s source code directly.
      </p>

      {phase === "choose" && picker && (
        <div style={{ marginTop: 16 }}>
          <p>This address is verified on several chains. Which one do you want to scan?</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {picker.map((c) => (
              <button key={c.id} type="button" onClick={() => chooseChain(c)}>
                {chainLabel(c.id)}
              </button>
            ))}
          </div>
        </div>
      )}

      {message && (phase === "detecting" || phase === "submitting" || phase === "polling" || phase === "error") && (
        <p style={{ marginTop: 16, color: phase === "error" ? "red" : undefined }}>{message}</p>
      )}

      {phase === "done" && result !== null && (
        <ResultCard result={result as ScanResult} alsoOn={alsoOn} />
      )}
    </main>
  );
}
