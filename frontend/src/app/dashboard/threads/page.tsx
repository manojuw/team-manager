"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useProject } from "@/hooks/use-project";
import { threads as threadsApi, dataSources } from "@/lib/api";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  MessageSquare,
  Users,
  Mic,
  Video,
  Calendar,
  Loader2,
  ChevronRight,
  GitBranch,
  CheckSquare,
  AlertCircle,
  Hash,
  Download,
  Eye,
  EyeOff,
  Filter,
  Clock,
} from "lucide-react";

interface Thread {
  id: string;
  segment_type: string;
  source_type: string;
  source_identifier: Record<string, string>;
  started_by: string;
  participants: string[];
  message_count: number;
  has_audio: boolean;
  has_video: boolean;
  started_at: string | null;
  last_message_at: string | null;
  created_at: string | null;
  summary: string;
  task_planning: string;
  review_status: string;
  viewed: boolean;
  data_source_id: string | null;
}

interface WorkItem {
  id: string;
  title: string;
  description: string;
  status: string;
  semantic_data_id: string | null;
  linked_to_devops: boolean;
  devops_work_item_id: string | null;
  created_at: string | null;
}

interface DataSource {
  id: string;
  name: string;
}

const SEGMENT_LABELS: Record<string, string> = {
  group_chat: "Group Chat",
  team_channel: "Channel",
  meeting: "Meeting",
};

const SEGMENT_COLORS: Record<string, string> = {
  group_chat: "bg-blue-100 text-blue-700 border-blue-200",
  team_channel: "bg-green-100 text-green-700 border-green-200",
  meeting: "bg-purple-100 text-purple-700 border-purple-200",
};

const REVIEW_STATUS_COLORS: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-700 border-yellow-200",
  ignore: "bg-gray-100 text-gray-500 border-gray-200",
  action_taken: "bg-green-100 text-green-700 border-green-200",
};

const REVIEW_STATUS_LABELS: Record<string, string> = {
  pending: "Pending",
  ignore: "Ignored",
  action_taken: "Action Taken",
};

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("en-IN", {
      day: "numeric", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function formatDateShort(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("en-IN", {
      day: "numeric", month: "short", year: "numeric",
    });
  } catch {
    return iso;
  }
}

function formatInline(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, "<code class=\"bg-muted px-1 rounded text-xs\">$1</code>");
}

function TaskPlanningRenderer({ markdown }: { markdown: string }) {
  if (!markdown) return <p className="text-muted-foreground text-sm">No task planning available.</p>;

  const lines = markdown.split("\n");
  const elements: React.ReactNode[] = [];
  let firstSection = true;

  lines.forEach((line, i) => {
    if (line.startsWith("## ")) {
      const headingMt = firstSection ? "mt-0" : "mt-4";
      firstSection = false;
      elements.push(
        <h3 key={i} className={`font-semibold text-sm ${headingMt} mb-2 text-foreground`}>
          {line.replace("## ", "")}
        </h3>
      );
    } else if (line.startsWith("### ")) {
      elements.push(
        <h4 key={i} className="font-medium text-sm mt-3 mb-1 text-foreground">
          {line.replace("### ", "")}
        </h4>
      );
    } else if (line.startsWith("- [ ] ")) {
      const content = line.replace("- [ ] ", "");
      elements.push(
        <div key={i} className="flex items-start gap-2 py-1">
          <CheckSquare className="h-4 w-4 text-muted-foreground mt-0.5 flex-shrink-0" />
          <span className="text-sm" dangerouslySetInnerHTML={{ __html: formatInline(content) }} />
        </div>
      );
    } else if (line.startsWith("- [x] ") || line.startsWith("- [X] ")) {
      const content = line.replace(/^- \[[xX]\] /, "");
      elements.push(
        <div key={i} className="flex items-start gap-2 py-1">
          <CheckSquare className="h-4 w-4 text-green-600 mt-0.5 flex-shrink-0" />
          <span className="text-sm line-through text-muted-foreground" dangerouslySetInnerHTML={{ __html: formatInline(content) }} />
        </div>
      );
    } else if (line.startsWith("- ")) {
      const content = line.replace("- ", "");
      elements.push(
        <div key={i} className="flex items-start gap-2 py-0.5">
          <span className="text-muted-foreground mt-1 flex-shrink-0">•</span>
          <span className="text-sm" dangerouslySetInnerHTML={{ __html: formatInline(content) }} />
        </div>
      );
    } else if (line.trim() === "") {
      elements.push(<div key={i} className="h-1" />);
    } else {
      elements.push(
        <p key={i} className="text-sm text-muted-foreground" dangerouslySetInnerHTML={{ __html: formatInline(line) }} />
      );
    }
  });

  return <div className="space-y-1">{elements}</div>;
}

export default function ThreadsPage() {
  const { currentProject } = useProject();
  const [threadList, setThreadList] = useState<Thread[]>([]);
  const [selectedThread, setSelectedThread] = useState<Thread | null>(null);
  const [workItems, setWorkItems] = useState<WorkItem[]>([]);
  const [loadingThreads, setLoadingThreads] = useState(false);
  const [loadingWorkItems, setLoadingWorkItems] = useState(false);
  const [downloadingTranscript, setDownloadingTranscript] = useState(false);
  const [updatingStatus, setUpdatingStatus] = useState(false);
  const [availableDataSources, setAvailableDataSources] = useState<DataSource[]>([]);

  const [filterDataSource, setFilterDataSource] = useState("all");
  const [filterSegmentType, setFilterSegmentType] = useState("all");
  const [filterViewed, setFilterViewed] = useState("all");
  const [filterReviewStatus, setFilterReviewStatus] = useState("all");
  const [filterDateFrom, setFilterDateFrom] = useState("");
  const [filterDateTo, setFilterDateTo] = useState("");

  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (currentProject) {
      fetchDataSources();
      fetchThreads();
      setSelectedThread(null);
      setWorkItems([]);
    }
  }, [currentProject?.id]);

  async function fetchDataSources() {
    if (!currentProject) return;
    try {
      const data = await threadsApi.getDataSources(currentProject.id);
      setAvailableDataSources(data.data_sources || []);
    } catch {
    }
  }

  function buildFilters() {
    const f: Record<string, string> = {};
    if (filterDataSource !== "all") f.data_source_id = filterDataSource;
    if (filterSegmentType !== "all") f.segment_type = filterSegmentType;
    if (filterViewed !== "all") f.viewed = filterViewed;
    if (filterReviewStatus !== "all") f.review_status = filterReviewStatus;
    if (filterDateFrom) f.date_from = filterDateFrom;
    if (filterDateTo) f.date_to = filterDateTo;
    return f;
  }

  async function fetchThreads() {
    if (!currentProject) return;
    setLoadingThreads(true);
    try {
      const data = await threadsApi.list(currentProject.id, buildFilters());
      setThreadList(data.threads || []);
    } catch (e) {
      toast.error("Failed to load threads");
    } finally {
      setLoadingThreads(false);
    }
  }

  const applyFilters = useCallback(() => {
    fetchThreads();
  }, [filterDataSource, filterSegmentType, filterViewed, filterReviewStatus, filterDateFrom, filterDateTo, currentProject?.id]);

  const selectThread = useCallback(async (thread: Thread) => {
    setSelectedThread(thread);
    setWorkItems([]);
    setLoadingWorkItems(true);

    if (!thread.viewed) {
      try {
        await threadsApi.updateStatus(thread.id, { viewed: true });
        setThreadList(prev => prev.map(t => t.id === thread.id ? { ...t, viewed: true } : t));
        thread = { ...thread, viewed: true };
        setSelectedThread({ ...thread, viewed: true });
      } catch {
      }
    }

    try {
      const data = await threadsApi.getWorkItems(thread.id);
      setWorkItems(data.work_items || []);
    } catch (e) {
      toast.error("Failed to load work items");
    } finally {
      setLoadingWorkItems(false);
    }
  }, []);

  async function handleReviewStatus(status: string) {
    if (!selectedThread) return;
    setUpdatingStatus(true);
    try {
      await threadsApi.updateStatus(selectedThread.id, { review_status: status });
      const updated = { ...selectedThread, review_status: status };
      setSelectedThread(updated);
      setThreadList(prev => prev.map(t => t.id === selectedThread.id ? { ...t, review_status: status } : t));
      toast.success("Status updated");
    } catch {
      toast.error("Failed to update status");
    } finally {
      setUpdatingStatus(false);
    }
  }

  async function handleDownloadTranscript() {
    if (!selectedThread) return;
    setDownloadingTranscript(true);
    try {
      const data = await threadsApi.getTranscript(selectedThread.id);
      const blob = new Blob([data.transcript], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const name = selectedThread.source_identifier?.channel_name ||
        selectedThread.source_identifier?.chat_name ||
        selectedThread.id.slice(0, 8);
      a.download = `thread-transcript-${name}.txt`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Failed to download transcript");
    } finally {
      setDownloadingTranscript(false);
    }
  }

  if (!currentProject) {
    return (
      <div className="flex items-center justify-center h-64 text-muted-foreground">
        Select a project to view threads.
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-8rem)] flex flex-col">
      <div className="mb-3 flex-shrink-0">
        <h1 className="text-2xl font-bold">Threads</h1>
        <p className="text-muted-foreground text-sm mt-0.5">
          Conversation threads with AI-generated summaries and task plans
        </p>
      </div>

      {/* Filter bar */}
      <div className="flex-shrink-0 flex flex-wrap items-end gap-2 mb-3 p-3 border rounded-lg bg-card">
        <Filter className="h-4 w-4 text-muted-foreground mt-1 flex-shrink-0" />

        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Data Source</span>
          <Select value={filterDataSource} onValueChange={setFilterDataSource}>
            <SelectTrigger className="h-8 w-44 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Sources</SelectItem>
              {availableDataSources.map(ds => (
                <SelectItem key={ds.id} value={ds.id}>{ds.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Type</span>
          <Select value={filterSegmentType} onValueChange={setFilterSegmentType}>
            <SelectTrigger className="h-8 w-36 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Types</SelectItem>
              <SelectItem value="group_chat">Group Chat</SelectItem>
              <SelectItem value="team_channel">Channel</SelectItem>
              <SelectItem value="meeting">Meeting</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Viewed</span>
          <Select value={filterViewed} onValueChange={setFilterViewed}>
            <SelectTrigger className="h-8 w-32 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="true">Viewed</SelectItem>
              <SelectItem value="false">Unviewed</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Review Status</span>
          <Select value={filterReviewStatus} onValueChange={setFilterReviewStatus}>
            <SelectTrigger className="h-8 w-40 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Statuses</SelectItem>
              <SelectItem value="pending">Pending</SelectItem>
              <SelectItem value="ignore">Ignored</SelectItem>
              <SelectItem value="action_taken">Action Taken</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">From</span>
          <input
            type="date"
            value={filterDateFrom}
            onChange={e => setFilterDateFrom(e.target.value)}
            className="h-8 px-2 text-xs border rounded-md bg-background"
          />
        </div>

        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">To</span>
          <input
            type="date"
            value={filterDateTo}
            onChange={e => setFilterDateTo(e.target.value)}
            className="h-8 px-2 text-xs border rounded-md bg-background"
          />
        </div>

        <Button size="sm" className="h-8 mt-auto" onClick={applyFilters} disabled={loadingThreads}>
          {loadingThreads ? <Loader2 className="h-3 w-3 animate-spin" /> : "Apply"}
        </Button>
        <Button size="sm" variant="ghost" className="h-8 mt-auto" onClick={() => {
          setFilterDataSource("all");
          setFilterSegmentType("all");
          setFilterViewed("all");
          setFilterReviewStatus("all");
          setFilterDateFrom("");
          setFilterDateTo("");
        }}>
          Clear
        </Button>
      </div>

      <div className="flex-1 flex gap-4 min-h-0 overflow-hidden">
        {/* Left panel — Thread list */}
        <div className="w-full lg:w-[42%] flex flex-col border rounded-lg bg-card overflow-hidden">
          <div className="px-4 py-3 border-b flex items-center justify-between flex-shrink-0">
            <span className="text-sm font-medium">
              {loadingThreads ? "Loading..." : `${threadList.length} thread${threadList.length !== 1 ? "s" : ""}`}
            </span>
            {loadingThreads && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
          </div>
          <div className="flex-1 overflow-y-auto" ref={listRef}>
            {loadingThreads ? (
              <div className="flex items-center justify-center h-40">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : threadList.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-40 text-muted-foreground">
                <MessageSquare className="h-8 w-8 mb-2 opacity-40" />
                <p className="text-sm">No threads found</p>
                <p className="text-xs mt-1">Sync a data source to get started</p>
              </div>
            ) : (
              <div className="divide-y">
                {threadList.map((thread) => {
                  const isSelected = selectedThread?.id === thread.id;
                  const label = SEGMENT_LABELS[thread.segment_type] || thread.segment_type;
                  const colorClass = SEGMENT_COLORS[thread.segment_type] || "bg-gray-100 text-gray-700 border-gray-200";
                  const location =
                    thread.source_identifier?.channel_name ||
                    thread.source_identifier?.chat_name ||
                    "";

                  return (
                    <button
                      key={thread.id}
                      onClick={() => selectThread(thread)}
                      className={`w-full text-left px-4 py-3 hover:bg-muted/50 transition-colors flex items-start gap-3 ${isSelected ? "bg-muted border-l-2 border-l-primary" : ""}`}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                          <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium border ${colorClass}`}>
                            {label}
                          </span>
                          {!thread.viewed && (
                            <span className="h-2 w-2 rounded-full bg-blue-500 flex-shrink-0" title="Unread" />
                          )}
                          {thread.review_status && thread.review_status !== "pending" && (
                            <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium border ${REVIEW_STATUS_COLORS[thread.review_status] || ""}`}>
                              {REVIEW_STATUS_LABELS[thread.review_status] || thread.review_status}
                            </span>
                          )}
                          {thread.has_audio && <Mic className="h-3 w-3 text-muted-foreground" />}
                          {thread.has_video && <Video className="h-3 w-3 text-muted-foreground" />}
                          {location && (
                            <span className="text-xs text-muted-foreground flex items-center gap-0.5 truncate">
                              <Hash className="h-3 w-3 flex-shrink-0" />
                              {location}
                            </span>
                          )}
                        </div>
                        <p className="text-sm font-medium text-foreground truncate">
                          {thread.started_by || "Unknown"}
                        </p>
                        {thread.summary ? (
                          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                            {thread.summary}
                          </p>
                        ) : (
                          <p className="text-xs text-muted-foreground mt-0.5 italic">No summary yet</p>
                        )}
                        <div className="flex items-center gap-3 mt-1.5 text-xs text-muted-foreground">
                          <span className="flex items-center gap-1">
                            <MessageSquare className="h-3 w-3" />
                            {thread.message_count}
                          </span>
                          <span className="flex items-center gap-1">
                            <Calendar className="h-3 w-3" />
                            {formatDateShort(thread.created_at || thread.started_at)}
                          </span>
                        </div>
                      </div>
                      <ChevronRight className={`h-4 w-4 text-muted-foreground flex-shrink-0 mt-1 transition-transform ${isSelected ? "rotate-90" : ""}`} />
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Right panel — Thread detail */}
        <div className="hidden lg:flex flex-col flex-1 border rounded-lg bg-card overflow-hidden">
          {!selectedThread ? (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
              <MessageSquare className="h-12 w-12 mb-3 opacity-30" />
              <p className="font-medium">Select a thread to view details</p>
              <p className="text-sm mt-1">Click any thread on the left to see its summary and task plan</p>
            </div>
          ) : (
            <div className="flex-1 overflow-y-auto">
              <div className="p-6 space-y-6">
                {/* Thread header */}
                <div>
                  <div className="flex items-center gap-2 flex-wrap mb-3">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${SEGMENT_COLORS[selectedThread.segment_type] || "bg-gray-100 text-gray-700 border-gray-200"}`}>
                      {SEGMENT_LABELS[selectedThread.segment_type] || selectedThread.segment_type}
                    </span>
                    {selectedThread.has_audio && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-orange-100 text-orange-700 border border-orange-200">
                        <Mic className="h-3 w-3" /> Audio
                      </span>
                    )}
                    {selectedThread.has_video && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700 border border-red-200">
                        <Video className="h-3 w-3" /> Video
                      </span>
                    )}
                    <div className="ml-auto flex items-center gap-2 flex-wrap">
                      {(selectedThread.has_audio || selectedThread.has_video) && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7 text-xs gap-1"
                          onClick={handleDownloadTranscript}
                          disabled={downloadingTranscript}
                        >
                          {downloadingTranscript
                            ? <Loader2 className="h-3 w-3 animate-spin" />
                            : <Download className="h-3 w-3" />}
                          Transcript
                        </Button>
                      )}
                      <Select
                        value={selectedThread.review_status || "pending"}
                        onValueChange={handleReviewStatus}
                        disabled={updatingStatus}
                      >
                        <SelectTrigger className={`h-7 w-36 text-xs border ${REVIEW_STATUS_COLORS[selectedThread.review_status] || REVIEW_STATUS_COLORS.pending}`}>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="pending">Pending</SelectItem>
                          <SelectItem value="ignore">Ignore</SelectItem>
                          <SelectItem value="action_taken">Action Taken</SelectItem>
                        </SelectContent>
                      </Select>
                      {selectedThread.viewed
                        ? <Eye className="h-4 w-4 text-muted-foreground" title="Viewed" />
                        : <EyeOff className="h-4 w-4 text-muted-foreground" title="Not viewed" />}
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-muted-foreground text-xs uppercase tracking-wide">Started by</span>
                      <p className="font-medium mt-0.5">{selectedThread.started_by || "—"}</p>
                    </div>
                    <div>
                      <span className="text-muted-foreground text-xs uppercase tracking-wide">Start Date/Time</span>
                      <p className="font-medium mt-0.5 flex items-center gap-1">
                        <Clock className="h-3 w-3 text-muted-foreground" />
                        {formatDate(selectedThread.started_at)}
                      </p>
                    </div>
                    <div>
                      <span className="text-muted-foreground text-xs uppercase tracking-wide">End Date/Time</span>
                      <p className="font-medium mt-0.5 flex items-center gap-1">
                        <Clock className="h-3 w-3 text-muted-foreground" />
                        {formatDate(selectedThread.last_message_at)}
                      </p>
                    </div>
                    <div>
                      <span className="text-muted-foreground text-xs uppercase tracking-wide">Messages</span>
                      <p className="font-medium mt-0.5">{selectedThread.message_count}</p>
                    </div>
                    <div className="col-span-2">
                      <span className="text-muted-foreground text-xs uppercase tracking-wide">Location</span>
                      <p className="font-medium mt-0.5 truncate">
                        {selectedThread.source_identifier?.channel_name ||
                          selectedThread.source_identifier?.chat_name ||
                          selectedThread.source_identifier?.team_name ||
                          "—"}
                      </p>
                    </div>
                  </div>

                  {selectedThread.participants && selectedThread.participants.length > 0 && (
                    <div className="mt-3">
                      <span className="text-muted-foreground text-xs uppercase tracking-wide flex items-center gap-1 mb-1.5">
                        <Users className="h-3 w-3" /> Participants
                      </span>
                      <div className="flex flex-wrap gap-1.5">
                        {selectedThread.participants.slice(0, 12).map((p, i) => (
                          <span key={i} className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-muted text-muted-foreground">
                            {p}
                          </span>
                        ))}
                        {selectedThread.participants.length > 12 && (
                          <span className="text-xs text-muted-foreground px-1 py-0.5">
                            +{selectedThread.participants.length - 12} more
                          </span>
                        )}
                      </div>
                    </div>
                  )}
                </div>

                <Separator />

                {/* Summary */}
                <div>
                  <h2 className="text-base font-semibold mb-2">Summary</h2>
                  {selectedThread.summary ? (
                    <p className="text-sm text-muted-foreground leading-relaxed">
                      {selectedThread.summary}
                    </p>
                  ) : (
                    <p className="text-sm text-muted-foreground italic">
                      No summary available. Re-sync to generate.
                    </p>
                  )}
                </div>

                <Separator />

                {/* Task Planning */}
                <div>
                  <h2 className="text-base font-semibold mb-3">Task Planning</h2>
                  {selectedThread.task_planning ? (
                    <div className="rounded-lg p-4 border bg-muted/30">
                      <TaskPlanningRenderer markdown={selectedThread.task_planning} />
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground italic">
                      No task plan available. Re-sync to generate.
                    </p>
                  )}
                </div>

                <Separator />

                {/* Suggested Work Items */}
                <div>
                  <h2 className="text-base font-semibold mb-3 flex items-center gap-2">
                    Suggested Work Items
                    {loadingWorkItems && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
                    {!loadingWorkItems && (
                      <span className="text-xs font-normal text-muted-foreground">
                        ({workItems.length})
                      </span>
                    )}
                  </h2>
                  {loadingWorkItems ? (
                    <div className="flex items-center justify-center h-20">
                      <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                    </div>
                  ) : workItems.length === 0 ? (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
                      <AlertCircle className="h-4 w-4" />
                      No suggested work items for this thread.
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {workItems.map((item) => (
                        <div key={item.id} className="rounded-lg border bg-card p-4">
                          <div className="flex items-start justify-between gap-2">
                            <p className="text-sm font-medium leading-snug">{item.title}</p>
                            <div className="flex items-center gap-1.5 flex-shrink-0">
                              {item.linked_to_devops && (
                                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700 border border-green-200">
                                  <GitBranch className="h-3 w-3" />
                                  {item.devops_work_item_id ? `#${item.devops_work_item_id}` : "DevOps"}
                                </span>
                              )}
                              <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium border ${
                                item.status === "done"
                                  ? "bg-green-100 text-green-700 border-green-200"
                                  : item.status === "in_progress"
                                  ? "bg-yellow-100 text-yellow-700 border-yellow-200"
                                  : "bg-gray-100 text-gray-600 border-gray-200"
                              }`}>
                                {item.status}
                              </span>
                            </div>
                          </div>
                          {item.description && (
                            <p className="text-xs text-muted-foreground mt-2 leading-relaxed line-clamp-3">
                              {item.description}
                            </p>
                          )}
                          {item.created_at && (
                            <p className="text-xs text-muted-foreground mt-2">
                              {formatDate(item.created_at)}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
