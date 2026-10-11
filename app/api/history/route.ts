import { NextRequest, NextResponse } from "next/server";
import { getRecentScans, getStoredScanResult } from "@/lib/genlayer";
import { parseChainRef, addressFitsChain } from "@/lib/validate";

export const dynamic = "force-dynamic";

// GET /api/history                       -> the 10 most recent scans
// GET /api/history?chainId=1&address=0x  -> the full saved result for one scan
export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const chainIdRaw = sp.get("chainId");
  const address = sp.get("address");

  if (chainIdRaw || address) {
    const chainId = parseChainRef(chainIdRaw);
    if (chainId === null || !address || !addressFitsChain(chainId, address)) {
      return NextResponse.json(
        { error: "invalid_params", message: "chainId must be a supported chain and address valid for it." },
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
