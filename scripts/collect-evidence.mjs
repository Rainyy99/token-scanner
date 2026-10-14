// Collects authoritative evidence for the scans listed in evidence/scans.json:
// for each transaction, the consensus status and the leader's GenVM execution result from the
// receipt, plus the report read back from the deployed contract (get_scan / get_solana_scan).
//
//   CONTRACT_ADDRESS=0x... node scripts/collect-evidence.mjs
//
// Output: evidence/readbacks/<label>.json and evidence/SUMMARY.md
import { createClient } from "genlayer-js";
import { studionet } from "genlayer-js/chains";
import fs from "node:fs";

const contract = process.env.CONTRACT_ADDRESS;
if (!contract) throw new Error("Set CONTRACT_ADDRESS to the deployed contract address");
const scans = JSON.parse(fs.readFileSync("evidence/scans.json", "utf8"));
const client = createClient({ chain: studionet });

function leaderEntries(tx) {
  const lr = tx?.consensus_data?.leader_receipt ?? tx?.consensusData?.leaderReceipt;
  const entries = Array.isArray(lr) ? lr : lr ? [lr] : [];
  return entries.map((e) => ({
    mode: e?.mode ?? null,
    execution_result: e?.execution_result ?? e?.executionResult ?? null,
    result_status: e?.result?.status ?? null,
  }));
}

fs.mkdirSync("evidence/readbacks", { recursive: true });
const version = await client.readContract({ address: contract, functionName: "get_version", args: [] });
const rows = [];
for (const s of scans) {
  const tx = await client.getTransaction({ hash: s.tx });
  const entries = leaderEntries(tx);
  const leader = entries.filter((e) => e.mode === "leader");
  const executed = leader.length > 0 && leader.every((e) => e.execution_result === "SUCCESS");
  const isSol = s.chainId === "solana";
  const raw = await client.readContract({
    address: contract,
    functionName: isSol ? "get_solana_scan" : "get_scan",
    args: isSol ? [s.address] : [s.chainId, s.address],
  });
  const scan = JSON.parse(raw);
  const out = {
    contract, version, label: s.label, tx: s.tx,
    status: tx.statusName, leader_entries: entries, execution_confirmed: executed,
    readback_method: isSol ? "get_solana_scan" : "get_scan", readback_args: isSol ? [s.address] : [s.chainId, s.address],
    scan,
  };
  fs.writeFileSync(`evidence/readbacks/${s.label}.json`, JSON.stringify(out, null, 2));
  rows.push(`| ${s.label} | \`${s.tx}\` | ${tx.statusName} | ${executed ? "SUCCESS" : "NOT CONFIRMED"} | ${scan?.final?.headline ?? scan?.verdict ?? "?"} |`);
  console.log(s.label, tx.statusName, executed ? "SUCCESS" : "NOT CONFIRMED", scan?.final?.headline);
}
fs.writeFileSync(
  "evidence/SUMMARY.md",
  `Contract: \`${contract}\` (get_version: ${JSON.stringify(version)})\n\n| Scan | Transaction | Status | GenVM execution | Report headline |\n| --- | --- | --- | --- | --- |\n${rows.join("\n")}\n`
);
