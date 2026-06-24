export type Action =
  | "buy_call"
  | "buy_put"
  | "call_spread"
  | "put_spread"
  | "go_long"
  | "go_short"
  | "skip";

export type Direction = "bullish" | "bearish" | "neutral";

export interface Trade {
  id: string;
  ticker: string;
  action: Action;
  direction: Direction;
  earningsDate: string;
  thesis: string;
  keyFactors: string[];
  maxRisk: number;
  contracts: number;
  costPerContract: number;
  strike: number;
  expiry: string;
  receivedAt: Date;
}

export interface DayGroup {
  date: string;
  trades: Trade[];
}
