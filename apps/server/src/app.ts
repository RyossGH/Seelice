import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import fastifyStatic from "@fastify/static";
import type { HealthzResponse } from "@seelice/shared";
import Fastify, { type FastifyInstance } from "fastify";
import type { Config } from "./config.ts";

export interface BuildAppOptions {
  /** Folder of the built web interface. Defaults to `apps/web/dist`. */
  webRoot?: string;
}

const defaultWebRoot = fileURLToPath(new URL("../../web/dist", import.meta.url));

export async function buildApp(
  config: Config,
  options: BuildAppOptions = {},
): Promise<FastifyInstance> {
  const app = Fastify({
    logger: config.NODE_ENV === "test" ? false : { level: "info" },
  });

  app.get("/api/healthz", (): HealthzResponse => ({ status: "ok" }));

  const webRoot = options.webRoot ?? defaultWebRoot;
  const hasWebInterface = existsSync(webRoot);
  if (hasWebInterface) {
    await app.register(fastifyStatic, { root: webRoot });
  }

  app.setNotFoundHandler((request, reply) => {
    const isPageRequest = request.method === "GET" && !request.url.startsWith("/api/");
    if (hasWebInterface && isPageRequest) {
      // Single-page application: unknown paths are handled by the browser router.
      return reply.sendFile("index.html");
    }
    return reply.code(404).send({ error: "not_found" });
  });

  return app;
}
