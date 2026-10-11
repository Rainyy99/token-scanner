import { NextRequest, NextResponse } from "next/server";
import { checkScanStatus } from "@/lib/genlayer";
import { parseChainRef, addressFitsChain } from "@/lib/validate";

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const txHash = searchParams.get("hash");
  const chainIdRaw = searchParams.get("chainId");
  const address = searchParams.get("address");

  if (!txHash || !txHash.startsWith("0x")) {
    return NextResponse.json({ error: "invalid_hash", message: "hash query param is required." }, { status: 400 });
  }
  const chain = parseChainRef(chainIdRaw);
  if (chain === null) {
    return NextResponse.json(
      { error: "invalid_chain_id", message: "chainId query param is not a supported chain." },
      { status: 400 }
    );
  }
  if (!address || !addressFitsChain(chain, address)) {
    return NextResponse.json({ error: "invalid_address", message: "address query param is not valid for this chain." }, { status: 400 });
  }

  const result = await checkScanStatus(txHash, chain, address);
  return NextResponse.json(result);
}
