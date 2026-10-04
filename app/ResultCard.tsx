import "./result-card.css";

type Tone = "red" | "brass" | "green" | "grey";

type Finding = { answer?: string; function?: string; reason?: string };

export type ScanResult = {
  chain_id?: number;
  input_address?: string;
  analyzed_address?: string;
  is_proxy?: boolean;
  proxy_type?: string;
  source?: string;
  verified?: boolean;
  verdict?: string;
  reason?: string;
  llm_parse_ok?: boolean;
  review?: {
    project_files?: number;
    library_files?: number;
    functions_total?: number;
    functions_public_nonview?: number;
    flags?: Record<string, number>;
    map_truncated?: boolean;
    snippets_truncated?: boolean;
  } | null;
  llm_findings?: Record<string, unknown> | null;
};

const VERDICTS: Record<string, { label: string; tone: Tone; summary: string }> = {
  BAHAYA: {
    label: "Danger",
    tone: "red",
    summary:
      "Several high-impact privileged capabilities were found in the code. In issuer-managed tokens this can be by design, but either way holders are trusting whoever controls these powers.",
  },
  WASPADA: {
    label: "Caution",
    tone: "brass",
    summary: "One privileged capability was found in the code. Review it below before relying on this token.",
  },
  AMAN: {
    label: "Clear",
    tone: "green",
    summary:
      "None of the five checked capabilities was found in the code that was analyzed. This is not a guarantee of safety.",
  },
  INCONCLUSIVE: {
    label: "Inconclusive",
    tone: "grey",
    summary:
      "Too many of the checks could not be settled to give a verdict. Try again, or paste the contract's source code directly.",
  },
  UNVERIFIED_HIGH_CAUTION: {
    label: "Unverified",
    tone: "red",
    summary:
      "No verified source code was found, so this contract's behavior cannot be reviewed. Treat that as a risk signal on its own.",
  },
  NOT_ANALYZED: {
    label: "Not analyzed",
    tone: "grey",
    summary: "Nothing was analyzed because the pasted input was empty.",
  },
};

const CATEGORIES: Array<{ key: string; title: string; meaning: string }> = [
  {
    key: "unrestricted_mint",
    title: "Unrestricted minting",
    meaning: "Whether a privileged address can create new tokens with no visible cap, diluting every holder.",
  },
  {
    key: "blacklist_or_freeze",
    title: "Blacklist or freeze",
    meaning: "Whether a privileged address can block or freeze a specific holder's tokens.",
  },
  {
    key: "pause_transfers",
    title: "Transfer pause",
    meaning: "Whether a privileged address can halt transfers for every holder at once.",
  },
  {
    key: "upgrade_without_timelock",
    title: "Instant upgrades",
    meaning: "Whether the contract logic can be replaced with no delay visible in the code, so the rules could change without warning.",
  },
  {
    key: "hidden_privileged_calls",
    title: "Privileged low-level calls",
    meaning: "Whether a privileged function makes low-level calls (delegatecall, assembly) that could bypass the contract's normal rules.",
  },
];

const LIMITS = [
  "Who holds the admin or upgrade keys, and whether they sit behind a multisig or a timelock.",
  "Off-chain controls, and the reputation of whoever issued the token.",
  "Whether the code has been professionally audited.",
  "How other contracts that interact with this token behave.",
];

function shortAddr(addr?: string): string {
  if (!addr) return "unknown address";
  if (addr.length <= 18) return addr;
  return addr.slice(0, 8) + "…" + addr.slice(-6);
}

function asFinding(value: unknown): Finding | null {
  if (value && typeof value === "object" && !Array.isArray(value)) return value as Finding;
  return null;
}

function statusOf(answer?: string): { text: string; tone: Tone } {
  const a = (answer || "").toUpperCase();
  if (a === "YES") return { text: "Found", tone: "brass" };
  if (a === "NO") return { text: "Not found", tone: "green" };
  return { text: "Unclear", tone: "grey" };
}

export default function ResultCard({ result }: { result: ScanResult }) {
  const verdictKey = result.verdict || "";
  const meta = VERDICTS[verdictKey] || {
    label: verdictKey || "Unknown",
    tone: "grey" as Tone,
    summary: "The scan finished with a result this page does not recognize. See the raw data below.",
  };

  const findings = result.llm_findings && typeof result.llm_findings === "object" ? result.llm_findings : null;
  const explanation = findings && typeof findings["explanation"] === "string" ? (findings["explanation"] as string) : "";
  const review = result.review || null;

  const implDiffers =
    !!result.analyzed_address &&
    !!result.input_address &&
    result.analyzed_address.toLowerCase() !== result.input_address.toLowerCase();

  const flagText = review?.flags
    ? Object.entries(review.flags)
        .filter(([, n]) => typeof n === "number" && n > 0)
        .map(([name, n]) => name + " " + n)
        .join(" · ") || "none"
    : "";

  const facts: Array<[string, string]> = [];
  if (result.chain_id !== undefined) facts.push(["Chain", String(result.chain_id)]);
  facts.push([
    "Source",
    result.source === "pasted" ? "Pasted code" : result.verified ? "Verified on Sourcify" : "No verified source",
  ]);
  facts.push([
    "Proxy",
    result.is_proxy
      ? (result.proxy_type || "Yes") + (result.verified ? " · implementation analyzed" : " · implementation not readable")
      : "No",
  ]);
  if (review) {
    if (review.project_files !== undefined && review.library_files !== undefined) {
      facts.push(["Files", review.project_files + " project · " + review.library_files + " library"]);
    }
    if (review.functions_total !== undefined && review.functions_public_nonview !== undefined) {
      facts.push(["Functions", review.functions_total + " total · " + review.functions_public_nonview + " state-changing"]);
    }
    if (flagText) facts.push(["Low-level flags", flagText]);
  }

  const truncated = !!(review && (review.map_truncated || review.snippets_truncated));

  return (
    <section className={"rc-card rc-tone-" + meta.tone} aria-label="Scan result">
      <div className="rc-head">
        <div>
          <p className="rc-eyebrow">Case file</p>
          <p className="rc-subject">
            <span className="rc-nowrap" title={result.input_address}>
              {shortAddr(result.input_address)}
            </span>
            {implDiffers && (
              <small title={result.analyzed_address}>
                Implementation <span className="rc-nowrap">{shortAddr(result.analyzed_address)}</span>
              </small>
            )}
          </p>
        </div>
        <div className="rc-stamp">{meta.label}</div>
      </div>

      <p className="rc-summary">{meta.summary}</p>

      {explanation && <p className="rc-notice">{explanation}</p>}
      {truncated && (
        <p className="rc-notice">
          Part of this contract&apos;s code was too large to include, so these results may be incomplete.
        </p>
      )}
      {result.llm_parse_ok === false && (
        <p className="rc-notice">
          The reviewer&apos;s answer could not be read cleanly, so any &quot;Unclear&quot; below may be a formatting problem rather
          than something in the code.
        </p>
      )}

      {findings && CATEGORIES.some((c) => asFinding(findings[c.key]) !== null) && (
        <>
          <h3 className="rc-section">What was checked</h3>
          <ul className="rc-findings">
            {CATEGORIES.map((c) => {
              const f = asFinding(findings[c.key]);
              if (!f) return null;
              const st = statusOf(f.answer);
              return (
                <li key={c.key} className="rc-finding">
                  <div className="rc-finding-top">
                    <span className="rc-finding-title">{c.title}</span>
                    <span className={"rc-chip rc-tone-" + st.tone}>{st.text}</span>
                  </div>
                  {f.function ? (
                    <p className="rc-fn">
                      Function: <code>{f.function}</code>
                    </p>
                  ) : null}
                  {f.reason ? <p className="rc-reason">{f.reason}</p> : null}
                  <p className="rc-meaning">{c.meaning}</p>
                </li>
              );
            })}
          </ul>
        </>
      )}

      <h3 className="rc-section">About this contract</h3>
      <dl className="rc-facts">
        {facts.map(([label, value]) => (
          <div key={label} className="rc-fact">
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>

      <h3 className="rc-section">What this scan cannot tell you</h3>
      <ul className="rc-limits">
        {LIMITS.map((l) => (
          <li key={l}>{l}</li>
        ))}
      </ul>
      <p className="rc-foot">A flagged capability means it exists in the code, not that anyone has used it.</p>

      <details className="rc-raw">
        <summary>Show raw data</summary>
        <pre>{JSON.stringify(result, null, 2)}</pre>
      </details>
    </section>
  );
}
