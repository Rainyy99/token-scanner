"use client";

import { useState, useRef } from "react";

type PollResult =
  | { status: "pending"; statusName?: string }
  | { status: "failed"; reason: string; detail: string }
  | { status: "done"; result: unknown };

type StoredScan = { txHash: string; submittedAt: number };

const STALE_MS = 15 * 60 * 1000; // 15 minutes

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
  const [chainId, setChainId] = useState("");
  const [address, setAddress] = useState("");
  const [pastedCode, setPastedCode] = useState("");
  const [phase, setPhase] = useState<"idle" | "submitting" | "polling" | "done" | "error">("idle");
  const [message, setMessage] = useState<string>("");
  const [result, setResult] = useState<unknown>(null);
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

  async function handleScan(e: React.FormEvent) {
    e.preventDefault();
    stopPolling();
    setResult(null);

    const chainIdNum = Number(chainId);

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

  return (
    <main style={{ maxWidth: 640, margin: "0 auto", padding: 24, fontFamily: "monospace" }}>
      <h1>Token Security Scanner</h1>
      <form onSubmit={handleScan}>
        <div>
          <label>Chain ID</label>
          <br />
          <input value={chainId} onChange={(e) => setChainId(e.target.value)} />
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
        <button type="submit" disabled={phase === "submitting" || phase === "polling"} style={{ marginTop: 12 }}>
          {phase === "submitting" || phase === "polling" ? "Scanning..." : "Scan"}
        </button>
      </form>

      <p style={{ marginTop: 12, fontSize: 13, opacity: 0.7 }}>
        Note: large, multi-file or proxy contracts can take longer and sometimes fail validator consensus.
        If that happens, paste the contract&apos;s source code directly.
      </p>

      {message && (phase === "submitting" || phase === "polling" || phase === "error") && (
        <p style={{ marginTop: 16, color: phase === "error" ? "red" : undefined }}>{message}</p>
      )}

      {phase === "done" && result !== null && (
        <pre style={{ marginTop: 24, whiteSpace: "pre-wrap", background: "#111", color: "#0f0", padding: 12 }}>
          {JSON.stringify(result, null, 2)}
        </pre>
      )}
    </main>
  );
}
