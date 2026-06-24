import { useState, useEffect, useCallback } from "react";
import {
  View,
  Text,
  SectionList,
  StyleSheet,
  RefreshControl,
  TouchableOpacity,
  ActivityIndicator,
} from "react-native";
import { SafeAreaView, SafeAreaProvider } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";
import AsyncStorage from "@react-native-async-storage/async-storage";
import TradeCard from "./src/components/TradeCard";
import SettingsSheet from "./src/components/SettingsSheet";
import { fetchTrades, groupByDate } from "./src/api/ntfy";
import { Trade } from "./src/types/trade";

const TOPIC_KEY = "ntfy_topic";

export default function App() {
  const [topic, setTopic] = useState("");
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [showSettings, setShowSettings] = useState(false);

  useEffect(() => {
    AsyncStorage.getItem(TOPIC_KEY).then((saved: string | null) => {
      if (saved) {
        setTopic(saved);
      } else {
        setLoading(false);
        setShowSettings(true);
      }
    });
  }, []);

  const loadTrades = useCallback(async () => {
    if (!topic) {
      setLoading(false);
      return;
    }
    setError("");
    try {
      const result = await fetchTrades(topic);
      setTrades(result);
    } catch (e: any) {
      setError(e.message || "Failed to load trades");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [topic]);

  useEffect(() => {
    if (topic) {
      setLoading(true);
      loadTrades();
    }
  }, [topic, loadTrades]);

  const onRefresh = () => {
    setRefreshing(true);
    loadTrades();
  };

  const saveTopic = async (newTopic: string) => {
    await AsyncStorage.setItem(TOPIC_KEY, newTopic);
    setTopic(newTopic);
  };

  const sections = groupByDate(trades).map((g) => ({
    title: g.date,
    data: g.trades,
  }));

  const bullCount = trades.filter(
    (t) => t.direction === "bullish"
  ).length;
  const bearCount = trades.filter(
    (t) => t.direction === "bearish"
  ).length;

  return (
    <SafeAreaProvider>
    <SafeAreaView style={styles.container}>
      <StatusBar style="dark" />

      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>EarningsBot</Text>
          <Text style={styles.subtitle}>
            {trades.length > 0
              ? `${trades.length} trades  ·  ${bullCount} bullish  ·  ${bearCount} bearish`
              : "Pre-earnings trade scanner"}
          </Text>
        </View>
        <TouchableOpacity
          style={styles.settingsBtn}
          onPress={() => setShowSettings(true)}
        >
          <Text style={styles.settingsIcon}>⚙</Text>
        </TouchableOpacity>
      </View>

      {/* Content */}
      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color="#1a1a1a" />
        </View>
      ) : error ? (
        <View style={styles.center}>
          <Text style={styles.errorText}>{error}</Text>
          <TouchableOpacity style={styles.retryBtn} onPress={loadTrades}>
            <Text style={styles.retryText}>Retry</Text>
          </TouchableOpacity>
        </View>
      ) : !topic ? (
        <View style={styles.center}>
          <Text style={styles.emptyTitle}>No topic configured</Text>
          <Text style={styles.emptyText}>
            Tap the gear icon to enter your ntfy topic name
          </Text>
        </View>
      ) : trades.length === 0 ? (
        <View style={styles.center}>
          <Text style={styles.emptyTitle}>No trades yet</Text>
          <Text style={styles.emptyText}>
            Pull down to refresh, or wait for the next morning scan
          </Text>
        </View>
      ) : (
        <SectionList
          sections={sections}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) => <TradeCard trade={item} />}
          renderSectionHeader={({ section }) => (
            <Text style={styles.sectionHeader}>{section.title}</Text>
          )}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
          }
          contentContainerStyle={styles.list}
          stickySectionHeadersEnabled={false}
        />
      )}

      <SettingsSheet
        visible={showSettings}
        topic={topic}
        onSave={saveTopic}
        onClose={() => setShowSettings(false)}
      />
    </SafeAreaView>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#f5f5f5",
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 20,
    paddingTop: 12,
    paddingBottom: 8,
    backgroundColor: "#fff",
    borderBottomWidth: 1,
    borderBottomColor: "#eee",
  },
  title: {
    fontSize: 24,
    fontWeight: "800",
    color: "#1a1a1a",
    letterSpacing: -0.5,
  },
  subtitle: {
    fontSize: 13,
    color: "#888",
    marginTop: 2,
  },
  settingsBtn: {
    padding: 8,
  },
  settingsIcon: {
    fontSize: 22,
  },
  list: {
    paddingVertical: 8,
    paddingBottom: 24,
  },
  sectionHeader: {
    fontSize: 13,
    fontWeight: "700",
    color: "#999",
    textTransform: "uppercase",
    letterSpacing: 0.5,
    paddingHorizontal: 20,
    paddingTop: 16,
    paddingBottom: 6,
  },
  center: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    padding: 40,
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: "700",
    color: "#1a1a1a",
    marginBottom: 8,
  },
  emptyText: {
    fontSize: 14,
    color: "#999",
    textAlign: "center",
    lineHeight: 20,
  },
  errorText: {
    fontSize: 14,
    color: "#C62828",
    textAlign: "center",
    marginBottom: 16,
  },
  retryBtn: {
    paddingHorizontal: 24,
    paddingVertical: 10,
    borderRadius: 8,
    backgroundColor: "#1a1a1a",
  },
  retryText: {
    fontSize: 14,
    fontWeight: "600",
    color: "#fff",
  },
});
