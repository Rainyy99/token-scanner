import { createClient, createAccount } from "genlayer-js";
import { studionet } from "genlayer-js/chains";
import { TransactionStatus, DECIDED_STATES } from "genlayer-js/types";

const CONTRACT_ADDRESS = process.env.CONTRACT_ADDRESS as `0x${string}`;
const OPERATOR_PRIVATE_KEY = process.env.OPERATOR_PRIVATE_KEY as `0x${string}`;

function getOperatorClient() {
  if (!OPERATOR_PRIVATE_KEY) {
    throw new Error("OPERATOR_PRIVATE_KEY is not set");
  }
  const account = createAccount(OPERATOR_PRIVATE_KEY);
  return createClient({ chain: studionet, account });
}

function getReadClient() {
  return createClient({ chain: studionet });
}

// ---- Submit (fast, does not wait for consensus) ----

export type SubmitResult =
  | { ok: true; txHash: string }
  | { ok: false; reason: "config_error"; detail: string };

async function submitWrite(
  functionName: "scan_token" | "scan_pasted_code",
  args: unknown[]
): Promise<SubmitResult> {
  if (!CONTRACT_ADDRESS) {
    return { ok: false, reason: "config_error", detail: "CONTRACT_ADDRESS is not set" };
  }
  let client;
  try {
    client = getOperatorClient();
  } catch (e) {
    return { ok: false, reason: "config_error", detail: String(e) };
  }

  const txHash = await client.writeContract({
    address: CONTRACT_ADDRESS,
    functionName,
    args: args as never,
    value: 0n,
  });

  return { ok: true, txHash: txHash as string };
}

export async function submitScanToken(chainId: number, address: string): Promise<SubmitResult> {
  return submitWrite("scan_token", [chainId, address]);
}

export async function submitScanPastedCode(
  chainId: number,
  address: string,
  pastedCode: string
): Promise<SubmitResult> {
  return submitWrite("scan_pasted_code", [chainId, address, pastedCode]);
}

// ---- Status check (single, non-blocking check — meant to be polled) ----

export type StatusResult =
  | { status: "pending"; statusName?: string }
  | { status: "failed"; reason: "undetermined" | "execution_error" | string; detail: string }
  | { status: "done"; result: unknown };

export async function checkScanStatus(
  txHash: string,
  chainId: number,
  address: string
): Promise<StatusResult> {
  const client = getReadClient();

  let tx;
  try {
    tx = await client.getTransaction({ hash: txHash as never });
  } catch (e) {
    // Transaction not found yet (e.g. not yet indexed) — treat as still pending.
    return { status: "pending", statusName: "not_found_yet: " + String(e) };
  }

  const statusName = tx.statusName;

  if (!statusName || !DECIDED_STATES.includes(statusName)) {
    return { status: "pending", statusName };
  }

  if (statusName === TransactionStatus.UNDETERMINED) {
    return {
      status: "failed",
      reason: "undetermined",
      detail: "Validators could not reach consensus on this scan. Please try again.",
    };
  }

  if (statusName !== TransactionStatus.ACCEPTED && statusName !== TransactionStatus.FINALIZED) {
    return {
      status: "failed",
      reason: statusName,
      detail: "Transaction ended in state: " + statusName,
    };
  }

  if (tx.txExecutionResultName === "FINISHED_WITH_ERROR") {
    return {
      status: "failed",
      reason: "execution_error",
      detail: "Contract execution failed.",
    };
  }

  // ACCEPTED or FINALIZED with a successful execution result: read the scan.
  if (!CONTRACT_ADDRESS) {
    return { status: "failed", reason: "config_error", detail: "CONTRACT_ADDRESS is not set" };
  }
  let scanJson: string;
  try {
    scanJson = (await client.readContract({
      address: CONTRACT_ADDRESS,
      functionName: "get_scan",
      args: [chainId, address],
    })) as string;
  } catch (e) {
    return { status: "failed", reason: "read_failed", detail: String(e) };
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(scanJson);
  } catch {
    return { status: "failed", reason: "parse_failed", detail: "Could not parse scan result." };
  }

  return { status: "done", result: parsed };
}
