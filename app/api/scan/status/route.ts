import { NextRequest, NextResponse } from "next/server";
import { checkScanStatus } from "@/lib/genlayer";

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const txHash = searchParams.get("hash");
  const chainIdRaw = searchParams.get("chainId");
  const address = searchParams.get("address");

  if (!txHash || !txHash.startsWith("0x")) {
    return NextResponse.json({ error: "invalid_hash", message: "hash query param is required." }, { status: 400 });
  }
  const chainId = Number(chainIdRaw);
  if (!chainIdRaw || !Number.isInteger(chainId) || chainId <= 0) {
    return NextResponse.json(
      { error: "invalid_chain_id", message: "chainId query param must be a positive integer." },
      { status: 400 }
    );
  }
  if (!address) {
    return NextResponse.json({ error: "invalid_address", message: "address query param is required." }, { status: 400 });
  }

  const result = await checkScanStatus(txHash, chainId, address);
  console.log("[scan/status]", txHash, JSON.stringify(result));
  return NextResponse.json(result);
}
