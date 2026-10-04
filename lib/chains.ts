export type ChainOption = { id: number; name: string };

// Shown in the chain dropdown, in this order.
export const POPULAR_CHAINS: ChainOption[] = [
  { id: 1, name: "Ethereum" },
  { id: 8453, name: "Base" },
  { id: 56, name: "BNB Chain" },
  { id: 137, name: "Polygon" },
  { id: 42161, name: "Arbitrum One" },
  { id: 10, name: "OP Mainnet" },
  { id: 43114, name: "Avalanche" },
  { id: 4663, name: "Robinhood Chain" },
];

// Extra names, used only to label results (not shown in the dropdown).
const MORE_NAMES: Record<number, string> = {
  100: "Gnosis",
  130: "Unichain",
  146: "Sonic",
  196: "X Layer",
  250: "Fantom",
  324: "zkSync Era",
  369: "PulseChain",
  5000: "Mantle",
  57073: "Ink",
  59144: "Linea",
  81457: "Blast",
  534352: "Scroll",
};

export function chainName(id?: number): string {
  if (id === undefined) return "";
  const popular = POPULAR_CHAINS.find((c) => c.id === id);
  if (popular) return popular.name;
  return MORE_NAMES[id] || "";
}

// "Ethereum · 1" when the name is known, otherwise "Chain 4663".
export function chainLabel(id?: number): string {
  if (id === undefined) return "Unknown chain";
  const name = chainName(id);
  return name ? name + " · " + id : "Chain " + id;
}
