import { Router, Response } from "express";
import { z } from "zod";
import { query } from "../db/index.js";
import { authMiddleware, AuthRequest } from "../middleware/auth.js";

const router = Router();
router.use(authMiddleware);

const createProjectSchema = z.object({
  name: z.string().min(1).max(100),
  description: z.string().max(500).optional().default(""),
});

router.get("/", async (req: AuthRequest, res: Response) => {
  try {
    const result = await query(
      `SELECT p.id, p.name, p.description, p.created_at,
              (SELECT COUNT(*) FROM teams_messages tm WHERE tm.project_id = p.id) as message_count,
              (SELECT COUNT(*) FROM project_data_sources ds WHERE ds.project_id = p.id) as source_count
       FROM projects p WHERE p.tenant_id = $1 ORDER BY p.created_at DESC`,
      [req.user!.tenantId]
    );
    res.json(result.rows);
  } catch (error) {
    console.error("List projects error:", error);
    res.status(500).json({ error: "Internal server error" });
  }
});

router.post("/", async (req: AuthRequest, res: Response) => {
  try {
    const data = createProjectSchema.parse(req.body);
    const result = await query(
      "INSERT INTO projects (tenant_id, name, description) VALUES ($1, $2, $3) RETURNING *",
      [req.user!.tenantId, data.name, data.description]
    );
    res.status(201).json(result.rows[0]);
  } catch (error) {
    if (error instanceof z.ZodError) {
      res.status(400).json({ error: error.errors[0].message });
      return;
    }
    console.error("Create project error:", error);
    res.status(500).json({ error: "Internal server error" });
  }
});

router.get("/:id", async (req: AuthRequest, res: Response) => {
  try {
    const result = await query(
      `SELECT p.*, 
              (SELECT COUNT(*) FROM teams_messages tm WHERE tm.project_id = p.id) as message_count,
              (SELECT COUNT(*) FROM project_data_sources ds WHERE ds.project_id = p.id) as source_count
       FROM projects p WHERE p.id = $1 AND p.tenant_id = $2`,
      [req.params.id, req.user!.tenantId]
    );
    if (result.rows.length === 0) {
      res.status(404).json({ error: "Project not found" });
      return;
    }
    res.json(result.rows[0]);
  } catch (error) {
    console.error("Get project error:", error);
    res.status(500).json({ error: "Internal server error" });
  }
});

router.put("/:id", async (req: AuthRequest, res: Response) => {
  try {
    const data = createProjectSchema.parse(req.body);
    const result = await query(
      "UPDATE projects SET name = $1, description = $2 WHERE id = $3 AND tenant_id = $4 RETURNING *",
      [data.name, data.description, req.params.id, req.user!.tenantId]
    );
    if (result.rows.length === 0) {
      res.status(404).json({ error: "Project not found" });
      return;
    }
    res.json(result.rows[0]);
  } catch (error) {
    if (error instanceof z.ZodError) {
      res.status(400).json({ error: error.errors[0].message });
      return;
    }
    console.error("Update project error:", error);
    res.status(500).json({ error: "Internal server error" });
  }
});

router.delete("/:id", async (req: AuthRequest, res: Response) => {
  try {
    await query("DELETE FROM teams_messages WHERE project_id = $1 AND tenant_id = $2", [
      req.params.id,
      req.user!.tenantId,
    ]);
    await query("DELETE FROM sync_metadata WHERE project_id = $1 AND tenant_id = $2", [
      req.params.id,
      req.user!.tenantId,
    ]);
    await query("DELETE FROM sync_history WHERE project_id = $1 AND tenant_id = $2", [
      req.params.id,
      req.user!.tenantId,
    ]);
    const result = await query(
      "DELETE FROM projects WHERE id = $1 AND tenant_id = $2 RETURNING id",
      [req.params.id, req.user!.tenantId]
    );
    if (result.rows.length === 0) {
      res.status(404).json({ error: "Project not found" });
      return;
    }
    res.json({ success: true });
  } catch (error) {
    console.error("Delete project error:", error);
    res.status(500).json({ error: "Internal server error" });
  }
});

export default router;
