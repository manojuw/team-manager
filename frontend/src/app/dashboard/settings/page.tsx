"use client";

import { useAuth } from "@/hooks/use-auth";
import { useProject } from "@/hooks/use-project";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Settings, User, Building, Shield } from "lucide-react";

export default function SettingsPage() {
  const { user } = useAuth();
  const { currentProject } = useProject();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">Account and project information</p>
      </div>

      <Separator />

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <User className="size-4" />
              User Information
            </CardTitle>
            <CardDescription>Your account details</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">Name</p>
              <p className="text-sm font-medium">{user?.name || "—"}</p>
            </div>
            <Separator />
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">Email</p>
              <p className="text-sm font-medium">{user?.email || "—"}</p>
            </div>
            <Separator />
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">Role</p>
              <Badge variant="secondary">{user?.role || "—"}</Badge>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Building className="size-4" />
              Organization
            </CardTitle>
            <CardDescription>Your organization details</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">Tenant Name</p>
              <p className="text-sm font-medium">{user?.tenantName || "—"}</p>
            </div>
            <Separator />
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">Tenant ID</p>
              <p className="text-sm font-medium font-mono text-xs">{user?.tenantId || "—"}</p>
            </div>
          </CardContent>
        </Card>

        {currentProject && (
          <Card className="md:col-span-2">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Shield className="size-4" />
                Current Project
              </CardTitle>
              <CardDescription>Currently selected project details</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-1">
                  <p className="text-sm text-muted-foreground">Project Name</p>
                  <p className="text-sm font-medium">{currentProject.name}</p>
                </div>
                <div className="space-y-1">
                  <p className="text-sm text-muted-foreground">Description</p>
                  <p className="text-sm font-medium">{currentProject.description || "No description"}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
