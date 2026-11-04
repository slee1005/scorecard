import * as SQLite from "expo-sqlite";
import type { components } from "./api-schema";
export type Project = Required<components["schemas"]["Project"]>;
export type Course = components["schemas"]["Course"];
export type Summary = {
  project: Project;
  totals: Record<
    string,
    { score: number | null; relative: number | null; played: number }
  >;
};
// Local development only. iOS simulator / adb reverse reach the same loopback server.
// A hosted endpoint requires a separate authenticated HTTPS backend deployment.
export const BASE = "http://127.0.0.1:8775/api/v1";
export class Conflict extends Error {}
let database: Promise<SQLite.SQLiteDatabase> | undefined;
async function db() {
  if (!database)
    database = (async () => {
      const d = await SQLite.openDatabaseAsync("studio.db");
      await d.execAsync(
        "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL); CREATE TABLE IF NOT EXISTS pending (id TEXT PRIMARY KEY, body TEXT NOT NULL);",
      );
      return d;
    })();
  return database;
}
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (r.status === 409)
    throw new Conflict(
      "The web project has changed. Your offline edits are retained. Resolve this conflict before syncing.",
    );
  if (!r.ok) throw Error(await r.text());
  return r.json();
}
export async function cached<T>(key: string): Promise<T | null> {
  const row = await (
    await db()
  ).getFirstAsync<{ value: string }>(
    "SELECT value FROM cache WHERE key=?",
    key,
  );
  return row ? JSON.parse(row.value) : null;
}
export async function cache(key: string, value: unknown) {
  await (
    await db()
  ).runAsync(
    "INSERT OR REPLACE INTO cache VALUES (?,?)",
    key,
    JSON.stringify(value),
  );
}
export async function openProject(id: string): Promise<Summary> {
  const d = await db();
  const pending = await d.getFirstAsync<{ body: string }>(
    "SELECT body FROM pending WHERE id=?",
    id,
  );
  if (pending) {
    const summary = await cached<Summary>("project:" + id);
    if (summary) return { ...summary, project: JSON.parse(pending.body) };
  }
  try {
    const data = await request<Summary>("/projects/" + id);
    await cache("project:" + id, data);
    await cache("last", id);
    return data;
  } catch (e) {
    const local = await cached<Summary>("project:" + id);
    if (local) return local;
    throw e;
  }
}
export async function stage(project: Project) {
  await (
    await db()
  ).runAsync(
    "INSERT OR REPLACE INTO pending VALUES (?,?)",
    project.id,
    JSON.stringify(project),
  );
  const old = await cached<Summary>("project:" + project.id);
  if (old) await cache("project:" + project.id, { ...old, project });
}
export async function pendingCount() {
  return (await (await db()).getAllAsync("SELECT id FROM pending")).length;
}
export async function sync(): Promise<void> {
  const d = await db();
  const rows = await d.getAllAsync<{ id: string; body: string }>(
    "SELECT id,body FROM pending",
  );
  for (const row of rows) {
    const p = JSON.parse(row.body) as Project;
    const latest = await request<Summary>("/projects/" + row.id);
    if (latest.project.revision !== p.revision)
      throw new Conflict(
        "Newer server data exists. Offline changes have been kept on this device.",
      );
    const saved = await request<Summary>("/projects/" + p.id, {
      method: "PUT",
      body: row.body,
    });
    await cache("project:" + p.id, saved);
    await d.runAsync(
      "DELETE FROM pending WHERE id=? AND body=?",
      row.id,
      row.body,
    );
  }
}
// Resolve only by explicit user action: export the draft or discard it and fetch the server.
export async function discardPending(id: string) {
  await (await db()).runAsync("DELETE FROM pending WHERE id=?", id);
  return openProject(id);
}
