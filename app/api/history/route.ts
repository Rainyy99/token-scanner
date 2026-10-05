import { NextRequest, NextResponse } from "next/server";
import { getRecentScans, getStoredScanResult } from "@/lib/genlayer";

export const dynamic = "force-dynamic";

const ADDRESS_RE = /^0x[a-fA-F0-9]{40}$/;

// GET /api/history                       -> the 10 most recent scans
// GET /api/history?chainId=1&address=0x  -> the full saved result for one scan
export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const chainIdRaw = sp.get("chainId");
  const address = sp.get("address");

  if (chainIdRaw || address) {
    const chainId = Number(chainIdRaw);
    if (!Number.isInteger(chainId) || chainId <= 0 || !address || !ADDRESS_RE.test(address)) {
      return NextResponse.json(
        { error: "invalid_params", message: "chainId must be a positive integer and address a valid 0x address." },
        { status: 400 }
      );
    }
    try {
      const result = await getStoredScanResult(chainId, address);
      if (!result) {
        return NextResponse.json({ error: "not_found", message: "No saved scan for this token." }, { status: 404 });
      }
      return NextResponse.json({ result });
    } catch {
      return NextResponse.json(
        { error: "read_failed", message: "Could not load this scan right now." },
        { status: 502 }
      );
    }
  }

  try {
    return NextResponse.json({ scans: await getRecentScans(10) });
  } catch {
    // Older contract without history, or a read error: show no history instead of failing the page.
    return NextResponse.json({ scans: [] });
  }
}
