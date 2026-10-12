# Token Security Scanner

Paste an EVM token address or a Solana token mint. GenLayer validators read the contract, check who holds the supply and how established the token is, and file one case report. The report never says a token is "safe".

Built on [GenLayer](https://www.genlayer.com): an intelligent contract (`contracts/`) does the analysis, and a Next.js app on Vercel is the front end.

## What it checks

**Contract powers (EVM).** The contract fetches verified source from [Sourcify](https://sourcify.dev), follows proxies to the implementation, maps the functions, and asks an LLM five questions:

- unrestricted minting
- blacklist or freeze
- transfer pause
- instant upgrades (no timelock visible in the code)
- privileged low-level calls

Validators must agree on the answers (GenLayer equivalence principle). The verdict itself is computed by fixed rules from the code, including whether each matching function sits behind an access check, so the same code gives the same verdict.

**Authorities (Solana).** Mint and freeze authority, and rug flags, from RugCheck.

**Token profile and market structure.**

| Profile | Meaning |
| --- | --- |
| Stablecoin | Address matches a verified issuer contract, or CoinGecko lists it as a stablecoin with strong ranking |
| Established | Reputation, holder base and age all met (12+ months) |
| Launchpad | Launched through a token launchpad and still young |
| Unproven | Not enough independent signals |

Alongside the profile: holder count, top-wallet concentration, locked liquidity, token age, and a neutral **DEX Paid** label. DEX Paid only means a paid DexScreener profile exists; it says nothing about safety.

**Final headline.** The contract verdict, profile and market flags are composed into one headline, in this priority order: DANGER, UNVERIFIED CONTRACT or CODE NOT AVAILABLE TO ANALYZER, INCONCLUSIVE, STABLECOIN, CENTRALIZED CONTROL, CAUTION, NO RED FLAGS FOUND (established tokens only), NO CONTRACT RED FLAGS. Established tokens and stablecoins get softer treatment for concentration and holder flags (shown as notes), but honeypot, high-tax, rugged and danger signals always stay strong.

## Supported chains

Ethereum (1), Base (8453), BNB Chain (56), Robinhood Chain (4663), Arbitrum One (42161), Polygon (137), OP Mainnet (10), and Solana.

On Robinhood Chain, tokens launched through Pons also get a launch date and launchpad status read from the Pons factory.

## Limitations

- **The peg is not checked.** A stablecoin label means the address matches the issuer's official contract, not that it currently trades at $1.
- **Unlabeled wallets can inflate concentration.** Treasuries, exchanges and vaults without a public label look like large holders.
- **No "safe" label, ever.** "No red flags found" means none of the checks fired.
- **Source code comes from Sourcify only.** Contracts it has not verified cannot be reviewed; they get UNVERIFIED CONTRACT, or CODE NOT AVAILABLE TO ANALYZER when another source reports the code is open.
- **Multi-contract bundles.** When the verified source covers a whole system (more than 30 project files), the analyzer cannot tell which functions belong to the token. An unrestricted-looking power in such a bundle is reported as INCONCLUSIVE, never as CLEAR and never silently downgraded.
- **Large or proxy contracts** can take longer and sometimes fail validator consensus. Try again, or paste the source code directly (EVM only).
- **Honeypot and high-tax detection** relies on GoPlus data. Offline tests cover honeypot, high-tax, rugged and liquidity-risk cases with mocked API data, but they have not been run against a live honeypot token.
- **Solana liquidity locks** can only be checked for pools that issue LP tokens. Concentrated-liquidity pools are reported as partly checked.
- Market data comes from third-party APIs (GoPlus, RugCheck, Jupiter, DexScreener, CoinGecko). When one is down, the report says that structure was not checked.

## How the app works

- **Operator relay.** A backend wallet pays gas, so visitors need no wallet.
- **Submit and poll.** `POST /api/scan/submit` sends the transaction and returns immediately; the page polls `GET /api/scan/status` every three seconds. This avoids serverless timeouts.
- **Date from the front end.** Validators have no reliable clock, so the server passes today's date (UTC) to the contract for age calculations.
- **Recent scans** are stored in the contract and shared by all visitors.
- **Rate limit** is in memory, per instance (5 per hour and 15 per day per IP): a best-effort deterrent, not a hard guarantee.

## Run it

```bash
npm install
cp .env.example .env.local   # then fill in the two values
npm run dev
```

| Variable | Purpose |
| --- | --- |
| `CONTRACT_ADDRESS` | Deployed `TokenSecurityScanner` contract on GenLayer Studio |
| `OPERATOR_PRIVATE_KEY` | Funded account that sends scan transactions |

## Verdict rules

Each of the five contract questions ends as YES, NO or UNCLEAR. Missing, malformed or conflicting model answers count as UNCLEAR. A NO that the code evidence contradicts is changed to UNCLEAR (or YES). The verdict is then computed by fixed rules:

| Verdict | When |
| --- | --- |
| DANGER | A YES on a power that sits in an open (unrestricted) function |
| CENTRALIZED | Two or more YES answers, all behind access checks |
| CAUTION | One YES answer behind an access check |
| INCONCLUSIVE | Any UNCLEAR answer, a truncated function map or source excerpt, or a failed source lookup |
| CLEAR | All five checks answered NO on complete code |

Incomplete analysis can never lower the severity of a real finding and can never produce CLEAR. Unavailable market data (GoPlus, RugCheck and others) is reported as "not verified", not as clean.

## Tests

Offline tests run the contract with mocked network and LLM responses, so they need no network and no GenLayer node:

```bash
python3 tests/test_verdict_rules.py   # verdict rules and reconciliation
python3 tests/test_adversarial.py     # unrestricted mint, blacklist, pause, unsafe upgrade, delegatecall,
                                      # malformed model output, conflicting validators, incomplete source
python3 tests/test_market.py          # honeypot, high tax, rugged, liquidity risk, unavailable API data
```

## Frontend execution check

A scan is shown as successful only after the transaction is ACCEPTED or FINALIZED **and** the leader's GenVM execution result in the receipt is not an error. The page then reads the report back from the contract with `get_scan` / `get_solana_scan`. UNDETERMINED transactions and execution errors are shown as failures.

## Deployment and evidence

Deployed contract (GenLayer Studio, `get_version` returns `"v16"`): `0xdb54C5495d3824b0A10117A7977FC4b7233eE356`

The live web app uses this same address (`CONTRACT_ADDRESS`). Each scan below was sent from the web app, reached FINALIZED with a successful GenVM execution, and was then read back from the contract with `get_scan` / `get_solana_scan`.

| Token | Method | Transaction (FINALIZED) | Readback |
| --- | --- | --- | --- |
| UNI, Ethereum (1) `0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984` | `scan_token_full` | `0xae198c3b38014ea8d3a13d37af2156be4406357ab644dc90896e69f218ddee29` | contract verdict CAUTION (mint power behind an access check; low-level calls UNCLEAR, reported as "check not settled") |
| USDC, Base (8453) `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` | `scan_token_full` | `0x996b9cdfa7e60722fc4c191df475c06bfe34401330b72455b9df7b9c07d3d1ac` | proxy followed to `0x2Ce6311ddAE708829bc0784C967b7d77D19FD779`; contract verdict CENTRALIZED (mint, blacklist, pause and upgrade found, low-level calls UNCLEAR); headline STABLECOIN with the incomplete-check note |
| JUP, Solana `JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN` | `scan_solana_token` | `0xa4aaaad4cd4f9c35ba9cf0b66df130176b5d186bcf48cddbbb86e600d9e35ac8` | headline NO RED FLAGS FOUND, established token, liquidity lock only partly checkable |

## Contract

The full intelligent contract is in [`contracts/token_security_scanner_v16.py`](contracts/token_security_scanner_v16.py). To run your own copy, deploy that file to GenLayer Studio and put the deployed address in `CONTRACT_ADDRESS`. The web app in `app/` and `lib/` only relays requests to it and renders the stored result.

## Contract methods

Writes: `scan_token_full(chain_id, address, today)`, `scan_solana_token(mint, today)`, `scan_token(chain_id, address)`, `scan_pasted_code(chain_id, address, code)`.
Reads: `get_scan`, `get_solana_scan`, `get_recent_scans`, `get_scan_count`, `get_version`.

Automated analysis. Not financial advice and not a guarantee.
