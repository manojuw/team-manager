"use client";

import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { z } from "zod";

import { useProject } from "@/hooks/use-project";
import { connectors, dataSources, teams, devops, sync } from "@/lib/api";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Plug,
  Plus,
  Trash2,
  Settings,
  Hash,
  MessageSquare,
  RefreshCw,
  CheckCircle,
  Loader2,
  ChevronDown,
  ChevronRight,
  Users,
  XCircle,
  Database,
  GitBranch,
  FolderKanban,
} from "lucide-react";

const teamsConfigSchema = z.object({
  tenant_id: z.string().min(1, "Tenant ID is required"),
  client_id: z.string().min(1, "Client ID is required"),
  client_secret: z.string().min(1, "Client Secret is required"),
});
type TeamsConfigForm = z.infer<typeof teamsConfigSchema>;

const devopsConfigSchema = z.object({
  organization: z.string().min(1, "Organization name is required"),
  auth_type: z.enum(["pat", "azure_ad"]),
  pat: z.string().optional(),
  tenant_id: z.string().optional(),
  client_id: z.string().optional(),
  client_secret: z.string().optional(),
}).refine(
  (data) => {
    if (data.auth_type === "pat") return !!data.pat && data.pat.length > 0;
    return !!data.tenant_id && !!data.client_id && !!data.client_secret;
  },
  { message: "Please provide the required credentials for your chosen auth type", path: ["auth_type"] }
);
type DevOpsConfigForm = z.infer<typeof devopsConfigSchema>;

interface Connector {
  id: string;
  project_id: string;
  name: string;
  connector_type: string;
  config?: Record<string, string>;
  secrets_updated_at?: string;
  created_at?: string;
}

interface DataSourceItem {
  id: string;
  connector_id: string;
  name: string;
  source_type: string;
  config: Record<string, string>;
  sync_interval_minutes?: number;
  sync_enabled?: boolean;
  last_sync_at?: string;
}

interface Team {
  id: string;
  displayName: string;
}

interface Channel {
  id: string;
  displayName: string;
  description?: string;
}

interface UserItem {
  id: string;
  displayName: string;
  mail?: string;
}

interface GroupChat {
  id: string;
  topic?: string;
  members?: Array<{ displayName?: string; userId?: string }>;
  chat_type?: string;
}

interface DevOpsProject {
  id: string;
  name: string;
  description?: string;
  state?: string;
}

const CONNECTOR_TYPES = [
  { value: "microsoft_teams", label: "Microsoft Teams", icon: MessageSquare },
  { value: "azure_devops", label: "Azure DevOps", icon: GitBranch },
];

const SYNC_INTERVALS = [
  { label: "Off", value: "0" },
  { label: "15 minutes", value: "15" },
  { label: "30 minutes", value: "30" },
  { label: "1 hour", value: "60" },
  { label: "4 hours", value: "240" },
  { label: "12 hours", value: "720" },
  { label: "24 hours", value: "1440" },
];

export default function ConnectorsPage() {
  const { currentProject } = useProject();
  const [connectorList, setConnectorList] = useState<Connector[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [connectorType, setConnectorType] = useState("microsoft_teams");
  const [connectorName, setConnectorName] = useState("");
  const [expandedConnectorId, setExpandedConnectorId] = useState<string | null>(null);
  const [updateDialogId, setUpdateDialogId] = useState<string | null>(null);

  const addForm = useForm<TeamsConfigForm>({
    resolver: zodResolver(teamsConfigSchema),
    defaultValues: { tenant_id: "", client_id: "", client_secret: "" },
  });

  const addDevOpsForm = useForm<DevOpsConfigForm>({
    resolver: zodResolver(devopsConfigSchema),
    defaultValues: { organization: "", auth_type: "pat", pat: "", tenant_id: "", client_id: "", client_secret: "" },
  });

  const devopsAuthType = addDevOpsForm.watch("auth_type");

  const updateForm = useForm<TeamsConfigForm>({
    resolver: zodResolver(teamsConfigSchema),
    defaultValues: { tenant_id: "", client_id: "", client_secret: "" },
  });

  async function fetchConnectors() {
    if (!currentProject) { setLoading(false); return; }
    try {
      const data = await connectors.list(currentProject.id);
      setConnectorList(data);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load connectors");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    fetchConnectors();
  }, [currentProject?.id]);

  async function onAddConnector(values: TeamsConfigForm) {
    if (!currentProject) return;
    setCreating(true);
    try {
      await connectors.create({
        projectId: currentProject.id,
        name: connectorName || "Microsoft Teams Connector",
        connectorType: connectorType,
        config: {
          tenant_id: values.tenant_id,
          client_id: values.client_id,
          client_secret: values.client_secret,
        },
      });
      toast.success("Connector created");
      addForm.reset();
      setConnectorName("");
      setAddDialogOpen(false);
      await fetchConnectors();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to create connector");
    } finally {
      setCreating(false);
    }
  }

  async function onAddDevOpsConnector(values: DevOpsConfigForm) {
    if (!currentProject) return;
    setCreating(true);
    try {
      const config: Record<string, string> = {
        organization: values.organization,
        auth_type: values.auth_type,
      };
      if (values.auth_type === "pat") {
        config.pat = values.pat || "";
      } else {
        config.tenant_id = values.tenant_id || "";
        config.client_id = values.client_id || "";
        config.client_secret = values.client_secret || "";
      }
      await connectors.create({
        projectId: currentProject.id,
        name: connectorName || "Azure DevOps Connector",
        connectorType: "azure_devops",
        config,
      });
      toast.success("Connector created");
      addDevOpsForm.reset();
      setConnectorName("");
      setAddDialogOpen(false);
      await fetchConnectors();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to create connector");
    } finally {
      setCreating(false);
    }
  }

  async function onUpdateCredentials(id: string, values: TeamsConfigForm) {
    try {
      await connectors.update(id, {
        config: {
          tenant_id: values.tenant_id,
          client_id: values.client_id,
          client_secret: values.client_secret,
        },
      });
      toast.success("Credentials updated");
      setUpdateDialogId(null);
      updateForm.reset();
      await fetchConnectors();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to update credentials");
    }
  }

  async function onRemoveConnector(id: string) {
    try {
      await connectors.delete(id);
      toast.success("Connector removed");
      await fetchConnectors();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to remove connector");
    }
  }

  function getConnectorTypeLabel(type: string) {
    const found = CONNECTOR_TYPES.find((t) => t.value === type);
    return found ? found.label : type;
  }

  if (!currentProject) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Connectors</h1>
          <p className="text-muted-foreground">Connect external data sources to your project</p>
        </div>
        <Separator />
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Plug className="size-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold">No project selected</h3>
          <p className="text-muted-foreground mt-1">Please select a project first from the Projects page</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Connectors</h1>
          <p className="text-muted-foreground">
            Connect external services to <span className="font-medium text-foreground">{currentProject.name}</span>
          </p>
        </div>
        <Dialog open={addDialogOpen} onOpenChange={setAddDialogOpen}>
          <DialogTrigger asChild>
            <Button><Plus className="size-4" /> Add Connector</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add Connector</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div className="space-y-2">
                <Label>Connector Type</Label>
                <Select value={connectorType} onValueChange={(val) => { setConnectorType(val); addForm.reset(); addDevOpsForm.reset(); }}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {CONNECTOR_TYPES.map((t) => (
                      <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="connector-name">Name</Label>
                <Input
                  id="connector-name"
                  placeholder={connectorType === "azure_devops" ? "e.g. My DevOps Org" : "e.g. Production Teams"}
                  value={connectorName}
                  onChange={(e) => setConnectorName(e.target.value)}
                />
              </div>
              <Separator />
              {connectorType === "microsoft_teams" && (
                <form onSubmit={addForm.handleSubmit(onAddConnector)} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="add-tenant-id">Azure Tenant ID</Label>
                    <Input id="add-tenant-id" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" {...addForm.register("tenant_id")} />
                    {addForm.formState.errors.tenant_id && <p className="text-sm text-destructive">{addForm.formState.errors.tenant_id.message}</p>}
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="add-client-id">Client ID</Label>
                    <Input id="add-client-id" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" {...addForm.register("client_id")} />
                    {addForm.formState.errors.client_id && <p className="text-sm text-destructive">{addForm.formState.errors.client_id.message}</p>}
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="add-client-secret">Client Secret</Label>
                    <Input id="add-client-secret" type="password" placeholder="Enter client secret" {...addForm.register("client_secret")} />
                    {addForm.formState.errors.client_secret && <p className="text-sm text-destructive">{addForm.formState.errors.client_secret.message}</p>}
                  </div>
                  <DialogFooter>
                    <Button type="submit" disabled={creating}>{creating ? "Creating..." : "Create Connector"}</Button>
                  </DialogFooter>
                </form>
              )}
              {connectorType === "azure_devops" && (
                <form onSubmit={addDevOpsForm.handleSubmit(onAddDevOpsConnector)} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="add-org">Organization</Label>
                    <Input id="add-org" placeholder="my-organization" {...addDevOpsForm.register("organization")} />
                    {addDevOpsForm.formState.errors.organization && <p className="text-sm text-destructive">{addDevOpsForm.formState.errors.organization.message}</p>}
                  </div>
                  <div className="space-y-2">
                    <Label>Authentication Type</Label>
                    <Select value={devopsAuthType} onValueChange={(val: "pat" | "azure_ad") => addDevOpsForm.setValue("auth_type", val)}>
                      <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="pat">Personal Access Token (PAT)</SelectItem>
                        <SelectItem value="azure_ad">Azure AD (Service Principal)</SelectItem>
                      </SelectContent>
                    </Select>
                    {addDevOpsForm.formState.errors.auth_type && <p className="text-sm text-destructive">{addDevOpsForm.formState.errors.auth_type.message}</p>}
                  </div>
                  {devopsAuthType === "pat" && (
                    <div className="space-y-2">
                      <Label htmlFor="add-pat">Personal Access Token</Label>
                      <Input id="add-pat" type="password" placeholder="Enter your PAT" {...addDevOpsForm.register("pat")} />
                    </div>
                  )}
                  {devopsAuthType === "azure_ad" && (
                    <>
                      <div className="space-y-2">
                        <Label htmlFor="add-devops-tenant-id">Azure Tenant ID</Label>
                        <Input id="add-devops-tenant-id" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" {...addDevOpsForm.register("tenant_id")} />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="add-devops-client-id">Client ID</Label>
                        <Input id="add-devops-client-id" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" {...addDevOpsForm.register("client_id")} />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="add-devops-client-secret">Client Secret</Label>
                        <Input id="add-devops-client-secret" type="password" placeholder="Enter client secret" {...addDevOpsForm.register("client_secret")} />
                      </div>
                    </>
                  )}
                  <DialogFooter>
                    <Button type="submit" disabled={creating}>{creating ? "Creating..." : "Create Connector"}</Button>
                  </DialogFooter>
                </form>
              )}
            </div>
          </DialogContent>
        </Dialog>
      </div>

      <Separator />

      {loading ? (
        <div className="space-y-4">
          {[1, 2].map((i) => (
            <Card key={i}>
              <CardHeader><Skeleton className="h-5 w-40" /><Skeleton className="h-4 w-56" /></CardHeader>
              <CardContent><Skeleton className="h-4 w-32" /></CardContent>
            </Card>
          ))}
        </div>
      ) : connectorList.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Plug className="size-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold">No connectors</h3>
          <p className="text-muted-foreground mt-1">Add a connector to start syncing data</p>
        </div>
      ) : (
        <div className="space-y-4">
          {connectorList.map((connector) => (
            <ConnectorCard
              key={connector.id}
              connector={connector}
              expanded={expandedConnectorId === connector.id}
              onToggleExpand={() => setExpandedConnectorId(expandedConnectorId === connector.id ? null : connector.id)}
              onRemove={() => {
                if (confirm("Remove this connector and all its data sources? This cannot be undone.")) {
                  onRemoveConnector(connector.id);
                }
              }}
              onUpdateCredentials={() => {
                setUpdateDialogId(connector.id);
                updateForm.reset({
                  tenant_id: connector.config?.tenant_id ?? "",
                  client_id: connector.config?.client_id ?? "",
                  client_secret: "",
                });
              }}
              getConnectorTypeLabel={getConnectorTypeLabel}
              currentProject={currentProject}
            />
          ))}
        </div>
      )}

      <Dialog open={!!updateDialogId} onOpenChange={(open) => { if (!open) setUpdateDialogId(null); }}>
        <DialogContent>
          <DialogHeader><DialogTitle>Update Credentials</DialogTitle></DialogHeader>
          <form onSubmit={updateForm.handleSubmit((values) => onUpdateCredentials(updateDialogId!, values))} className="space-y-4">
            <div className="space-y-2">
              <Label>Azure Tenant ID</Label>
              <Input placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" {...updateForm.register("tenant_id")} />
              {updateForm.formState.errors.tenant_id && <p className="text-sm text-destructive">{updateForm.formState.errors.tenant_id.message}</p>}
            </div>
            <div className="space-y-2">
              <Label>Client ID</Label>
              <Input placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" {...updateForm.register("client_id")} />
              {updateForm.formState.errors.client_id && <p className="text-sm text-destructive">{updateForm.formState.errors.client_id.message}</p>}
            </div>
            <div className="space-y-2">
              <Label>Client Secret</Label>
              <Input type="password" placeholder="Enter new client secret" {...updateForm.register("client_secret")} />
              {updateForm.formState.errors.client_secret && <p className="text-sm text-destructive">{updateForm.formState.errors.client_secret.message}</p>}
            </div>
            <DialogFooter><Button type="submit">Update</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function ConnectorCard({
  connector,
  expanded,
  onToggleExpand,
  onRemove,
  onUpdateCredentials,
  getConnectorTypeLabel,
  currentProject,
}: {
  connector: Connector;
  expanded: boolean;
  onToggleExpand: () => void;
  onRemove: () => void;
  onUpdateCredentials: () => void;
  getConnectorTypeLabel: (type: string) => string;
  currentProject: { id: string; name: string };
}) {
  const [sourceList, setSourceList] = useState<DataSourceItem[]>([]);
  const [loadingSources, setLoadingSources] = useState(false);
  const [addSourceType, setAddSourceType] = useState<string | null>(null);
  const [syncingSourceId, setSyncingSourceId] = useState<string | null>(null);

  useEffect(() => {
    if (expanded) {
      fetchSources();
    }
  }, [expanded]);

  async function fetchSources() {
    setLoadingSources(true);
    try {
      const data = await dataSources.listByConnector(connector.id);
      setSourceList(data);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load data sources");
    } finally {
      setLoadingSources(false);
    }
  }

  async function syncNow(source: DataSourceItem) {
    setSyncingSourceId(source.id);
    try {
      let result;
      if (source.source_type === "team_channel") {
        result = await teams.syncChannel({
          project_id: currentProject.id,
          connector_id: connector.id,
          data_source_id: source.id,
          team_id: source.config.team_id,
          team_name: source.config.team_name,
          channel_id: source.config.channel_id,
          channel_name: source.config.channel_name,
        });
      } else if (source.source_type === "group_chat") {
        result = await teams.syncGroupChat({
          project_id: currentProject.id,
          connector_id: connector.id,
          data_source_id: source.id,
          chat_id: source.config.chat_id,
          chat_name: source.config.chat_name,
        });
      } else if (source.source_type === "devops_project") {
        result = await devops.syncProject({
          project_id: currentProject.id,
          connector_id: connector.id,
          data_source_id: source.id,
          devops_project_id: source.config.devops_project_id,
          devops_project_name: source.config.devops_project_name,
        });
      }
      const added = result?.added ?? 0;
      const fetched = result?.total_fetched ?? 0;
      toast.success(`Sync complete: ${added} new items added (${fetched} fetched)`);
      await fetchSources();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Sync failed");
    } finally {
      setSyncingSourceId(null);
    }
  }

  async function removeSource(id: string) {
    try {
      await dataSources.delete(id);
      toast.success("Data source removed");
      await fetchSources();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to remove data source");
    }
  }

  async function toggleSync(id: string, enabled: boolean) {
    try {
      await dataSources.update(id, { syncEnabled: enabled });
      toast.success(enabled ? "Sync enabled" : "Sync disabled");
      await fetchSources();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to toggle sync");
    }
  }

  async function updateSyncInterval(id: string, minutes: number) {
    try {
      await dataSources.update(id, { syncIntervalMinutes: minutes });
      toast.success("Sync interval updated");
      await fetchSources();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to update interval");
    }
  }

  return (
    <Card>
      <CardHeader className="cursor-pointer" onClick={onToggleExpand}>
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            {expanded ? <ChevronDown className="size-4 mt-0.5" /> : <ChevronRight className="size-4 mt-0.5" />}
            <div className="space-y-1">
              <CardTitle className="flex items-center gap-2">
                <Plug className="size-4" />
                {connector.name || getConnectorTypeLabel(connector.connector_type)}
              </CardTitle>
              <CardDescription>
                {getConnectorTypeLabel(connector.connector_type)}
                {connector.secrets_updated_at && (
                  <span className="ml-2 text-xs">
                    Credentials updated {new Date(connector.secrets_updated_at).toLocaleDateString()}
                  </span>
                )}
              </CardDescription>
            </div>
          </div>
          <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
            <Badge variant="outline">{sourceList.length} data source(s)</Badge>
            <Button variant="outline" size="sm" onClick={onUpdateCredentials}>
              <Settings className="size-3" /> Credentials
            </Button>
            <Button variant="destructive" size="sm" onClick={onRemove}>
              <Trash2 className="size-3" />
            </Button>
          </div>
        </div>
      </CardHeader>

      {expanded && (
        <CardContent className="border-t pt-4">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">Data Sources</h3>
              {connector.connector_type === "microsoft_teams" && (
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => setAddSourceType("team_channel")}>
                    <Hash className="size-3" /> Add Channels
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setAddSourceType("group_chat")}>
                    <MessageSquare className="size-3" /> Add Group Chats
                  </Button>
                </div>
              )}
              {connector.connector_type === "azure_devops" && (
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => setAddSourceType("devops_project")}>
                    <FolderKanban className="size-3" /> Add DevOps Project
                  </Button>
                </div>
              )}
            </div>

            {loadingSources ? (
              <div className="space-y-2">
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
              </div>
            ) : sourceList.length === 0 && !addSourceType ? (
              <div className="text-center py-8 text-muted-foreground">
                <Database className="size-8 mx-auto mb-2 opacity-50" />
                <p className="text-sm">No data sources added yet</p>
                <p className="text-xs mt-1">
                  {connector.connector_type === "azure_devops"
                    ? "Add DevOps projects to start syncing work items"
                    : "Add channels or group chats to start syncing"}
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {sourceList.map((source) => (
                  <div key={source.id} className="flex items-center gap-3 rounded-md border px-4 py-3">
                    {source.source_type === "team_channel" ? (
                      <Hash className="size-4 text-muted-foreground shrink-0" />
                    ) : source.source_type === "devops_project" ? (
                      <FolderKanban className="size-4 text-muted-foreground shrink-0" />
                    ) : (
                      <MessageSquare className="size-4 text-muted-foreground shrink-0" />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-sm truncate">{source.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {source.source_type === "team_channel" ? "Channel" : source.source_type === "devops_project" ? "DevOps Project" : "Group Chat"}
                        <span className="ml-2">
                          {source.last_sync_at
                            ? `Last synced: ${new Date(source.last_sync_at).toLocaleString()}`
                            : "Never synced"}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-8 text-xs"
                        disabled={syncingSourceId === source.id}
                        onClick={() => syncNow(source)}
                      >
                        {syncingSourceId === source.id ? (
                          <><Loader2 className="size-3 animate-spin" /> Syncing…</>
                        ) : (
                          <><RefreshCw className="size-3" /> Sync Now</>
                        )}
                      </Button>
                      <Select
                        value={String(source.sync_interval_minutes ?? 0)}
                        onValueChange={(val) => updateSyncInterval(source.id, parseInt(val))}
                      >
                        <SelectTrigger className="w-[120px] h-8 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {SYNC_INTERVALS.map((interval) => (
                            <SelectItem key={interval.value} value={interval.value}>{interval.label}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Button
                        variant={source.sync_enabled ? "secondary" : "outline"}
                        size="sm"
                        className="h-8 text-xs"
                        onClick={() => toggleSync(source.id, !source.sync_enabled)}
                      >
                        {source.sync_enabled ? (
                          <><CheckCircle className="size-3" /> On</>
                        ) : (
                          <><XCircle className="size-3" /> Off</>
                        )}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-8 text-destructive hover:text-destructive"
                        onClick={() => {
                          if (confirm(`Remove "${source.name}"?`)) removeSource(source.id);
                        }}
                      >
                        <Trash2 className="size-3" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {addSourceType === "team_channel" && (
              <AddChannelSources
                connectorId={connector.id}
                projectId={currentProject.id}
                onClose={() => setAddSourceType(null)}
                onAdded={fetchSources}
              />
            )}
            {addSourceType === "group_chat" && (
              <AddGroupChatSources
                connectorId={connector.id}
                projectId={currentProject.id}
                onClose={() => setAddSourceType(null)}
                onAdded={fetchSources}
              />
            )}
            {addSourceType === "devops_project" && (
              <AddDevOpsProjectSources
                connectorId={connector.id}
                projectId={currentProject.id}
                onClose={() => setAddSourceType(null)}
                onAdded={fetchSources}
              />
            )}
          </div>
        </CardContent>
      )}
    </Card>
  );
}

function AddChannelSources({
  connectorId,
  projectId,
  onClose,
  onAdded,
}: {
  connectorId: string;
  projectId: string;
  onClose: () => void;
  onAdded: () => void;
}) {
  const [teamsList, setTeamsList] = useState<Team[]>([]);
  const [loadingTeams, setLoadingTeams] = useState(true);
  const [selectedTeamId, setSelectedTeamId] = useState("");
  const [selectedTeamName, setSelectedTeamName] = useState("");
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loadingChannels, setLoadingChannels] = useState(false);
  const [selectedChannelIds, setSelectedChannelIds] = useState<Set<string>>(new Set());
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    async function fetchTeams() {
      try {
        const data = await teams.listTeams(connectorId);
        setTeamsList(data.teams || []);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Failed to load teams");
      } finally {
        setLoadingTeams(false);
      }
    }
    fetchTeams();
  }, [connectorId]);

  useEffect(() => {
    if (!selectedTeamId) return;
    setLoadingChannels(true);
    setChannels([]);
    setSelectedChannelIds(new Set());
    async function fetchChannels() {
      try {
        const data = await teams.listChannels(connectorId, selectedTeamId);
        setChannels(data.channels || []);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Failed to load channels");
      } finally {
        setLoadingChannels(false);
      }
    }
    fetchChannels();
  }, [connectorId, selectedTeamId]);

  function toggleChannel(id: string) {
    setSelectedChannelIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  async function addSelected() {
    const selected = channels.filter((c) => selectedChannelIds.has(c.id));
    if (selected.length === 0) return;
    setAdding(true);
    let added = 0;
    for (const channel of selected) {
      try {
        await dataSources.create({
          connectorId,
          name: `${selectedTeamName} / ${channel.displayName}`,
          sourceType: "team_channel",
          config: {
            team_id: selectedTeamId,
            team_name: selectedTeamName,
            channel_id: channel.id,
            channel_name: channel.displayName,
          },
        });
        added++;
      } catch (error) {
        toast.error(`Failed to add ${channel.displayName}`);
      }
    }
    if (added > 0) {
      toast.success(`Added ${added} channel(s)`);
      onAdded();
    }
    setAdding(false);
    onClose();
  }

  return (
    <Card className="border-dashed">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-2">
            <Hash className="size-4" /> Add Channels
          </CardTitle>
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {loadingTeams ? (
          <Skeleton className="h-10 w-full" />
        ) : (
          <Select
            value={selectedTeamId}
            onValueChange={(val) => {
              setSelectedTeamId(val);
              const team = teamsList.find((t) => t.id === val);
              setSelectedTeamName(team?.displayName || "");
            }}
          >
            <SelectTrigger><SelectValue placeholder="Select a team..." /></SelectTrigger>
            <SelectContent>
              {teamsList.map((t) => (
                <SelectItem key={t.id} value={t.id}>{t.displayName}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        {selectedTeamId && (
          <>
            {loadingChannels ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => <Skeleton key={i} className="h-8 w-full" />)}
              </div>
            ) : (
              <div className="space-y-1 max-h-48 overflow-y-auto rounded-md border p-2">
                {channels.map((channel) => (
                  <label key={channel.id} className="flex items-center gap-3 px-3 py-2 rounded-md hover:bg-accent/50 cursor-pointer">
                    <Checkbox
                      checked={selectedChannelIds.has(channel.id)}
                      onCheckedChange={() => toggleChannel(channel.id)}
                    />
                    <Hash className="size-3 text-muted-foreground" />
                    <span className="text-sm">{channel.displayName}</span>
                  </label>
                ))}
              </div>
            )}
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">{selectedChannelIds.size} selected</span>
              <Button size="sm" disabled={selectedChannelIds.size === 0 || adding} onClick={addSelected}>
                {adding ? <><Loader2 className="size-3 animate-spin" /> Adding...</> : <><Plus className="size-3" /> Add Selected</>}
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function AddGroupChatSources({
  connectorId,
  projectId,
  onClose,
  onAdded,
}: {
  connectorId: string;
  projectId: string;
  onClose: () => void;
  onAdded: () => void;
}) {
  const [users, setUsers] = useState<UserItem[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [selectedUserIds, setSelectedUserIds] = useState<Set<string>>(new Set());
  const [groupChats, setGroupChats] = useState<GroupChat[]>([]);
  const [loadingChats, setLoadingChats] = useState(false);
  const [selectedChatIds, setSelectedChatIds] = useState<Set<string>>(new Set());
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    async function fetchUsers() {
      try {
        const data = await teams.listUsers(connectorId);
        setUsers(data.users || []);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Failed to load users");
      } finally {
        setLoadingUsers(false);
      }
    }
    fetchUsers();
  }, [connectorId]);

  function toggleUser(id: string) {
    setSelectedUserIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  async function loadChats() {
    if (selectedUserIds.size === 0) return;
    setLoadingChats(true);
    setGroupChats([]);
    setSelectedChatIds(new Set());
    try {
      const data = await teams.listGroupChats(connectorId, Array.from(selectedUserIds));
      setGroupChats(data.chats || []);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load group chats");
    } finally {
      setLoadingChats(false);
    }
  }

  function getChatName(chat: GroupChat) {
    if (chat.topic) return chat.topic;
    if (chat.members && chat.members.length > 0) {
      return chat.members.map((m) => m.displayName).filter(Boolean).slice(0, 3).join(", ") +
        (chat.members.length > 3 ? "..." : "");
    }
    return "Unnamed Chat";
  }

  function toggleChat(id: string) {
    setSelectedChatIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  async function addSelected() {
    const selected = groupChats.filter((c) => selectedChatIds.has(c.id));
    if (selected.length === 0) return;
    setAdding(true);
    let added = 0;
    for (const chat of selected) {
      try {
        await dataSources.create({
          connectorId,
          name: getChatName(chat),
          sourceType: "group_chat",
          config: {
            chat_id: chat.id,
            chat_name: getChatName(chat),
          },
        });
        added++;
      } catch (error) {
        toast.error(`Failed to add ${getChatName(chat)}`);
      }
    }
    if (added > 0) {
      toast.success(`Added ${added} group chat(s)`);
      onAdded();
    }
    setAdding(false);
    onClose();
  }

  return (
    <Card className="border-dashed">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-2">
            <MessageSquare className="size-4" /> Add Group Chats
          </CardTitle>
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {loadingUsers ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => <Skeleton key={i} className="h-8 w-full" />)}
          </div>
        ) : (
          <>
            <div className="space-y-1 max-h-40 overflow-y-auto rounded-md border p-2">
              {users.map((user) => (
                <label key={user.id} className="flex items-center gap-3 px-3 py-2 rounded-md hover:bg-accent/50 cursor-pointer">
                  <Checkbox checked={selectedUserIds.has(user.id)} onCheckedChange={() => toggleUser(user.id)} />
                  <div className="min-w-0">
                    <span className="text-sm font-medium block truncate">{user.displayName}</span>
                    {user.mail && <span className="text-xs text-muted-foreground block truncate">{user.mail}</span>}
                  </div>
                </label>
              ))}
            </div>
            <Button size="sm" variant="outline" disabled={selectedUserIds.size === 0 || loadingChats} onClick={loadChats}>
              {loadingChats ? <><Loader2 className="size-3 animate-spin" /> Loading...</> : <><Users className="size-3" /> Load Group Chats</>}
            </Button>
          </>
        )}

        {groupChats.length > 0 && (
          <>
            <Separator />
            <div className="space-y-1 max-h-48 overflow-y-auto rounded-md border p-2">
              {groupChats.map((chat) => (
                <label key={chat.id} className="flex items-center gap-3 px-3 py-2 rounded-md hover:bg-accent/50 cursor-pointer">
                  <Checkbox checked={selectedChatIds.has(chat.id)} onCheckedChange={() => toggleChat(chat.id)} />
                  <MessageSquare className="size-3 text-muted-foreground shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm block truncate">{getChatName(chat)}</span>
                      <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium border shrink-0 ${
                        chat.chat_type === "meeting"
                          ? "bg-blue-100 text-blue-700 border-blue-200"
                          : "bg-gray-100 text-gray-600 border-gray-200"
                      }`}>
                        {chat.chat_type === "meeting" ? "Meeting" : "Group"}
                      </span>
                    </div>
                    {chat.members && (
                      <span className="text-xs text-muted-foreground block truncate">
                        {chat.members.length} member(s)
                      </span>
                    )}
                  </div>
                </label>
              ))}
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">{selectedChatIds.size} selected</span>
              <Button size="sm" disabled={selectedChatIds.size === 0 || adding} onClick={addSelected}>
                {adding ? <><Loader2 className="size-3 animate-spin" /> Adding...</> : <><Plus className="size-3" /> Add Selected</>}
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function AddDevOpsProjectSources({
  connectorId,
  projectId,
  onClose,
  onAdded,
}: {
  connectorId: string;
  projectId: string;
  onClose: () => void;
  onAdded: () => void;
}) {
  const [projectsList, setProjectsList] = useState<DevOpsProject[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [selectedProjectIds, setSelectedProjectIds] = useState<Set<string>>(new Set());
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    async function fetchProjects() {
      try {
        const data = await devops.listProjects(connectorId);
        setProjectsList(data.projects || []);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Failed to load DevOps projects");
      } finally {
        setLoadingProjects(false);
      }
    }
    fetchProjects();
  }, [connectorId]);

  function toggleProject(id: string) {
    setSelectedProjectIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  async function addSelected() {
    const selected = projectsList.filter((p) => selectedProjectIds.has(p.id));
    if (selected.length === 0) return;
    setAdding(true);
    let added = 0;
    for (const project of selected) {
      try {
        await dataSources.create({
          connectorId,
          name: project.name,
          sourceType: "devops_project",
          config: {
            devops_project_id: project.id,
            devops_project_name: project.name,
          },
        });
        added++;
      } catch (error) {
        toast.error(`Failed to add ${project.name}`);
      }
    }
    if (added > 0) {
      toast.success(`Added ${added} DevOps project(s)`);
      onAdded();
    }
    setAdding(false);
    onClose();
  }

  return (
    <Card className="border-dashed">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-2">
            <FolderKanban className="size-4" /> Add DevOps Projects
          </CardTitle>
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {loadingProjects ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => <Skeleton key={i} className="h-8 w-full" />)}
          </div>
        ) : projectsList.length === 0 ? (
          <div className="text-center py-4 text-muted-foreground">
            <p className="text-sm">No projects found in this organization</p>
          </div>
        ) : (
          <>
            <div className="space-y-1 max-h-48 overflow-y-auto rounded-md border p-2">
              {projectsList.map((project) => (
                <label key={project.id} className="flex items-center gap-3 px-3 py-2 rounded-md hover:bg-accent/50 cursor-pointer">
                  <Checkbox
                    checked={selectedProjectIds.has(project.id)}
                    onCheckedChange={() => toggleProject(project.id)}
                  />
                  <FolderKanban className="size-3 text-muted-foreground" />
                  <div className="min-w-0">
                    <span className="text-sm font-medium block truncate">{project.name}</span>
                    {project.description && (
                      <span className="text-xs text-muted-foreground block truncate">{project.description}</span>
                    )}
                  </div>
                </label>
              ))}
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">{selectedProjectIds.size} selected</span>
              <Button size="sm" disabled={selectedProjectIds.size === 0 || adding} onClick={addSelected}>
                {adding ? <><Loader2 className="size-3 animate-spin" /> Adding...</> : <><Plus className="size-3" /> Add Selected</>}
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
