"use client";

import { useState } from "react";

type ScanResponse = {
  result?: unknown;
  error?: string;
  message?: string;
};

export default function Home() {
  const [chainId, setChainId] = useState("4663");
  const [address, setAddress] = useState("");
  const [pastedCode, setPastedCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<ScanResponse | null>(null);

  async function handleScan(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setResponse(null);
    try {
      const res = await fetch("/api/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chainId: Number(chainId),
          address,
          pastedCode: pastedCode.trim() === "" ? undefined : pastedCode,
        }),
      });
      const data: ScanResponse = await res.json();
      setResponse(data);
    } catch (err) {
      setResponse({ error: "network_error", message: String(err) });
    } finally {
      setLoading(false);
    }
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
        <button type="submit" disabled={loading} style={{ marginTop: 12 }}>
          {loading ? "Scanning..." : "Scan"}
        </button>
      </form>

      {response && (
        <pre style={{ marginTop: 24, whiteSpace: "pre-wrap", background: "#111", color: "#0f0", padding: 12 }}>
          {JSON.stringify(response, null, 2)}
        </pre>
      )}
    </main>
  );
}
