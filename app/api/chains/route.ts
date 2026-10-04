import { NextRequest, NextResponse } from "next/server";
import { chainName } from "@/lib/chains";

export const dynamic = "force-dynamic";

const ADDRESS_RE = /^0x[a-fA-F0-9]{40}$/;
const SOURCIFY_BASE = process.env.SOURCIFY_BASE || "https://sourcify.dev";

type Found = { id: number; name: string };

// Finds every chain where this address has verified source on Sourcify.
export async function GET(req: NextRequest) {
  const address = req.nextUrl.searchParams.get("address") || "";
  if (!ADDRESS_RE.test(address)) {
    return NextResponse.json(
      { error: "invalid_address", message: "address must be a valid 0x-prefixed 40-hex-char address." },
      { status: 400 }
    );
  }

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 8000);
  try {
    const res = await fetch(`${SOURCIFY_BASE}/server/v2/contract/all-chains/${address}`, {
      signal: ctrl.signal,
      headers: { accept: "application/json" },
      cache: "no-store",
    });
    if (res.status === 404) return NextResponse.json({ chains: [] });
    if (!res.ok) {
      return NextResponse.json(
        { error: "lookup_failed", message: `Chain lookup failed (${res.status}).` },
        { status: 502 }
      );
    }
    const data = await res.json();
    const list: unknown[] = Array.isArray(data)
      ? data
      : Array.isArray(data?.results)
        ? data.results
        : Array.isArray(data?.contracts)
          ? data.contracts
          : [];

    const seen = new Set<number>();
    const chains: Found[] = [];
    for (const item of list) {
      if (!item || typeof item !== "object") continue;
      const rec = item as { chainId?: string | number; match?: string | null };
      const id = Number(rec.chainId);
      if (!Number.isInteger(id) || id <= 0 || seen.has(id)) continue;
      if (rec.match === null || rec.match === undefined) continue;
      seen.add(id);
      chains.push({ id, name: chainName(id) });
    }
    chains.sort((a, b) => a.id - b.id);
    return NextResponse.json({ chains });
  } catch {
    return NextResponse.json(
      { error: "lookup_failed", message: "Could not look up this address right now." },
      { status: 502 }
    );
  } finally {
    clearTimeout(timer);
  }
}
