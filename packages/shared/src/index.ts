import { z } from "zod";

/** Response of the public liveness probe `GET /api/healthz`. */
export const healthzResponseSchema = z.object({
  status: z.literal("ok"),
});

export type HealthzResponse = z.infer<typeof healthzResponseSchema>;
