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
import { Separator } from "@/components/ui/separator";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { MessageSquare, RefreshCw, CheckCircle, Loader2, Users } from "lucide-react";

interface User {
  id: string;
  displayName: string;
  mail?: string;
}

interface GroupChat {
  id: string;
  topic?: string;
  chatType?: string;
  members?: Array<{ displayName?: string; userId?: string }>;
}

export default function GroupChatsPage() {
  const { currentProject } = useProject();
  const [dataSourceId, setDataSourceId] = useState<string | null>(null);
  const [loadingSource, setLoadingSource] = useState(true);
  const [noTeamsSource, setNoTeamsSource] = useState(false);

  const [users, setUsers] = useState<User[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [selectedUserIds, setSelectedUserIds] = useState<Set<string>>(new Set());

  const [groupChats, setGroupChats] = useState<GroupChat[]>([]);
  const [loadingChats, setLoadingChats] = useState(false);
  const [selectedChatIds, setSelectedChatIds] = useState<Set<string>>(new Set());

  const [syncingChatId, setSyncingChatId] = useState<string | null>(null);
  const [syncingAll, setSyncingAll] = useState(false);
  const [syncProgress, setSyncProgress] = useState({ current: 0, total: 0 });
  const [syncedChatIds, setSyncedChatIds] = useState<Set<string>>(new Set());

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
    async function fetchUsers() {
      if (!dataSourceId) return;
      setLoadingUsers(true);
      try {
        const data = await teams.listUsers(dataSourceId);
        setUsers(data.users || data || []);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Failed to load users");
      } finally {
        setLoadingUsers(false);
      }
    }
    fetchUsers();
  }, [dataSourceId]);

  function toggleUser(userId: string) {
    setSelectedUserIds((prev) => {
      const next = new Set(prev);
      if (next.has(userId)) {
        next.delete(userId);
      } else {
        next.add(userId);
      }
      return next;
    });
  }

  function toggleAllUsers() {
    if (selectedUserIds.size === users.length) {
      setSelectedUserIds(new Set());
    } else {
      setSelectedUserIds(new Set(users.map((u) => u.id)));
    }
  }

  function toggleChat(chatId: string) {
    setSelectedChatIds((prev) => {
      const next = new Set(prev);
      if (next.has(chatId)) {
        next.delete(chatId);
      } else {
        next.add(chatId);
      }
      return next;
    });
  }

  function toggleAllChats() {
    if (selectedChatIds.size === groupChats.length) {
      setSelectedChatIds(new Set());
    } else {
      setSelectedChatIds(new Set(groupChats.map((c) => c.id)));
    }
  }

  async function loadGroupChats() {
    if (!dataSourceId || selectedUserIds.size === 0) {
      toast.error("Please select at least one user");
      return;
    }
    setLoadingChats(true);
    setGroupChats([]);
    setSelectedChatIds(new Set());
    setSyncedChatIds(new Set());
    try {
      const data = await teams.listGroupChats(dataSourceId, Array.from(selectedUserIds));
      setGroupChats(data.chats || data || []);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load group chats");
    } finally {
      setLoadingChats(false);
    }
  }

  function getChatDisplayName(chat: GroupChat) {
    if (chat.topic) return chat.topic;
    if (chat.members && chat.members.length > 0) {
      return chat.members
        .map((m) => m.displayName)
        .filter(Boolean)
        .slice(0, 3)
        .join(", ") + (chat.members.length > 3 ? "..." : "");
    }
    return "Unnamed Chat";
  }

  async function syncChat(chat: GroupChat) {
    if (!currentProject || !dataSourceId) return;
    setSyncingChatId(chat.id);
    try {
      await teams.syncGroupChat({
        project_id: currentProject.id,
        data_source_id: dataSourceId,
        chat_id: chat.id,
        chat_name: getChatDisplayName(chat),
      });
      toast.success(`Synced "${getChatDisplayName(chat)}"`);
      setSyncedChatIds((prev) => new Set(prev).add(chat.id));
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : `Failed to sync "${getChatDisplayName(chat)}"`
      );
    } finally {
      setSyncingChatId(null);
    }
  }

  async function syncAllSelected() {
    if (!currentProject || !dataSourceId) return;
    const selected = groupChats.filter((c) => selectedChatIds.has(c.id));
    if (selected.length === 0) {
      toast.error("No chats selected");
      return;
    }
    setSyncingAll(true);
    setSyncProgress({ current: 0, total: selected.length });

    let successCount = 0;
    let failCount = 0;

    for (let i = 0; i < selected.length; i++) {
      const chat = selected[i];
      setSyncProgress({ current: i + 1, total: selected.length });
      setSyncingChatId(chat.id);
      try {
        await teams.syncGroupChat({
          project_id: currentProject.id,
          data_source_id: dataSourceId,
          chat_id: chat.id,
          chat_name: getChatDisplayName(chat),
        });
        setSyncedChatIds((prev) => new Set(prev).add(chat.id));
        successCount++;
      } catch {
        failCount++;
      }
    }

    setSyncingChatId(null);
    setSyncingAll(false);

    if (failCount === 0) {
      toast.success(`Successfully synced ${successCount} chat(s)`);
    } else {
      toast.warning(`Synced ${successCount}, failed ${failCount} chat(s)`);
    }
  }

  if (!currentProject) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Group Chats</h1>
          <p className="text-muted-foreground">Sync Microsoft Teams group chats</p>
        </div>
        <Separator />
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <MessageSquare className="size-12 text-muted-foreground mb-4" />
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
        <h1 className="text-2xl font-bold tracking-tight">Group Chats</h1>
        <p className="text-muted-foreground">
          Sync Microsoft Teams group chats for{" "}
          <span className="font-medium text-foreground">{currentProject.name}</span>
        </p>
      </div>

      <Separator />

      {loadingSource ? (
        <div className="space-y-4">
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
          <MessageSquare className="size-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold">No Microsoft Teams data source</h3>
          <p className="text-muted-foreground mt-1">
            Please add a Microsoft Teams data source in the Data Sources tab first
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                  <Users className="size-4" />
                  Select Users
                  {users.length > 0 && (
                    <Badge variant="secondary">{users.length}</Badge>
                  )}
                </CardTitle>
                {users.length > 0 && (
                  <Button variant="outline" size="sm" onClick={toggleAllUsers}>
                    {selectedUserIds.size === users.length
                      ? "Deselect All"
                      : "Select All"}
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent>
              {loadingUsers ? (
                <div className="space-y-3">
                  {[1, 2, 3, 4, 5].map((i) => (
                    <div key={i} className="flex items-center gap-3">
                      <Skeleton className="size-4" />
                      <Skeleton className="h-4 w-48" />
                    </div>
                  ))}
                </div>
              ) : users.length === 0 ? (
                <p className="text-muted-foreground text-sm py-4 text-center">
                  No users found
                </p>
              ) : (
                <div className="space-y-1 max-h-64 overflow-y-auto rounded-md border p-2">
                  {users.map((user) => (
                    <label
                      key={user.id}
                      className="flex items-center gap-3 rounded-md px-3 py-2 hover:bg-accent/50 transition-colors cursor-pointer"
                    >
                      <Checkbox
                        checked={selectedUserIds.has(user.id)}
                        onCheckedChange={() => toggleUser(user.id)}
                      />
                      <div className="flex-1 min-w-0">
                        <span className="text-sm font-medium truncate block">
                          {user.displayName}
                        </span>
                        {user.mail && (
                          <span className="text-xs text-muted-foreground truncate block">
                            {user.mail}
                          </span>
                        )}
                      </div>
                    </label>
                  ))}
                </div>
              )}
              {users.length > 0 && (
                <div className="flex items-center justify-between mt-4">
                  <span className="text-sm text-muted-foreground">
                    {selectedUserIds.size} user(s) selected
                  </span>
                  <Button
                    onClick={loadGroupChats}
                    disabled={selectedUserIds.size === 0 || loadingChats}
                  >
                    {loadingChats ? (
                      <>
                        <Loader2 className="size-4 animate-spin" />
                        Loading Chats...
                      </>
                    ) : (
                      <>
                        <MessageSquare className="size-4" />
                        Load Group Chats
                      </>
                    )}
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>

          {(groupChats.length > 0 || loadingChats) && (
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="flex items-center gap-2">
                    <MessageSquare className="size-4" />
                    Group Chats
                    {groupChats.length > 0 && (
                      <Badge variant="secondary">{groupChats.length}</Badge>
                    )}
                  </CardTitle>
                  {groupChats.length > 0 && (
                    <Button variant="outline" size="sm" onClick={toggleAllChats}>
                      {selectedChatIds.size === groupChats.length
                        ? "Deselect All"
                        : "Select All"}
                    </Button>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                {loadingChats ? (
                  <div className="space-y-3">
                    {[1, 2, 3].map((i) => (
                      <Card key={i}>
                        <CardContent className="pt-4">
                          <div className="space-y-2">
                            <Skeleton className="h-4 w-48" />
                            <Skeleton className="h-3 w-32" />
                            <Skeleton className="h-3 w-64" />
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                ) : groupChats.length === 0 ? (
                  <p className="text-muted-foreground text-sm py-4 text-center">
                    No group chats found
                  </p>
                ) : (
                  <div className="space-y-2">
                    {groupChats.map((chat) => (
                      <div
                        key={chat.id}
                        className="flex items-start gap-3 rounded-md border px-4 py-3 hover:bg-accent/50 transition-colors"
                      >
                        <Checkbox
                          checked={selectedChatIds.has(chat.id)}
                          onCheckedChange={() => toggleChat(chat.id)}
                          disabled={syncingAll}
                          className="mt-0.5"
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <MessageSquare className="size-3.5 text-muted-foreground shrink-0" />
                            <span className="font-medium text-sm truncate">
                              {getChatDisplayName(chat)}
                            </span>
                            {syncedChatIds.has(chat.id) && (
                              <CheckCircle className="size-3.5 text-green-500 shrink-0" />
                            )}
                          </div>
                          <div className="flex items-center gap-3 mt-1 pl-5">
                            {chat.members && (
                              <Badge variant="outline" className="text-xs">
                                <Users className="size-3 mr-1" />
                                {chat.members.length} member(s)
                              </Badge>
                            )}
                          </div>
                          {chat.members && chat.members.length > 0 && (
                            <p className="text-xs text-muted-foreground mt-1 truncate pl-5">
                              {chat.members
                                .map((m) => m.displayName)
                                .filter(Boolean)
                                .join(", ")}
                            </p>
                          )}
                        </div>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={syncingChatId === chat.id || syncingAll}
                          onClick={() => syncChat(chat)}
                          className="shrink-0"
                        >
                          {syncingChatId === chat.id ? (
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

          {groupChats.length > 0 && (
            <div className="flex items-center justify-between">
              <div className="text-sm text-muted-foreground">
                {selectedChatIds.size} of {groupChats.length} chat(s) selected
                {syncingAll && (
                  <span className="ml-2">
                    — Syncing {syncProgress.current}/{syncProgress.total}
                  </span>
                )}
              </div>
              <Button
                onClick={syncAllSelected}
                disabled={selectedChatIds.size === 0 || syncingAll}
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
