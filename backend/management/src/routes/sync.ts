import { Router, Response } from "express";
import { query } from "../db/index.js";
import { authMiddleware, AuthRequest } from "../middleware/auth.js";

const router = Router();
router.use(authMiddleware);

router.get("/history/:projectId", async (req: AuthRequest, res: Response) => {
  try {
    const result = await query(
      `SELECT sh.*, ds.source_type 
       FROM sync_history sh 
       JOIN project_data_sources ds ON sh.data_source_id = ds.id
       WHERE sh.project_id = $1 AND sh.tenant_id = $2 
       ORDER BY sh.started_at DESC LIMIT 50`,
      [req.params.projectId, req.user!.tenantId]
    );
    res.json(result.rows);
  } catch (error) {
    console.error("Get sync history error:", error);
    res.status(500).json({ error: "Internal server error" });
  }
});

router.get("/status/:projectId", async (req: AuthRequest, res: Response) => {
  try {
    const sources = await query(
      `SELECT ds.id, ds.source_type, ds.sync_interval_minutes, ds.last_sync_at, ds.sync_enabled,
              (SELECT COUNT(*) FROM teams_messages tm WHERE tm.project_id = ds.project_id AND tm.tenant_id = ds.tenant_id) as message_count,
              (SELECT COUNT(DISTINCT tm.team) FROM teams_messages tm WHERE tm.project_id = ds.project_id AND tm.tenant_id = ds.tenant_id AND tm.team IS NOT NULL) as team_count,
              (SELECT COUNT(DISTINCT tm.channel) FROM teams_messages tm WHERE tm.project_id = ds.project_id AND tm.tenant_id = ds.tenant_id AND tm.channel IS NOT NULL) as channel_count
       FROM project_data_sources ds 
       WHERE ds.project_id = $1 AND ds.tenant_id = $2`,
      [req.params.projectId, req.user!.tenantId]
    );

    const recent = await query(
      `SELECT * FROM sync_history 
       WHERE project_id = $1 AND tenant_id = $2 
       ORDER BY started_at DESC LIMIT 5`,
      [req.params.projectId, req.user!.tenantId]
    );

    res.json({
      sources: sources.rows,
      recentSyncs: recent.rows,
    });
  } catch (error) {
    console.error("Get sync status error:", error);
    res.status(500).json({ error: "Internal server error" });
  }
});

export default router;
