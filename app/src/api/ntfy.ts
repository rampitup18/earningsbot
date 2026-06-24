import { Trade, Action, Direction } from "../types/trade";

const NTFY_SERVER = "https://ntfy.sh";

interface NtfyMessage {
  id: string;
  time: number;
  event: string;
  topic: string;
  title?: string;
  message?: string;
  priority?: number;
}

function parseAction(title: string): { action: Action; direction: Direction; ticker: string } {
  const match = title.match(/^\[([v^-])\]\s+(\w+)\s+(.+)$/);
  if (!match) return { action: "skip", direction: "neutral", ticker: "???" };

  const [, arrow, ticker, actionText] = match;
  const direction: Direction =
    arrow === "^" ? "bullish" : arrow === "v" ? "bearish" : "neutral";

  const actionMap: Record<string, Action> = {
    "BUY CALL": "buy_call",
    "BUY PUT": "buy_put",
    "CALL DEBIT SPREAD": "call_spread",
    "PUT DEBIT SPREAD": "put_spread",
    "BUY SHARES (LONG)": "go_long",
    "SELL SHORT": "go_short",
  };

  const action = actionMap[actionText.trim()] ?? "skip";
  return { action, direction, ticker };
}

function parseTrade(msg: NtfyMessage): Trade | null {
  if (msg.event !== "message" || !msg.title || !msg.message) return null;

  const { action, direction, ticker } = parseAction(msg.title);
  if (action === "skip") return null;

  const body = msg.message;
  const lines = body.split("\n");

  let earningsDate = "";
  let maxRisk = 0;
  let contracts = 0;
  let costPerContract = 0;
  let strike = 0;
  let expiry = "";
  let thesis = "";
  const keyFactors: string[] = [];

  let parsingFactors = false;

  for (const line of lines) {
    const trimmed = line.trim();

    if (trimmed.startsWith("Earnings:")) {
      earningsDate = trimmed.replace("Earnings:", "").trim();
    } else if (trimmed.startsWith("Strike")) {
      const parts = trimmed.match(/Strike \$(\d+)\s+Exp\s+(.+)/);
      if (parts) {
        strike = parseFloat(parts[1]);
        expiry = parts[2].trim();
      }
    } else if (trimmed.match(/^\d+ shares @/)) {
      const parts = trimmed.match(/^(\d+) shares @ \$(.+)/);
      if (parts) {
        contracts = parseInt(parts[1]);
        costPerContract = parseFloat(parts[2]);
      }
    } else if (trimmed.match(/^\$[\d.]+\/contract/)) {
      const parts = trimmed.match(/^\$([\d.]+)\/contract x(\d+)/);
      if (parts) {
        costPerContract = parseFloat(parts[1]);
        contracts = parseInt(parts[2]);
      }
    } else if (trimmed.startsWith("Max risk")) {
      const m = trimmed.match(/\$([\d.]+)/);
      if (m) maxRisk = parseFloat(m[1]);
    } else if (trimmed.startsWith("•")) {
      keyFactors.push(trimmed.replace(/^•\s*/, ""));
      parsingFactors = true;
    } else if (parsingFactors) {
      // Done with factors
    } else if (trimmed && !trimmed.startsWith("Implied") && !trimmed.startsWith("IV/HV")) {
      if (!thesis && trimmed.length > 10) thesis = trimmed;
    }
  }

  return {
    id: msg.id,
    ticker,
    action,
    direction,
    earningsDate,
    thesis,
    keyFactors,
    maxRisk,
    contracts,
    costPerContract,
    strike,
    expiry,
    receivedAt: new Date(msg.time * 1000),
  };
}

export async function fetchTrades(topic: string, since: string = "7d"): Promise<Trade[]> {
  const url = `${NTFY_SERVER}/${topic}/json?poll=1&since=${since}`;

  const response = await fetch(url);
  if (!response.ok) throw new Error(`ntfy error: ${response.status}`);

  const text = await response.text();
  const messages: NtfyMessage[] = text
    .trim()
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line));

  const trades: Trade[] = [];
  for (const msg of messages) {
    const trade = parseTrade(msg);
    if (trade) trades.push(trade);
  }

  return trades.sort((a, b) => b.receivedAt.getTime() - a.receivedAt.getTime());
}

export function groupByDate(trades: Trade[]): { date: string; trades: Trade[] }[] {
  const groups = new Map<string, Trade[]>();

  for (const trade of trades) {
    const key = trade.receivedAt.toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
    });
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(trade);
  }

  return Array.from(groups.entries()).map(([date, trades]) => ({ date, trades }));
}
