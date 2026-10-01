"use client";

import { useState, useRef } from "react";

type PollResult =
  | { status: "pending"; statusName?: string }
  | { status: "failed"; reason: string; detail: string }
  | { status: "done"; result: unknown };

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

  async function handleScan(e: React.FormEvent) {
    e.preventDefault();
    stopPolling();
    setResult(null);
    setPhase("submitting");
    setMessage("Submitting scan...");

    let txHash: string;
    try {
      const res = await fetch("/api/scan/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chainId: Number(chainId),
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

    setPhase("polling");
    setMessage("Waiting for validator consensus...");

    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(
          `/api/scan/status?hash=${txHash}&chainId=${Number(chainId)}&address=${address}`
        );
        const data: PollResult = await res.json();

        if (data.status === "pending") {
          setMessage("Waiting for validator consensus" + (data.statusName ? ` (${data.statusName})` : "..."));
          return;
        }
        stopPolling();
        if (data.status === "failed") {
          setPhase("error");
          setMessage(data.detail);
          return;
        }
        if (data.status === "done") {
          setPhase("done");
          setResult(data.result);
        }
      } catch (err) {
        stopPolling();
        setPhase("error");
        setMessage(String(err));
      }
    }, 3000);
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
