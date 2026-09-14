import { Pool } from "pg";

// Reused across warm invocations of the same function instance -- a fresh
// Pool per request would exhaust Supabase's connection limit quickly under
// concurrent serverless invocations. Use the TRANSACTION pooler connection
// string here (see web/.env.example), which is what this pattern expects.
let pool: Pool | undefined;

export function getPool(): Pool {
  if (!pool) {
    const connectionString = process.env.DATABASE_URL;
    if (!connectionString) {
      throw new Error("DATABASE_URL is not set (Supabase transaction-pooler connection string)");
    }
    pool = new Pool({
      connectionString,
      ssl: { rejectUnauthorized: false },
      max: 3,
      idleTimeoutMillis: 10_000,
    });
  }
  return pool;
}
