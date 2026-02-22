import { z } from "zod";

export const loginSchema = z.object({
  email: z.string().email("Please enter a valid email"),
  password: z.string().min(1, "Password is required"),
});

export const signupSchema = z.object({
  name: z.string().min(1, "Name is required"),
  email: z.string().email("Please enter a valid email"),
  password: z.string().min(8, "Password must be at least 8 characters"),
  tenantName: z.string().min(1, "Organization name is required"),
});

export const createProjectSchema = z.object({
  name: z.string().min(1, "Project name is required").max(100),
  description: z.string().max(500).optional(),
});

export const teamsCredentialsSchema = z.object({
  client_id: z.string().min(1, "Client ID is required"),
  client_secret: z.string().min(1, "Client Secret is required"),
  tenant_id: z.string().min(1, "Tenant ID is required"),
});

export const syncSettingsSchema = z.object({
  syncIntervalMinutes: z.number().int().min(0).max(1440),
  syncEnabled: z.boolean(),
});

export type LoginForm = z.infer<typeof loginSchema>;
export type SignupForm = z.infer<typeof signupSchema>;
export type CreateProjectForm = z.infer<typeof createProjectSchema>;
export type TeamsCredentialsForm = z.infer<typeof teamsCredentialsSchema>;
export type SyncSettingsForm = z.infer<typeof syncSettingsSchema>;
