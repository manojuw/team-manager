import { Router, Response } from "express";
import bcrypt from "bcryptjs";
import { z } from "zod";
import { query } from "../db/index.js";
import { generateToken, authMiddleware, AuthRequest } from "../middleware/auth.js";

const router = Router();

const signupSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8),
  name: z.string().min(1),
  tenantName: z.string().min(1),
});

const loginSchema = z.object({
  email: z.string().email(),
  password: z.string(),
});

router.post("/signup", async (req: AuthRequest, res: Response) => {
  try {
    const data = signupSchema.parse(req.body);

    const existing = await query("SELECT id FROM users WHERE email = $1", [
      data.email,
    ]);
    if (existing.rows.length > 0) {
      res.status(400).json({ error: "Email already registered" });
      return;
    }

    const tenantResult = await query(
      "INSERT INTO tenants (name) VALUES ($1) RETURNING id",
      [data.tenantName]
    );
    const tenantId = tenantResult.rows[0].id;

    const passwordHash = await bcrypt.hash(data.password, 12);
    const userResult = await query(
      "INSERT INTO users (email, password_hash, name, tenant_id, role) VALUES ($1, $2, $3, $4, $5) RETURNING id, role",
      [data.email, passwordHash, data.name, tenantId, "admin"]
    );

    const user = userResult.rows[0];
    const token = generateToken({
      userId: user.id,
      tenantId,
      email: data.email,
      name: data.name,
      role: user.role,
    });

    res.status(201).json({
      token,
      user: {
        id: user.id,
        email: data.email,
        name: data.name,
        tenantId,
        role: user.role,
      },
    });
  } catch (error) {
    if (error instanceof z.ZodError) {
      res.status(400).json({ error: error.errors[0].message });
      return;
    }
    console.error("Signup error:", error);
    res.status(500).json({ error: "Internal server error" });
  }
});

router.post("/login", async (req: AuthRequest, res: Response) => {
  try {
    const data = loginSchema.parse(req.body);

    const result = await query(
      "SELECT u.id, u.email, u.password_hash, u.name, u.tenant_id, u.role, t.name as tenant_name FROM users u JOIN tenants t ON u.tenant_id = t.id WHERE u.email = $1",
      [data.email]
    );

    if (result.rows.length === 0) {
      res.status(401).json({ error: "Invalid email or password" });
      return;
    }

    const user = result.rows[0];
    const validPassword = await bcrypt.compare(data.password, user.password_hash);
    if (!validPassword) {
      res.status(401).json({ error: "Invalid email or password" });
      return;
    }

    const token = generateToken({
      userId: user.id,
      tenantId: user.tenant_id,
      email: user.email,
      name: user.name,
      role: user.role,
    });

    res.json({
      token,
      user: {
        id: user.id,
        email: user.email,
        name: user.name,
        tenantId: user.tenant_id,
        tenantName: user.tenant_name,
        role: user.role,
      },
    });
  } catch (error) {
    if (error instanceof z.ZodError) {
      res.status(400).json({ error: error.errors[0].message });
      return;
    }
    console.error("Login error:", error);
    res.status(500).json({ error: "Internal server error" });
  }
});

router.get("/me", authMiddleware, async (req: AuthRequest, res: Response) => {
  try {
    const result = await query(
      "SELECT u.id, u.email, u.name, u.tenant_id, u.role, t.name as tenant_name FROM users u JOIN tenants t ON u.tenant_id = t.id WHERE u.id = $1",
      [req.user!.userId]
    );

    if (result.rows.length === 0) {
      res.status(404).json({ error: "User not found" });
      return;
    }

    const user = result.rows[0];
    res.json({
      id: user.id,
      email: user.email,
      name: user.name,
      tenantId: user.tenant_id,
      tenantName: user.tenant_name,
      role: user.role,
    });
  } catch (error) {
    console.error("Get user error:", error);
    res.status(500).json({ error: "Internal server error" });
  }
});

export default router;
