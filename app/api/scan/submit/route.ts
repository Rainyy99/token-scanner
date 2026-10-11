import { NextRequest, NextResponse } from "next/server";
import { submitScanToken, submitScanSolana, submitScanPastedCode } from "@/lib/genlayer";
import { SOLANA } from "@/lib/chains";
import { parseChainRef, addressFitsChain } from "@/lib/validate";
import { checkRateLimit } from "@/lib/rateLimit";

function getClientIp(req: NextRequest): string {
  const fwd = req.headers.get("x-forwarded-for");
  if (fwd) return fwd.split(",")[0].trim();
  return "unknown";
}

export async function POST(req: NextRequest) {
  const ip = getClientIp(req);
  const rl = checkRateLimit(ip);
  if (!rl.allowed) {
    const retryMinutes = Math.ceil((rl.retryAfterMs ?? 0) / 60000);
    return NextResponse.json(
      { error: "rate_limited", message: `Too many scans. Try again in about ${retryMinutes} minute(s).` },
      { status: 429 }
    );
  }

  let body: { chainId?: number | string; address?: string; pastedCode?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid_body", message: "Malformed JSON body." }, { status: 400 });
  }

  const { address, pastedCode } = body;

  const chain = parseChainRef(body.chainId);
  if (chain === null) {
    return NextResponse.json(
      { error: "invalid_chain_id", message: "This chain is not supported. Use Solana or one of the listed EVM chains." },
      { status: 400 }
    );
  }
  if (typeof address !== "string" || !addressFitsChain(chain, address)) {
    return NextResponse.json(
      {
        error: "invalid_address",
        message:
          chain === SOLANA
            ? "address must be a valid Solana token mint (base58, 32-44 characters)."
            : "address must be a valid 0x-prefixed 40-hex-char address.",
      },
      { status: 400 }
    );
  }
  if (pastedCode !== undefined && typeof pastedCode !== "string") {
    return NextResponse.json(
      { error: "invalid_pasted_code", message: "pastedCode must be a string." },
      { status: 400 }
    );
  }
  if (chain === SOLANA && pastedCode && pastedCode.trim() !== "") {
    return NextResponse.json(
      { error: "invalid_pasted_code", message: "Pasted source code applies to EVM contracts only." },
      { status: 400 }
    );
  }

  let result;
  if (chain === SOLANA) {
    result = await submitScanSolana(address);
  } else if (pastedCode && pastedCode.trim() !== "") {
    result = await submitScanPastedCode(chain, address, pastedCode);
  } else {
    result = await submitScanToken(chain, address);
  }

  if (!result.ok) {
    return NextResponse.json({ error: result.reason, message: result.detail }, { status: 500 });
  }

  return NextResponse.json({ txHash: result.txHash });
}
