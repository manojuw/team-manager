"use client";

import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import { useProject } from "@/hooks/use-project";
import { dataSources } from "@/lib/api";
import { teamsCredentialsSchema, type TeamsCredentialsForm } from "@/lib/schemas";

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
import { Database, Plus, Trash2, CheckCircle, XCircle, Settings } from "lucide-react";

interface DataSource {
  id: string;
  project_id: string;
  source_type: string;
  config?: {
    tenant_id?: string;
    client_id?: string;
    client_secret?: string;
  };
  sync_interval_minutes?: number;
  sync_enabled?: boolean;
  created_at?: string;
}

const SYNC_INTERVALS = [
  { label: "Off", value: "0" },
  { label: "15 minutes", value: "15" },
  { label: "30 minutes", value: "30" },
  { label: "1 hour", value: "60" },
  { label: "4 hours", value: "240" },
  { label: "12 hours", value: "720" },
  { label: "24 hours", value: "1440" },
];

export default function DataSourcesPage() {
  const { currentProject } = useProject();
  const [sourceList, setSourceList] = useState<DataSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [updateDialogId, setUpdateDialogId] = useState<string | null>(null);
  const [sourceType, setSourceType] = useState("microsoft_teams");

  const addForm = useForm<TeamsCredentialsForm>({
    resolver: zodResolver(teamsCredentialsSchema),
    defaultValues: {
      tenant_id: "",
      client_id: "",
      client_secret: "",
    },
  });

  const updateForm = useForm<TeamsCredentialsForm>({
    resolver: zodResolver(teamsCredentialsSchema),
    defaultValues: {
      tenant_id: "",
      client_id: "",
      client_secret: "",
    },
  });

  async function fetchDataSources() {
    if (!currentProject) {
      setLoading(false);
      return;
    }
    try {
      const data = await dataSources.list(currentProject.id);
      setSourceList(data);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load data sources");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    fetchDataSources();
  }, [currentProject?.id]);

  async function onAddDataSource(values: TeamsCredentialsForm) {
    if (!currentProject) return;
    setCreating(true);
    try {
      await dataSources.create({
        projectId: currentProject.id,
        sourceType: sourceType,
        config: {
          tenant_id: values.tenant_id,
          client_id: values.client_id,
          client_secret: values.client_secret,
        },
        syncIntervalMinutes: 0,
        syncEnabled: false,
      });
      toast.success("Data source added");
      addForm.reset();
      setAddDialogOpen(false);
      await fetchDataSources();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to add data source");
    } finally {
      setCreating(false);
    }
  }

  async function onUpdateCredentials(id: string, values: TeamsCredentialsForm) {
    try {
      await dataSources.update(id, {
        config: {
          tenant_id: values.tenant_id,
          client_id: values.client_id,
          client_secret: values.client_secret,
        },
      });
      toast.success("Credentials updated");
      setUpdateDialogId(null);
      updateForm.reset();
      await fetchDataSources();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to update credentials");
    }
  }

  async function onRemoveSource(id: string) {
    try {
      await dataSources.delete(id);
      toast.success("Data source removed");
      await fetchDataSources();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to remove data source");
    }
  }

  async function onUpdateSyncInterval(id: string, minutes: number) {
    try {
      await dataSources.update(id, { syncIntervalMinutes: minutes });
      toast.success("Sync interval updated");
      await fetchDataSources();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to update sync interval");
    }
  }

  async function onToggleSync(id: string, enabled: boolean) {
    try {
      await dataSources.update(id, { syncEnabled: enabled });
      toast.success(enabled ? "Sync enabled" : "Sync disabled");
      await fetchDataSources();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to toggle sync");
    }
  }

  function maskSecret(value?: string) {
    if (!value) return "—";
    if (value.length <= 8) return "••••••••";
    return value.substring(0, 4) + "••••" + value.substring(value.length - 4);
  }

  if (!currentProject) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Data Sources</h1>
          <p className="text-muted-foreground">
            Connect external data sources to your project
          </p>
        </div>
        <Separator />
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Database className="size-12 text-muted-foreground mb-4" />
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
          <h1 className="text-2xl font-bold tracking-tight">Data Sources</h1>
          <p className="text-muted-foreground">
            Connect external data sources to <span className="font-medium text-foreground">{currentProject.name}</span>
          </p>
        </div>
        <Dialog open={addDialogOpen} onOpenChange={setAddDialogOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="size-4" />
              Add Data Source
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add Data Source</DialogTitle>
            </DialogHeader>
            <form onSubmit={addForm.handleSubmit(onAddDataSource)} className="space-y-4">
              <div className="space-y-2">
                <Label>Source Type</Label>
                <Select value={sourceType} onValueChange={setSourceType}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="microsoft_teams">Microsoft Teams</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Separator />
              <div className="space-y-2">
                <Label htmlFor="add-tenant-id">Tenant ID</Label>
                <Input
                  id="add-tenant-id"
                  placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                  {...addForm.register("tenant_id")}
                />
                {addForm.formState.errors.tenant_id && (
                  <p className="text-sm text-destructive">
                    {addForm.formState.errors.tenant_id.message}
                  </p>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="add-client-id">Client ID</Label>
                <Input
                  id="add-client-id"
                  placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                  {...addForm.register("client_id")}
                />
                {addForm.formState.errors.client_id && (
                  <p className="text-sm text-destructive">
                    {addForm.formState.errors.client_id.message}
                  </p>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="add-client-secret">Client Secret</Label>
                <Input
                  id="add-client-secret"
                  type="password"
                  placeholder="••••••••"
                  {...addForm.register("client_secret")}
                />
                {addForm.formState.errors.client_secret && (
                  <p className="text-sm text-destructive">
                    {addForm.formState.errors.client_secret.message}
                  </p>
                )}
              </div>
              <DialogFooter>
                <Button type="submit" disabled={creating}>
                  {creating ? "Adding…" : "Add Data Source"}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <Separator />

      {loading ? (
        <div className="space-y-4">
          {[1, 2].map((i) => (
            <Card key={i}>
              <CardHeader>
                <Skeleton className="h-5 w-40" />
                <Skeleton className="h-4 w-56" />
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-4 w-24" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : sourceList.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Database className="size-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold">No data sources</h3>
          <p className="text-muted-foreground mt-1">
            Add a data source to start syncing data
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {sourceList.map((source) => (
            <Card key={source.id}>
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="space-y-1">
                    <CardTitle className="flex items-center gap-2">
                      <Database className="size-4" />
                      {source.source_type === "microsoft_teams"
                        ? "Microsoft Teams"
                        : source.source_type}
                    </CardTitle>
                    <CardDescription className="flex items-center gap-2">
                      {source.config?.tenant_id ? (
                        <>
                          Tenant: {maskSecret(source.config.tenant_id)}
                        </>
                      ) : (
                        "No credentials configured"
                      )}
                    </CardDescription>
                  </div>
                  <div className="flex items-center gap-2">
                    {source.sync_enabled ? (
                      <Badge variant="default" className="gap-1">
                        <CheckCircle className="size-3" />
                        Sync On
                      </Badge>
                    ) : (
                      <Badge variant="secondary" className="gap-1">
                        <XCircle className="size-3" />
                        Sync Off
                      </Badge>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center gap-4">
                    <div className="flex items-center gap-2">
                      <Label className="text-muted-foreground">Sync Interval:</Label>
                      <Select
                        value={String(source.sync_interval_minutes ?? 0)}
                        onValueChange={(val) =>
                          onUpdateSyncInterval(source.id, parseInt(val))
                        }
                      >
                        <SelectTrigger className="w-[140px]">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {SYNC_INTERVALS.map((interval) => (
                            <SelectItem key={interval.value} value={interval.value}>
                              {interval.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <Button
                      variant={source.sync_enabled ? "secondary" : "default"}
                      size="sm"
                      onClick={() =>
                        onToggleSync(source.id, !source.sync_enabled)
                      }
                    >
                      {source.sync_enabled ? "Disable Sync" : "Enable Sync"}
                    </Button>
                  </div>

                  <Separator />

                  <div className="flex items-center gap-2">
                    <Dialog
                      open={updateDialogId === source.id}
                      onOpenChange={(open) => {
                        setUpdateDialogId(open ? source.id : null);
                        if (open) {
                          updateForm.reset({
                            tenant_id: source.config?.tenant_id ?? "",
                            client_id: source.config?.client_id ?? "",
                            client_secret: "",
                          });
                        }
                      }}
                    >
                      <DialogTrigger asChild>
                        <Button variant="outline" size="sm">
                          <Settings className="size-3" />
                          Update Credentials
                        </Button>
                      </DialogTrigger>
                      <DialogContent>
                        <DialogHeader>
                          <DialogTitle>Update Credentials</DialogTitle>
                        </DialogHeader>
                        <form
                          onSubmit={updateForm.handleSubmit((values) =>
                            onUpdateCredentials(source.id, values)
                          )}
                          className="space-y-4"
                        >
                          <div className="space-y-2">
                            <Label htmlFor="update-tenant-id">Tenant ID</Label>
                            <Input
                              id="update-tenant-id"
                              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                              {...updateForm.register("tenant_id")}
                            />
                            {updateForm.formState.errors.tenant_id && (
                              <p className="text-sm text-destructive">
                                {updateForm.formState.errors.tenant_id.message}
                              </p>
                            )}
                          </div>
                          <div className="space-y-2">
                            <Label htmlFor="update-client-id">Client ID</Label>
                            <Input
                              id="update-client-id"
                              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                              {...updateForm.register("client_id")}
                            />
                            {updateForm.formState.errors.client_id && (
                              <p className="text-sm text-destructive">
                                {updateForm.formState.errors.client_id.message}
                              </p>
                            )}
                          </div>
                          <div className="space-y-2">
                            <Label htmlFor="update-client-secret">Client Secret</Label>
                            <Input
                              id="update-client-secret"
                              type="password"
                              placeholder="Enter new client secret"
                              {...updateForm.register("client_secret")}
                            />
                            {updateForm.formState.errors.client_secret && (
                              <p className="text-sm text-destructive">
                                {updateForm.formState.errors.client_secret.message}
                              </p>
                            )}
                          </div>
                          <DialogFooter>
                            <Button type="submit">Update</Button>
                          </DialogFooter>
                        </form>
                      </DialogContent>
                    </Dialog>

                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => {
                        if (confirm("Remove this data source? This cannot be undone.")) {
                          onRemoveSource(source.id);
                        }
                      }}
                    >
                      <Trash2 className="size-3" />
                      Remove
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
