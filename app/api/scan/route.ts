import { NextRequest, NextResponse } from "next/server";
import { runScanToken, runScanPastedCode, getScan } from "@/lib/genlayer";
import { checkRateLimit } from "@/lib/rateLimit";

const ADDRESS_RE = /^0x[a-fA-F0-9]{40}$/;

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

  let body: { chainId?: number; address?: string; pastedCode?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid_body", message: "Malformed JSON body." }, { status: 400 });
  }

  const { chainId, address, pastedCode } = body;

  if (typeof chainId !== "number" || !Number.isInteger(chainId) || chainId <= 0) {
    return NextResponse.json(
      { error: "invalid_chain_id", message: "chainId must be a positive integer." },
      { status: 400 }
    );
  }
  if (typeof address !== "string" || !ADDRESS_RE.test(address)) {
    return NextResponse.json(
      { error: "invalid_address", message: "address must be a valid 0x-prefixed 40-hex-char address." },
      { status: 400 }
    );
  }
  if (pastedCode !== undefined && typeof pastedCode !== "string") {
    return NextResponse.json(
      { error: "invalid_pasted_code", message: "pastedCode must be a string." },
      { status: 400 }
    );
  }

  const runResult =
    pastedCode && pastedCode.trim() !== ""
      ? await runScanPastedCode(chainId, address, pastedCode)
      : await runScanToken(chainId, address);

  if (!runResult.ok) {
    const statusMap: Record<string, number> = {
      undetermined: 503,
      execution_error: 502,
      timeout: 504,
      config_error: 500,
    };
    return NextResponse.json(
      { error: runResult.reason, message: runResult.detail },
      { status: statusMap[runResult.reason] ?? 500 }
    );
  }

  let scanJson: string;
  try {
    scanJson = await getScan(chainId, address);
  } catch (e) {
    return NextResponse.json(
      { error: "read_failed", message: "Scan completed but reading the result failed: " + String(e) },
      { status: 500 }
    );
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(scanJson);
  } catch {
    return NextResponse.json(
      { error: "parse_failed", message: "Could not parse scan result from the contract." },
      { status: 500 }
    );
  }

  return NextResponse.json({ result: parsed });
}
