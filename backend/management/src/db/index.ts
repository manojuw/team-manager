import pg from "pg";
const { Pool } = pg;

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: process.env.DATABASE_URL?.includes("localhost")
    ? false
    : { rejectUnauthorized: false },
});

export async function query(text: string, params?: unknown[]) {
  const client = await pool.connect();
  try {
    const result = await client.query(text, params);
    return result;
  } finally {
    client.release();
  }
}

export async function initDatabase() {
  await query(`
    CREATE TABLE IF NOT EXISTS tenants (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      name TEXT NOT NULL,
      created_at TIMESTAMPTZ DEFAULT NOW()
    )
  `);

  await query(`
    CREATE TABLE IF NOT EXISTS users (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      email TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      name TEXT NOT NULL,
      tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
      role TEXT DEFAULT 'member',
      created_at TIMESTAMPTZ DEFAULT NOW()
    )
  `);

  await query(`
    CREATE TABLE IF NOT EXISTS projects (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
      name TEXT NOT NULL,
      description TEXT DEFAULT '',
      created_at TIMESTAMPTZ DEFAULT NOW()
    )
  `);

  await query(`
    CREATE TABLE IF NOT EXISTS project_data_sources (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
      source_type TEXT NOT NULL,
      config JSONB DEFAULT '{}',
      sync_interval_minutes INTEGER DEFAULT 0,
      last_sync_at TIMESTAMPTZ,
      sync_enabled BOOLEAN DEFAULT false,
      created_at TIMESTAMPTZ DEFAULT NOW()
    )
  `);

  await query(`CREATE EXTENSION IF NOT EXISTS vector`);

  await query(`
    CREATE TABLE IF NOT EXISTS teams_messages (
      id TEXT PRIMARY KEY,
      tenant_id UUID NOT NULL,
      project_id UUID NOT NULL,
      content TEXT NOT NULL,
      embedding vector(384),
      sender TEXT,
      created_at TEXT,
      team TEXT,
      channel TEXT,
      message_type TEXT DEFAULT 'message',
      message_id TEXT,
      parent_message_id TEXT,
      indexed_at TIMESTAMPTZ DEFAULT NOW()
    )
  `);

  await query(`
    CREATE TABLE IF NOT EXISTS sync_metadata (
      id TEXT PRIMARY KEY,
      tenant_id UUID NOT NULL,
      project_id UUID NOT NULL,
      team_id TEXT NOT NULL,
      channel_id TEXT NOT NULL,
      last_sync TEXT NOT NULL,
      updated_at TIMESTAMPTZ DEFAULT NOW()
    )
  `);

  await query(`
    CREATE TABLE IF NOT EXISTS sync_history (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      tenant_id UUID NOT NULL,
      project_id UUID NOT NULL,
      data_source_id UUID NOT NULL,
      status TEXT NOT NULL DEFAULT 'running',
      messages_added INTEGER DEFAULT 0,
      messages_fetched INTEGER DEFAULT 0,
      error_message TEXT,
      started_at TIMESTAMPTZ DEFAULT NOW(),
      completed_at TIMESTAMPTZ
    )
  `);

  await query(`CREATE INDEX IF NOT EXISTS idx_projects_tenant ON projects(tenant_id)`);
  await query(`CREATE INDEX IF NOT EXISTS idx_data_sources_project ON project_data_sources(project_id)`);
  await query(`CREATE INDEX IF NOT EXISTS idx_data_sources_tenant ON project_data_sources(tenant_id)`);
  await query(`CREATE INDEX IF NOT EXISTS idx_messages_tenant ON teams_messages(tenant_id)`);
  await query(`CREATE INDEX IF NOT EXISTS idx_messages_project ON teams_messages(project_id)`);
  await query(`CREATE INDEX IF NOT EXISTS idx_sync_history_project ON sync_history(project_id)`);

  console.log("Database tables initialized");
}

export default pool;
