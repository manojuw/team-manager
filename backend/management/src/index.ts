import express from "express";
import cors from "cors";
import helmet from "helmet";
import { initDatabase } from "./db/index.js";
import authRoutes from "./routes/auth.js";
import projectRoutes from "./routes/projects.js";
import dataSourceRoutes from "./routes/datasources.js";
import syncRoutes from "./routes/sync.js";

const app = express();
const PORT = 3001;

app.use(helmet());
app.use(cors({ origin: "*" }));
app.use(express.json());

app.use("/api/auth", authRoutes);
app.use("/api/projects", projectRoutes);
app.use("/api/datasources", dataSourceRoutes);
app.use("/api/sync", syncRoutes);

app.get("/api/health", (_req, res) => {
  res.json({ status: "ok", service: "management-api" });
});

async function start() {
  try {
    await initDatabase();
    app.listen(PORT, "0.0.0.0", () => {
      console.log(`Management API running on port ${PORT}`);
    });
  } catch (error) {
    console.error("Failed to start management API:", error);
    process.exit(1);
  }
}

start();
