"use client";

import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import { useProject } from "@/hooks/use-project";
import { projects } from "@/lib/api";
import { createProjectSchema, type CreateProjectForm } from "@/lib/schemas";

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
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Plus, FolderOpen, Trash2, ExternalLink } from "lucide-react";

interface Project {
  id: string;
  name: string;
  description: string;
  message_count?: number;
  source_count?: number;
  created_at?: string;
}

export default function ProjectsPage() {
  const { currentProject, setCurrentProject } = useProject();
  const [projectList, setProjectList] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  const form = useForm<CreateProjectForm>({
    resolver: zodResolver(createProjectSchema),
    defaultValues: {
      name: "",
      description: "",
    },
  });

  async function fetchProjects() {
    try {
      const data = await projects.list();
      setProjectList(data);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load projects");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchProjects();
  }, []);

  async function onCreateProject(values: CreateProjectForm) {
    setCreating(true);
    try {
      await projects.create(values);
      toast.success("Project created successfully");
      form.reset();
      setDialogOpen(false);
      await fetchProjects();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to create project");
    } finally {
      setCreating(false);
    }
  }

  async function onDeleteProject(id: string) {
    try {
      await projects.delete(id);
      toast.success("Project deleted");
      if (currentProject?.id === id) {
        setCurrentProject(null);
      }
      setDeleteConfirm(null);
      await fetchProjects();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to delete project");
    }
  }

  function formatDate(dateStr?: string) {
    if (!dateStr) return "—";
    return new Date(dateStr).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Projects</h1>
          <p className="text-muted-foreground">
            Manage your knowledge base projects
          </p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="size-4" />
              New Project
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create New Project</DialogTitle>
            </DialogHeader>
            <form onSubmit={form.handleSubmit(onCreateProject)} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="name">Project Name</Label>
                <Input
                  id="name"
                  placeholder="My Project"
                  {...form.register("name")}
                />
                {form.formState.errors.name && (
                  <p className="text-sm text-destructive">
                    {form.formState.errors.name.message}
                  </p>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="description">Description</Label>
                <Input
                  id="description"
                  placeholder="Optional description"
                  {...form.register("description")}
                />
                {form.formState.errors.description && (
                  <p className="text-sm text-destructive">
                    {form.formState.errors.description.message}
                  </p>
                )}
              </div>
              <DialogFooter>
                <Button type="submit" disabled={creating}>
                  {creating ? "Creating…" : "Create Project"}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <Separator />

      {loading ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Card key={i}>
              <CardHeader>
                <Skeleton className="h-5 w-32" />
                <Skeleton className="h-4 w-48" />
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <Skeleton className="h-4 w-24" />
                  <Skeleton className="h-4 w-20" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : projectList.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <FolderOpen className="size-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold">No projects yet</h3>
          <p className="text-muted-foreground mt-1">
            Create your first project to get started
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {projectList.map((project) => {
            const isActive = currentProject?.id === project.id;
            return (
              <Card
                key={project.id}
                className={isActive ? "border-primary" : ""}
              >
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div className="space-y-1">
                      <CardTitle className="flex items-center gap-2">
                        {project.name}
                        {isActive && (
                          <Badge variant="default" className="text-xs">
                            Active
                          </Badge>
                        )}
                      </CardTitle>
                      <CardDescription>
                        {project.description || "No description"}
                      </CardDescription>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    <div className="flex items-center gap-4 text-sm text-muted-foreground">
                      <span>{project.message_count ?? 0} messages</span>
                      <span>{project.source_count ?? 0} sources</span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Created {formatDate(project.created_at)}
                    </p>
                    <Separator />
                    <div className="flex items-center gap-2">
                      <Button
                        variant={isActive ? "secondary" : "default"}
                        size="sm"
                        className="flex-1"
                        onClick={() => {
                          setCurrentProject(project);
                          toast.success(`Selected "${project.name}"`);
                        }}
                      >
                        <ExternalLink className="size-3" />
                        {isActive ? "Selected" : "Select"}
                      </Button>
                      {deleteConfirm === project.id ? (
                        <div className="flex items-center gap-1">
                          <Button
                            variant="destructive"
                            size="sm"
                            onClick={() => onDeleteProject(project.id)}
                          >
                            Confirm
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setDeleteConfirm(null)}
                          >
                            Cancel
                          </Button>
                        </div>
                      ) : (
                        <Button
                          variant="outline"
                          size="icon-sm"
                          onClick={() => setDeleteConfirm(project.id)}
                        >
                          <Trash2 className="size-3" />
                        </Button>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
