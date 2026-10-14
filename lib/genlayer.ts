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
  functionName: "scan_token" | "scan_pasted_code" | "scan_token_full" | "scan_solana_token",
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

// The contract needs today's date (YYYY-MM-DD, UTC) because validators have no clock.
export function todayUtc(): string {
  return new Date().toISOString().slice(0, 10);
}

export async function submitScanToken(chainId: number, address: string): Promise<SubmitResult> {
  return submitWrite("scan_token_full", [chainId, address, todayUtc()]);
}

export async function submitScanSolana(mint: string): Promise<SubmitResult> {
  return submitWrite("scan_solana_token", [mint, todayUtc()]);
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
  | { status: "done"; result: unknown; execution: "success" };

// Reads the leader's execution result from the receipt. Returns "success", "error" or "unknown".
function executionOutcome(tx: unknown): "success" | "error" | "unknown" {
  const t = tx as Record<string, any>;
  const named = String(t?.txExecutionResultName ?? t?.tx_execution_result_name ?? "");
  if (named === "FINISHED_WITH_ERROR") return "error";
  const lr = t?.consensus_data?.leader_receipt ?? t?.consensusData?.leaderReceipt;
  const entries: any[] = Array.isArray(lr) ? lr : lr ? [lr] : [];
  const leaders = entries.filter((e) => !e?.mode || String(e.mode).toLowerCase() === "leader");
  let sawSuccess = named === "FINISHED_WITH_RETURN";
  for (const e of leaders) {
    const r = String(e?.execution_result ?? e?.executionResult ?? "").toUpperCase();
    const st = String(e?.result?.status ?? "").toLowerCase();
    if (r === "ERROR" || st === "contract_error" || st === "error") return "error";
    if (r === "SUCCESS" || st === "return" || st === "success") sawSuccess = true;
  }
  return sawSuccess ? "success" : "unknown";
}

// Read-only description of how a transaction's execution was judged (for /api/scan/status?debug=1).
export async function describeExecution(txHash: string) {
  const tx = (await getReadClient().getTransaction({ hash: txHash as never })) as Record<string, any>;
  const lr = tx?.consensus_data?.leader_receipt ?? tx?.consensusData?.leaderReceipt;
  const entries: any[] = Array.isArray(lr) ? lr : lr ? [lr] : [];
  return {
    statusName: tx?.statusName ?? null,
    outcome: executionOutcome(tx),
    leader_entries: entries.map((e) => ({
      mode: e?.mode ?? null,
      execution_result: e?.execution_result ?? e?.executionResult ?? null,
      result_status: e?.result?.status ?? null,
    })),
  };
}

export async function checkScanStatus(
  txHash: string,
  chainId: number | "solana",
  address: string
): Promise<StatusResult> {
  const client = getReadClient();

  let tx;
  try {
    tx = await client.getTransaction({ hash: txHash as never });
  } catch (e) {
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

  // Accepted/Finalized only means validators reached consensus; the contract call itself may still
  // have errored. The authoritative signal is the leader's execution result in the receipt.
  const exec = executionOutcome(tx);
  if (exec === "error") {
    return {
      status: "failed",
      reason: "execution_error",
      detail: "The GenVM execution of this scan failed, so no report was recorded.",
    };
  }
  if (exec !== "success") {
    // Never treat an unknown outcome as success: stored state could belong to an older scan.
    return {
      status: "failed",
      reason: "execution_unconfirmed",
      detail: "The GenVM execution result of this transaction could not be confirmed, so the report is not shown.",
    };
  }

  if (!CONTRACT_ADDRESS) {
    return { status: "failed", reason: "config_error", detail: "CONTRACT_ADDRESS is not set" };
  }
  let scanJson: string;
  try {
    scanJson = (await client.readContract({
      address: CONTRACT_ADDRESS,
      functionName: chainId === "solana" ? "get_solana_scan" : "get_scan",
      args: chainId === "solana" ? [address] : [chainId, address],
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

  return { status: "done", result: parsed, execution: "success" };
}

// ---- History (recent scans, shared by all visitors) ----

export type HistoryEntry = { chain_id: number | "solana"; address: string; verdict: string; source: string };

export async function getRecentScans(limit = 10): Promise<HistoryEntry[]> {
  if (!CONTRACT_ADDRESS) return [];
  const raw = (await getReadClient().readContract({
    address: CONTRACT_ADDRESS,
    functionName: "get_recent_scans",
    args: [limit],
  })) as string;
  const parsed = JSON.parse(raw);
  return Array.isArray(parsed) ? parsed : [];
}

export async function getStoredScanResult(chainId: number | "solana", address: string): Promise<unknown | null> {
  if (!CONTRACT_ADDRESS) return null;
  const raw = (await getReadClient().readContract({
    address: CONTRACT_ADDRESS,
    functionName: chainId === "solana" ? "get_solana_scan" : "get_scan",
    args: chainId === "solana" ? [address] : [chainId, address],
  })) as string;
  const parsed = JSON.parse(raw);
  return parsed && typeof parsed === "object" && Object.keys(parsed).length > 0 ? parsed : null;
}
