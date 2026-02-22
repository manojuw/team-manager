import { Router, Response } from "express";
import { z } from "zod";
import { query } from "../db/index.js";
import { authMiddleware, AuthRequest } from "../middleware/auth.js";

const router = Router();
router.use(authMiddleware);

const createDataSourceSchema = z.object({
  projectId: z.string().uuid(),
  sourceType: z.string().min(1),
  config: z.record(z.unknown()).optional().default({}),
  syncIntervalMinutes: z.number().int().min(0).optional().default(0),
  syncEnabled: z.boolean().optional().default(false),
});

const updateConfigSchema = z.object({
  config: z.record(z.unknown()).optional(),
  syncIntervalMinutes: z.number().int().min(0).optional(),
  syncEnabled: z.boolean().optional(),
});

router.get("/project/:projectId", async (req: AuthRequest, res: Response) => {
  try {
    const projectCheck = await query(
      "SELECT id FROM projects WHERE id = $1 AND tenant_id = $2",
      [req.params.projectId, req.user!.tenantId]
    );
    if (projectCheck.rows.length === 0) {
      res.status(404).json({ error: "Project not found" });
      return;
    }

    const result = await query(
      `SELECT id, project_id, source_type, config, sync_interval_minutes, 
              last_sync_at, sync_enabled, created_at
       FROM project_data_sources 
       WHERE project_id = $1 AND tenant_id = $2 
       ORDER BY created_at`,
      [req.params.projectId, req.user!.tenantId]
    );

    const sources = result.rows.map((row) => ({
      ...row,
      config: {
        ...row.config,
        client_secret: row.config?.client_secret ? "••••••••" : undefined,
      },
    }));

    res.json(sources);
  } catch (error) {
    console.error("List data sources error:", error);
    res.status(500).json({ error: "Internal server error" });
  }
});

router.post("/", async (req: AuthRequest, res: Response) => {
  try {
    const data = createDataSourceSchema.parse(req.body);

    const projectCheck = await query(
      "SELECT id FROM projects WHERE id = $1 AND tenant_id = $2",
      [data.projectId, req.user!.tenantId]
    );
    if (projectCheck.rows.length === 0) {
      res.status(404).json({ error: "Project not found" });
      return;
    }

    const result = await query(
      `INSERT INTO project_data_sources (project_id, tenant_id, source_type, config, sync_interval_minutes, sync_enabled)
       VALUES ($1, $2, $3, $4, $5, $6) RETURNING *`,
      [
        data.projectId,
        req.user!.tenantId,
        data.sourceType,
        JSON.stringify(data.config),
        data.syncIntervalMinutes,
        data.syncEnabled,
      ]
    );
    res.status(201).json(result.rows[0]);
  } catch (error) {
    if (error instanceof z.ZodError) {
      res.status(400).json({ error: error.errors[0].message });
      return;
    }
    console.error("Create data source error:", error);
    res.status(500).json({ error: "Internal server error" });
  }
});

router.put("/:id", async (req: AuthRequest, res: Response) => {
  try {
    const data = updateConfigSchema.parse(req.body);

    const existing = await query(
      "SELECT id, config FROM project_data_sources WHERE id = $1 AND tenant_id = $2",
      [req.params.id, req.user!.tenantId]
    );
    if (existing.rows.length === 0) {
      res.status(404).json({ error: "Data source not found" });
      return;
    }

    const updates: string[] = [];
    const values: unknown[] = [];
    let paramIdx = 1;

    if (data.config !== undefined) {
      const existingConfig = existing.rows[0].config || {};
      const newConfig = { ...existingConfig, ...data.config };
      updates.push(`config = $${paramIdx++}`);
      values.push(JSON.stringify(newConfig));
    }
    if (data.syncIntervalMinutes !== undefined) {
      updates.push(`sync_interval_minutes = $${paramIdx++}`);
      values.push(data.syncIntervalMinutes);
    }
    if (data.syncEnabled !== undefined) {
      updates.push(`sync_enabled = $${paramIdx++}`);
      values.push(data.syncEnabled);
    }

    if (updates.length === 0) {
      res.json(existing.rows[0]);
      return;
    }

    values.push(req.params.id, req.user!.tenantId);
    const result = await query(
      `UPDATE project_data_sources SET ${updates.join(", ")} WHERE id = $${paramIdx++} AND tenant_id = $${paramIdx} RETURNING *`,
      values
    );

    res.json(result.rows[0]);
  } catch (error) {
    if (error instanceof z.ZodError) {
      res.status(400).json({ error: error.errors[0].message });
      return;
    }
    console.error("Update data source error:", error);
    res.status(500).json({ error: "Internal server error" });
  }
});

router.delete("/:id", async (req: AuthRequest, res: Response) => {
  try {
    const result = await query(
      "DELETE FROM project_data_sources WHERE id = $1 AND tenant_id = $2 RETURNING id",
      [req.params.id, req.user!.tenantId]
    );
    if (result.rows.length === 0) {
      res.status(404).json({ error: "Data source not found" });
      return;
    }
    res.json({ success: true });
  } catch (error) {
    console.error("Delete data source error:", error);
    res.status(500).json({ error: "Internal server error" });
  }
});

router.get("/:id/config", async (req: AuthRequest, res: Response) => {
  try {
    const result = await query(
      "SELECT config FROM project_data_sources WHERE id = $1 AND tenant_id = $2",
      [req.params.id, req.user!.tenantId]
    );
    if (result.rows.length === 0) {
      res.status(404).json({ error: "Data source not found" });
      return;
    }
    res.json(result.rows[0].config);
  } catch (error) {
    console.error("Get config error:", error);
    res.status(500).json({ error: "Internal server error" });
  }
});

export default router;
