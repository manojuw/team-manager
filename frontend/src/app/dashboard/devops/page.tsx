"use client";

import { useEffect, useState } from "react";
import { useProject } from "@/hooks/use-project";
import { devopsStats } from "@/lib/api";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  GitBranch,
  Bug,
  CheckCircle2,
  Clock,
  Loader2,
  RefreshCw,
  AlertTriangle,
  ListChecks,
  MessageSquare,
  BarChart3,
  Circle,
  Bookmark,
  Layers,
} from "lucide-react";

interface DevOpsStatsData {
  total_work_items: number;
  by_type: Record<string, number>;
  by_state: Record<string, number>;
  total_comments: number;
}

const STATE_COLORS: Record<string, string> = {
  "New": "bg-blue-500",
  "To Do": "bg-blue-500",
  "Active": "bg-yellow-500",
  "In Progress": "bg-yellow-500",
  "Doing": "bg-yellow-500",
  "Resolved": "bg-purple-500",
  "Done": "bg-green-500",
  "Closed": "bg-green-600",
  "Removed": "bg-red-500",
};

const TYPE_ICONS: Record<string, typeof Bug> = {
  "Bug": Bug,
  "Task": ListChecks,
  "User Story": Bookmark,
  "Feature": Layers,
  "Epic": Layers,
};

function getStateColor(state: string): string {
  return STATE_COLORS[state] || "bg-gray-500";
}

export default function DevOpsPage() {
  const { currentProject } = useProject();
  const [stats, setStats] = useState<DevOpsStatsData | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (currentProject) {
      fetchStats();
    }
  }, [currentProject?.id]);

  async function fetchStats() {
    if (!currentProject) return;
    setLoading(true);
    try {
      const data = await devopsStats.get(currentProject.id);
      setStats(data);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load DevOps stats");
    } finally {
      setLoading(false);
    }
  }

  if (!currentProject) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Azure DevOps</h1>
          <p className="text-muted-foreground">Project status and work item breakdown</p>
        </div>
        <Separator />
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <GitBranch className="size-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold">No project selected</h3>
          <p className="text-muted-foreground mt-1">
            Please select a project first from the Projects page
          </p>
        </div>
      </div>
    );
  }

  const totalOpen = stats
    ? Object.entries(stats.by_state)
        .filter(([s]) => !["Done", "Closed", "Resolved", "Removed"].includes(s))
        .reduce((sum, [, count]) => sum + count, 0)
    : 0;

  const totalClosed = stats
    ? Object.entries(stats.by_state)
        .filter(([s]) => ["Done", "Closed", "Resolved"].includes(s))
        .reduce((sum, [, count]) => sum + count, 0)
    : 0;

  const progressPercent =
    stats && stats.total_work_items > 0
      ? Math.round((totalClosed / stats.total_work_items) * 100)
      : 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Azure DevOps</h1>
          <p className="text-muted-foreground">
            Work item dashboard for{" "}
            <span className="font-medium text-foreground">{currentProject.name}</span>
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchStats} disabled={loading}>
          {loading ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <RefreshCw className="size-4" />
          )}
          Refresh
        </Button>
      </div>

      <Separator />

      {loading && !stats ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="size-8 animate-spin text-muted-foreground" />
        </div>
      ) : !stats || stats.total_work_items === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <AlertTriangle className="size-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold">No DevOps data yet</h3>
          <p className="text-muted-foreground mt-1">
            Add an Azure DevOps connector and sync a project to see data here
          </p>
        </div>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-4">
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>Total Work Items</CardDescription>
                <CardTitle className="text-2xl flex items-center gap-2">
                  <GitBranch className="size-5 text-muted-foreground" />
                  {stats.total_work_items}
                </CardTitle>
              </CardHeader>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>Open</CardDescription>
                <CardTitle className="text-2xl flex items-center gap-2">
                  <Clock className="size-5 text-yellow-500" />
                  {totalOpen}
                </CardTitle>
              </CardHeader>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>Closed / Done</CardDescription>
                <CardTitle className="text-2xl flex items-center gap-2">
                  <CheckCircle2 className="size-5 text-green-500" />
                  {totalClosed}
                </CardTitle>
              </CardHeader>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>Comments</CardDescription>
                <CardTitle className="text-2xl flex items-center gap-2">
                  <MessageSquare className="size-5 text-muted-foreground" />
                  {stats.total_comments}
                </CardTitle>
              </CardHeader>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BarChart3 className="size-4" />
                Sprint Progress
              </CardTitle>
              <CardDescription>Overall completion across all work items</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">
                    {totalClosed} of {stats.total_work_items} completed
                  </span>
                  <span className="font-medium">{progressPercent}%</span>
                </div>
                <div className="h-3 w-full rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full rounded-full bg-green-500 transition-all duration-500"
                    style={{ width: `${progressPercent}%` }}
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Circle className="size-4" />
                  Work Items by State
                </CardTitle>
                <CardDescription>Breakdown of work items by current state</CardDescription>
              </CardHeader>
              <CardContent>
                {Object.keys(stats.by_state).length === 0 ? (
                  <p className="text-sm text-muted-foreground">No state data available</p>
                ) : (
                  <div className="space-y-3">
                    {Object.entries(stats.by_state)
                      .sort(([, a], [, b]) => b - a)
                      .map(([state, count]) => {
                        const pct = Math.round((count / stats.total_work_items) * 100);
                        return (
                          <div key={state} className="space-y-1.5">
                            <div className="flex items-center justify-between text-sm">
                              <div className="flex items-center gap-2">
                                <div className={`size-2.5 rounded-full ${getStateColor(state)}`} />
                                <span>{state}</span>
                              </div>
                              <span className="text-muted-foreground">
                                {count} ({pct}%)
                              </span>
                            </div>
                            <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                              <div
                                className={`h-full rounded-full ${getStateColor(state)} transition-all duration-500`}
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                          </div>
                        );
                      })}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Layers className="size-4" />
                  Work Items by Type
                </CardTitle>
                <CardDescription>Breakdown of work items by type</CardDescription>
              </CardHeader>
              <CardContent>
                {Object.keys(stats.by_type).length === 0 ? (
                  <p className="text-sm text-muted-foreground">No type data available</p>
                ) : (
                  <div className="space-y-3">
                    {Object.entries(stats.by_type)
                      .sort(([, a], [, b]) => b - a)
                      .map(([type, count]) => {
                        const Icon = TYPE_ICONS[type] || GitBranch;
                        return (
                          <div
                            key={type}
                            className="flex items-center justify-between rounded-md border p-3"
                          >
                            <div className="flex items-center gap-3">
                              <Icon className="size-4 text-muted-foreground" />
                              <span className="text-sm font-medium">{type}</span>
                            </div>
                            <Badge variant="secondary">{count}</Badge>
                          </div>
                        );
                      })}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
