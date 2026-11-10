import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { healthzResponseSchema } from "@seelice/shared";
import { afterAll, describe, expect, it } from "vitest";
import { buildApp } from "../src/app.ts";
import { loadConfig } from "../src/config.ts";

const config = loadConfig({ NODE_ENV: "test" });
const webRoot = mkdtempSync(join(tmpdir(), "seelice-web-"));
writeFileSync(join(webRoot, "index.html"), "<!doctype html><title>Seelice</title>");

afterAll(() => {
  rmSync(webRoot, { recursive: true, force: true });
});

describe("GET /api/healthz", () => {
  it("answers ok", async () => {
    const app = await buildApp(config, { webRoot });
    const response = await app.inject({ method: "GET", url: "/api/healthz" });
    expect(response.statusCode).toBe(200);
    expect(healthzResponseSchema.parse(response.json())).toEqual({ status: "ok" });
  });
});

describe("unknown routes", () => {
  it("returns a JSON 404 for unknown API routes", async () => {
    const app = await buildApp(config, { webRoot });
    const response = await app.inject({ method: "GET", url: "/api/does-not-exist" });
    expect(response.statusCode).toBe(404);
    expect(response.json()).toEqual({ error: "not_found" });
  });

  it("serves the web interface for unknown page paths", async () => {
    const app = await buildApp(config, { webRoot });
    const response = await app.inject({ method: "GET", url: "/cameras/42" });
    expect(response.statusCode).toBe(200);
    expect(response.headers["content-type"]).toContain("text/html");
  });

  it("returns a JSON 404 when the web interface is not built", async () => {
    const app = await buildApp(config, { webRoot: join(webRoot, "missing") });
    const response = await app.inject({ method: "GET", url: "/" });
    expect(response.statusCode).toBe(404);
  });
});
