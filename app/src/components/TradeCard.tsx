import React, { useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Animated,
} from "react-native";
import { Trade, Action } from "../types/trade";

const ACTION_CONFIG: Record<Action, { label: string; bg: string; text: string }> = {
  buy_call:    { label: "CALL",       bg: "#E8F5E9", text: "#2E7D32" },
  call_spread: { label: "CALL SPREAD",bg: "#E8F5E9", text: "#2E7D32" },
  go_long:     { label: "LONG",       bg: "#E8F5E9", text: "#2E7D32" },
  buy_put:     { label: "PUT",        bg: "#FFEBEE", text: "#C62828" },
  put_spread:  { label: "PUT SPREAD", bg: "#FFEBEE", text: "#C62828" },
  go_short:    { label: "SHORT",      bg: "#FFEBEE", text: "#C62828" },
  skip:        { label: "SKIP",       bg: "#F5F5F5", text: "#757575" },
};

const DIRECTION_ARROW: Record<string, string> = {
  bullish: "↑",
  bearish: "↓",
  neutral: "→",
};

interface Props {
  trade: Trade;
}

export default function TradeCard({ trade }: Props) {
  const [expanded, setExpanded] = useState(false);
  const config = ACTION_CONFIG[trade.action];
  const arrow = DIRECTION_ARROW[trade.direction] ?? "→";
  const isEquity = trade.action === "go_long" || trade.action === "go_short";
  const time = trade.receivedAt.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });

  return (
    <TouchableOpacity
      activeOpacity={0.7}
      onPress={() => setExpanded(!expanded)}
      style={styles.card}
    >
      {/* Header row */}
      <View style={styles.header}>
        <View style={styles.tickerRow}>
          <Text style={styles.ticker}>{trade.ticker}</Text>
          <Text style={[styles.arrow, { color: config.text }]}>{arrow}</Text>
        </View>
        <View style={[styles.badge, { backgroundColor: config.bg }]}>
          <Text style={[styles.badgeText, { color: config.text }]}>
            {config.label}
          </Text>
        </View>
      </View>

      {/* Thesis */}
      <Text style={styles.thesis} numberOfLines={expanded ? undefined : 2}>
        {trade.thesis}
      </Text>

      {/* Quick stats row */}
      <View style={styles.statsRow}>
        <View style={styles.stat}>
          <Text style={styles.statLabel}>Risk</Text>
          <Text style={styles.statValue}>${trade.maxRisk.toLocaleString()}</Text>
        </View>
        {isEquity ? (
          <View style={styles.stat}>
            <Text style={styles.statLabel}>Shares</Text>
            <Text style={styles.statValue}>{trade.contracts}</Text>
          </View>
        ) : (
          <>
            <View style={styles.stat}>
              <Text style={styles.statLabel}>Strike</Text>
              <Text style={styles.statValue}>${trade.strike}</Text>
            </View>
            <View style={styles.stat}>
              <Text style={styles.statLabel}>Contracts</Text>
              <Text style={styles.statValue}>{trade.contracts}</Text>
            </View>
          </>
        )}
        <View style={styles.stat}>
          <Text style={styles.statLabel}>Earnings</Text>
          <Text style={styles.statValue}>{trade.earningsDate}</Text>
        </View>
      </View>

      {/* Expanded: key factors */}
      {expanded && trade.keyFactors.length > 0 && (
        <View style={styles.factorsContainer}>
          <Text style={styles.factorsTitle}>Key Factors</Text>
          {trade.keyFactors.map((factor, i) => (
            <View key={i} style={styles.factorRow}>
              <Text style={styles.factorBullet}>•</Text>
              <Text style={styles.factorText}>{factor}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Footer */}
      <View style={styles.footer}>
        <Text style={styles.time}>{time}</Text>
        <Text style={styles.expandHint}>
          {expanded ? "tap to collapse" : "tap for details"}
        </Text>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: "#fff",
    borderRadius: 12,
    padding: 16,
    marginHorizontal: 16,
    marginVertical: 6,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.08,
    shadowRadius: 4,
    elevation: 2,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
  },
  tickerRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  ticker: {
    fontSize: 22,
    fontWeight: "700",
    color: "#1a1a1a",
    letterSpacing: 0.5,
  },
  arrow: {
    fontSize: 18,
    fontWeight: "700",
  },
  badge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 6,
  },
  badgeText: {
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 0.5,
  },
  thesis: {
    fontSize: 14,
    color: "#444",
    lineHeight: 20,
    marginBottom: 12,
  },
  statsRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    borderTopWidth: 1,
    borderTopColor: "#f0f0f0",
    paddingTop: 10,
  },
  stat: {
    alignItems: "center",
  },
  statLabel: {
    fontSize: 11,
    color: "#999",
    textTransform: "uppercase",
    letterSpacing: 0.5,
    marginBottom: 2,
  },
  statValue: {
    fontSize: 14,
    fontWeight: "600",
    color: "#1a1a1a",
  },
  factorsContainer: {
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: "#f0f0f0",
  },
  factorsTitle: {
    fontSize: 12,
    fontWeight: "700",
    color: "#999",
    textTransform: "uppercase",
    letterSpacing: 0.5,
    marginBottom: 8,
  },
  factorRow: {
    flexDirection: "row",
    marginBottom: 4,
    paddingRight: 8,
  },
  factorBullet: {
    fontSize: 14,
    color: "#999",
    marginRight: 6,
    lineHeight: 20,
  },
  factorText: {
    fontSize: 13,
    color: "#555",
    lineHeight: 20,
    flex: 1,
  },
  footer: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: 10,
  },
  time: {
    fontSize: 11,
    color: "#bbb",
  },
  expandHint: {
    fontSize: 11,
    color: "#bbb",
  },
});
