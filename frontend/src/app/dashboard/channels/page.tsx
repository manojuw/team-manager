"use client";

import { useEffect, useState } from "react";
import { useProject } from "@/hooks/use-project";
import { teams, dataSources } from "@/lib/api";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { Hash, RefreshCw, CheckCircle, Loader2 } from "lucide-react";

interface Team {
  id: string;
  displayName: string;
  description?: string;
}

interface Channel {
  id: string;
  displayName: string;
  description?: string;
}

export default function ChannelsPage() {
  const { currentProject } = useProject();
  const [dataSourceId, setDataSourceId] = useState<string | null>(null);
  const [loadingSource, setLoadingSource] = useState(true);
  const [noTeamsSource, setNoTeamsSource] = useState(false);

  const [teamsList, setTeamsList] = useState<Team[]>([]);
  const [loadingTeams, setLoadingTeams] = useState(false);
  const [selectedTeamId, setSelectedTeamId] = useState<string>("");
  const [selectedTeamName, setSelectedTeamName] = useState<string>("");

  const [channels, setChannels] = useState<Channel[]>([]);
  const [loadingChannels, setLoadingChannels] = useState(false);
  const [selectedChannelIds, setSelectedChannelIds] = useState<Set<string>>(new Set());

  const [syncingChannelId, setSyncingChannelId] = useState<string | null>(null);
  const [syncingAll, setSyncingAll] = useState(false);
  const [syncProgress, setSyncProgress] = useState({ current: 0, total: 0 });
  const [syncedChannelIds, setSyncedChannelIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    async function fetchDataSource() {
      if (!currentProject) {
        setLoadingSource(false);
        return;
      }
      setLoadingSource(true);
      setNoTeamsSource(false);
      try {
        const sources = await dataSources.list(currentProject.id);
        const teamsSource = sources.find(
          (s: { source_type: string }) => s.source_type === "microsoft_teams"
        );
        if (teamsSource) {
          setDataSourceId(teamsSource.id);
        } else {
          setNoTeamsSource(true);
        }
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Failed to load data sources");
      } finally {
        setLoadingSource(false);
      }
    }
    fetchDataSource();
  }, [currentProject?.id]);

  useEffect(() => {
    async function fetchTeams() {
      if (!dataSourceId) return;
      setLoadingTeams(true);
      try {
        const data = await teams.listTeams(dataSourceId);
        setTeamsList(data.teams || data || []);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Failed to load teams");
      } finally {
        setLoadingTeams(false);
      }
    }
    fetchTeams();
  }, [dataSourceId]);

  useEffect(() => {
    async function fetchChannels() {
      if (!dataSourceId || !selectedTeamId) return;
      setLoadingChannels(true);
      setChannels([]);
      setSelectedChannelIds(new Set());
      setSyncedChannelIds(new Set());
      try {
        const data = await teams.listChannels(dataSourceId, selectedTeamId);
        setChannels(data.channels || data || []);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Failed to load channels");
      } finally {
        setLoadingChannels(false);
      }
    }
    fetchChannels();
  }, [dataSourceId, selectedTeamId]);

  function toggleChannel(channelId: string) {
    setSelectedChannelIds((prev) => {
      const next = new Set(prev);
      if (next.has(channelId)) {
        next.delete(channelId);
      } else {
        next.add(channelId);
      }
      return next;
    });
  }

  function toggleAll() {
    if (selectedChannelIds.size === channels.length) {
      setSelectedChannelIds(new Set());
    } else {
      setSelectedChannelIds(new Set(channels.map((c) => c.id)));
    }
  }

  async function syncChannel(channel: Channel) {
    if (!currentProject || !dataSourceId || !selectedTeamId) return;
    setSyncingChannelId(channel.id);
    try {
      await teams.syncChannel({
        project_id: currentProject.id,
        data_source_id: dataSourceId,
        team_id: selectedTeamId,
        team_name: selectedTeamName,
        channel_id: channel.id,
        channel_name: channel.displayName,
      });
      toast.success(`Synced "${channel.displayName}"`);
      setSyncedChannelIds((prev) => new Set(prev).add(channel.id));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : `Failed to sync "${channel.displayName}"`);
    } finally {
      setSyncingChannelId(null);
    }
  }

  async function syncAllSelected() {
    if (!currentProject || !dataSourceId || !selectedTeamId) return;
    const selected = channels.filter((c) => selectedChannelIds.has(c.id));
    if (selected.length === 0) {
      toast.error("No channels selected");
      return;
    }
    setSyncingAll(true);
    setSyncProgress({ current: 0, total: selected.length });

    let successCount = 0;
    let failCount = 0;

    for (let i = 0; i < selected.length; i++) {
      const channel = selected[i];
      setSyncProgress({ current: i + 1, total: selected.length });
      setSyncingChannelId(channel.id);
      try {
        await teams.syncChannel({
          project_id: currentProject.id,
          data_source_id: dataSourceId,
          team_id: selectedTeamId,
          team_name: selectedTeamName,
          channel_id: channel.id,
          channel_name: channel.displayName,
        });
        setSyncedChannelIds((prev) => new Set(prev).add(channel.id));
        successCount++;
      } catch {
        failCount++;
      }
    }

    setSyncingChannelId(null);
    setSyncingAll(false);

    if (failCount === 0) {
      toast.success(`Successfully synced ${successCount} channel(s)`);
    } else {
      toast.warning(`Synced ${successCount}, failed ${failCount} channel(s)`);
    }
  }

  if (!currentProject) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Channels</h1>
          <p className="text-muted-foreground">Sync Microsoft Teams channels</p>
        </div>
        <Separator />
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Hash className="size-12 text-muted-foreground mb-4" />
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
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Channels</h1>
        <p className="text-muted-foreground">
          Sync Microsoft Teams channels for{" "}
          <span className="font-medium text-foreground">{currentProject.name}</span>
        </p>
      </div>

      <Separator />

      {loadingSource ? (
        <div className="space-y-4">
          <Skeleton className="h-10 w-64" />
          <Skeleton className="h-10 w-64" />
          <Card>
            <CardHeader>
              <Skeleton className="h-5 w-40" />
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-8 w-full" />
              </div>
            </CardContent>
          </Card>
        </div>
      ) : noTeamsSource ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Hash className="size-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold">No Microsoft Teams data source</h3>
          <p className="text-muted-foreground mt-1">
            Please add a Microsoft Teams data source in the Data Sources tab first
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Hash className="size-4" />
                Select Team
              </CardTitle>
            </CardHeader>
            <CardContent>
              {loadingTeams ? (
                <Skeleton className="h-10 w-full max-w-sm" />
              ) : (
                <Select
                  value={selectedTeamId}
                  onValueChange={(value) => {
                    setSelectedTeamId(value);
                    const team = teamsList.find((t) => t.id === value);
                    setSelectedTeamName(team?.displayName || "");
                  }}
                >
                  <SelectTrigger className="w-full max-w-sm">
                    <SelectValue placeholder="Choose a team..." />
                  </SelectTrigger>
                  <SelectContent>
                    {teamsList.map((team) => (
                      <SelectItem key={team.id} value={team.id}>
                        {team.displayName}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </CardContent>
          </Card>

          {selectedTeamId && (
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="flex items-center gap-2">
                    <Hash className="size-4" />
                    Channels
                    {channels.length > 0 && (
                      <Badge variant="secondary">{channels.length}</Badge>
                    )}
                  </CardTitle>
                  {channels.length > 0 && (
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={toggleAll}
                      >
                        {selectedChannelIds.size === channels.length
                          ? "Deselect All"
                          : "Select All"}
                      </Button>
                    </div>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                {loadingChannels ? (
                  <div className="space-y-3">
                    {[1, 2, 3, 4].map((i) => (
                      <div key={i} className="flex items-center gap-3">
                        <Skeleton className="size-4" />
                        <Skeleton className="h-4 w-48" />
                        <Skeleton className="ml-auto h-8 w-16" />
                      </div>
                    ))}
                  </div>
                ) : channels.length === 0 ? (
                  <p className="text-muted-foreground text-sm py-4 text-center">
                    No channels found for this team
                  </p>
                ) : (
                  <div className="space-y-1">
                    {channels.map((channel) => (
                      <div
                        key={channel.id}
                        className="flex items-center gap-3 rounded-md border px-4 py-3 hover:bg-accent/50 transition-colors"
                      >
                        <Checkbox
                          checked={selectedChannelIds.has(channel.id)}
                          onCheckedChange={() => toggleChannel(channel.id)}
                          disabled={syncingAll}
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <Hash className="size-3.5 text-muted-foreground shrink-0" />
                            <span className="font-medium text-sm truncate">
                              {channel.displayName}
                            </span>
                            {syncedChannelIds.has(channel.id) && (
                              <CheckCircle className="size-3.5 text-green-500 shrink-0" />
                            )}
                          </div>
                          {channel.description && (
                            <p className="text-xs text-muted-foreground mt-0.5 truncate pl-5">
                              {channel.description}
                            </p>
                          )}
                        </div>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={syncingChannelId === channel.id || syncingAll}
                          onClick={() => syncChannel(channel)}
                        >
                          {syncingChannelId === channel.id ? (
                            <>
                              <Loader2 className="size-3 animate-spin" />
                              Syncing
                            </>
                          ) : (
                            <>
                              <RefreshCw className="size-3" />
                              Sync
                            </>
                          )}
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {selectedTeamId && channels.length > 0 && (
            <div className="flex items-center justify-between">
              <div className="text-sm text-muted-foreground">
                {selectedChannelIds.size} of {channels.length} channel(s) selected
                {syncingAll && (
                  <span className="ml-2">
                    — Syncing {syncProgress.current}/{syncProgress.total}
                  </span>
                )}
              </div>
              <Button
                onClick={syncAllSelected}
                disabled={selectedChannelIds.size === 0 || syncingAll}
              >
                {syncingAll ? (
                  <>
                    <Loader2 className="size-4 animate-spin" />
                    Syncing {syncProgress.current}/{syncProgress.total}
                  </>
                ) : (
                  <>
                    <RefreshCw className="size-4" />
                    Sync All Selected
                  </>
                )}
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
