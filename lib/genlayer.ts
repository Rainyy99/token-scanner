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

export type ScanRunResult =
  | { ok: true }
  | {
      ok: false;
      reason: "undetermined" | "execution_error" | "timeout" | "config_error";
      detail: string;
    };

async function runWrite(
  functionName: "scan_token" | "scan_pasted_code",
  args: unknown[]
): Promise<ScanRunResult> {
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

  let receipt;
  try {
    receipt = await client.waitForTransactionReceipt({
      hash: txHash,
      status: TransactionStatus.FINALIZED,
      retries: 40,
      interval: 3000,
    });
  } catch (e) {
    return { ok: false, reason: "timeout", detail: String(e) };
  }

  const statusName = receipt.statusName;

  if (statusName && !DECIDED_STATES.includes(statusName)) {
    return {
      ok: false,
      reason: "timeout",
      detail: "Transaction did not reach a final state: " + statusName,
    };
  }
  if (statusName === TransactionStatus.UNDETERMINED) {
    return {
      ok: false,
      reason: "undetermined",
      detail: "Validators could not reach consensus on this scan. Please try again.",
    };
  }
  if (receipt.txExecutionResultName === "FINISHED_WITH_ERROR") {
    return {
      ok: false,
      reason: "execution_error",
      detail: "Contract execution failed.",
    };
  }

  return { ok: true };
}

export async function runScanToken(chainId: number, address: string): Promise<ScanRunResult> {
  return runWrite("scan_token", [chainId, address]);
}

export async function runScanPastedCode(
  chainId: number,
  address: string,
  pastedCode: string
): Promise<ScanRunResult> {
  return runWrite("scan_pasted_code", [chainId, address, pastedCode]);
}

export async function getScan(chainId: number, address: string): Promise<string> {
  if (!CONTRACT_ADDRESS) {
    throw new Error("CONTRACT_ADDRESS is not set");
  }
  const client = getReadClient();
  const result = await client.readContract({
    address: CONTRACT_ADDRESS,
    functionName: "get_scan",
    args: [chainId, address],
  });
  return result as string;
}
