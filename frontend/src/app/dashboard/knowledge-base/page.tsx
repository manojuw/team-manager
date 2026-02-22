"use client";

import { useEffect, useState } from "react";
import { useProject } from "@/hooks/use-project";
import { ai, sync } from "@/lib/api";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  BookOpen,
  Search,
  FileText,
  Trash2,
  BarChart3,
  RefreshCw,
  Loader2,
  AlertTriangle,
} from "lucide-react";

interface Stats {
  total_messages: number;
  unique_teams: number;
  unique_channels: number;
  unique_senders: number;
}

interface SyncRecord {
  id?: string;
  project_id?: string;
  source_type?: string;
  team_name?: string;
  channel_name?: string;
  chat_name?: string;
  messages_synced?: number;
  status?: string;
  synced_at?: string;
  created_at?: string;
}

interface SearchResult {
  content: string;
  sender?: string;
  team_name?: string;
  channel_name?: string;
  date?: string;
  similarity?: number;
  score?: number;
}

export default function KnowledgeBasePage() {
  const { currentProject } = useProject();
  const [stats, setStats] = useState<Stats | null>(null);
  const [loadingStats, setLoadingStats] = useState(false);
  const [syncHistory, setSyncHistory] = useState<SyncRecord[]>([]);
  const [loadingSyncHistory, setLoadingSyncHistory] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [clearing, setClearing] = useState(false);

  useEffect(() => {
    if (!currentProject) return;
    fetchStats();
    fetchSyncHistory();
  }, [currentProject?.id]);

  async function fetchStats() {
    if (!currentProject) return;
    setLoadingStats(true);
    try {
      const data = await ai.stats(currentProject.id);
      setStats(data);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load stats");
    } finally {
      setLoadingStats(false);
    }
  }

  async function fetchSyncHistory() {
    if (!currentProject) return;
    setLoadingSyncHistory(true);
    try {
      const data = await sync.history(currentProject.id);
      setSyncHistory(Array.isArray(data) ? data : data.history || []);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load sync history");
    } finally {
      setLoadingSyncHistory(false);
    }
  }

  async function handleSearch() {
    if (!currentProject || !searchQuery.trim()) return;
    setSearching(true);
    try {
      const data = await ai.search({ project_id: currentProject.id, query: searchQuery });
      setSearchResults(data.results || data || []);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Search failed");
    } finally {
      setSearching(false);
    }
  }

  async function handleClearData() {
    if (!currentProject) return;
    if (!confirm("Are you sure you want to clear all data? This action cannot be undone.")) return;
    setClearing(true);
    try {
      await ai.clearData(currentProject.id);
      toast.success("All data cleared successfully");
      setStats(null);
      setSyncHistory([]);
      setSearchResults([]);
      fetchStats();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to clear data");
    } finally {
      setClearing(false);
    }
  }

  if (!currentProject) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Knowledge Base</h1>
          <p className="text-muted-foreground">View and search your synced data</p>
        </div>
        <Separator />
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <BookOpen className="size-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold">No project selected</h3>
          <p className="text-muted-foreground mt-1">
            Please select a project first from the Projects page
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Knowledge Base</h1>
          <p className="text-muted-foreground">
            View and search synced data for{" "}
            <span className="font-medium text-foreground">{currentProject.name}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => { fetchStats(); fetchSyncHistory(); }}>
            <RefreshCw className="size-4" />
            Refresh
          </Button>
          <Button variant="destructive" size="sm" onClick={handleClearData} disabled={clearing}>
            {clearing ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                Clearing…
              </>
            ) : (
              <>
                <Trash2 className="size-4" />
                Clear All Data
              </>
            )}
          </Button>
        </div>
      </div>

      <Separator />

      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Total Messages</CardDescription>
            <CardTitle className="text-2xl flex items-center gap-2">
              <FileText className="size-5 text-muted-foreground" />
              {loadingStats ? <Loader2 className="size-5 animate-spin" /> : (stats?.total_messages ?? 0)}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Unique Teams</CardDescription>
            <CardTitle className="text-2xl flex items-center gap-2">
              <BarChart3 className="size-5 text-muted-foreground" />
              {loadingStats ? <Loader2 className="size-5 animate-spin" /> : (stats?.unique_teams ?? 0)}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Unique Channels</CardDescription>
            <CardTitle className="text-2xl flex items-center gap-2">
              <BarChart3 className="size-5 text-muted-foreground" />
              {loadingStats ? <Loader2 className="size-5 animate-spin" /> : (stats?.unique_channels ?? 0)}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Unique Senders</CardDescription>
            <CardTitle className="text-2xl flex items-center gap-2">
              <BarChart3 className="size-5 text-muted-foreground" />
              {loadingStats ? <Loader2 className="size-5 animate-spin" /> : (stats?.unique_senders ?? 0)}
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Search className="size-4" />
            Search Knowledge Base
          </CardTitle>
          <CardDescription>Search through your synced messages using semantic search</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            <Input
              placeholder="Search your knowledge base…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            />
            <Button onClick={handleSearch} disabled={searching || !searchQuery.trim()}>
              {searching ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Search className="size-4" />
              )}
              Search
            </Button>
          </div>

          {searchResults.length > 0 && (
            <div className="mt-4 space-y-3">
              {searchResults.map((result, index) => (
                <div key={index} className="rounded-md border p-4 space-y-2">
                  <p className="text-sm">{result.content}</p>
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    {result.sender && (
                      <Badge variant="outline">{result.sender}</Badge>
                    )}
                    {result.team_name && (
                      <Badge variant="secondary">{result.team_name}</Badge>
                    )}
                    {result.channel_name && (
                      <Badge variant="secondary">{result.channel_name}</Badge>
                    )}
                    {result.date && <span>{new Date(result.date).toLocaleString()}</span>}
                    {(result.similarity ?? result.score) != null && (
                      <Badge variant="default">
                        {((result.similarity ?? result.score ?? 0) * 100).toFixed(1)}% match
                      </Badge>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <RefreshCw className="size-4" />
            Sync History
          </CardTitle>
          <CardDescription>History of data synchronization operations</CardDescription>
        </CardHeader>
        <CardContent>
          {loadingSyncHistory ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="size-6 animate-spin text-muted-foreground" />
            </div>
          ) : syncHistory.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <AlertTriangle className="size-8 text-muted-foreground mb-2" />
              <p className="text-sm text-muted-foreground">No sync history yet</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Timestamp</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Messages Synced</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {syncHistory.map((record, index) => (
                  <TableRow key={record.id || index}>
                    <TableCell className="text-sm">
                      {record.synced_at || record.created_at
                        ? new Date(record.synced_at || record.created_at || "").toLocaleString()
                        : "—"}
                    </TableCell>
                    <TableCell className="text-sm">
                      {record.chat_name
                        ? record.chat_name
                        : [record.team_name, record.channel_name].filter(Boolean).join(" / ") || record.source_type || "—"}
                    </TableCell>
                    <TableCell className="text-sm">{record.messages_synced ?? "—"}</TableCell>
                    <TableCell>
                      <Badge variant={record.status === "success" ? "default" : record.status === "error" ? "destructive" : "secondary"}>
                        {record.status || "unknown"}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
