import { SOLANA, isSupportedEvm, type ChainRef } from "./chains";

export const EVM_ADDRESS_RE = /^0x[a-fA-F0-9]{40}$/;
// Solana mint: base58, 32-44 characters (no 0, O, I, l).
export const SOLANA_MINT_RE = /^[1-9A-HJ-NP-Za-km-z]{32,44}$/;

export function isSolanaMint(a: string): boolean {
  return SOLANA_MINT_RE.test(a);
}

// Parses a chain reference from user input: "solana" or a supported EVM chain id.
export function parseChainRef(v: unknown): ChainRef | null {
  if (v === SOLANA) return SOLANA;
  const n = typeof v === "string" && v.trim() !== "" ? Number(v) : v;
  if (typeof n === "number" && Number.isInteger(n) && isSupportedEvm(n)) return n;
  return null;
}

// True when the address fits the chain's format.
export function addressFitsChain(chain: ChainRef, address: string): boolean {
  return chain === SOLANA ? isSolanaMint(address) : EVM_ADDRESS_RE.test(address);
}
