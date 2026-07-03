import { z } from 'zod';

export const QueryRequestSchema = z.object({
  query: z.string().min(1),
});

export const TokenRequestSchema = z.object({
  username: z.string().min(1),
  password: z.string().min(1),
});

export const TokenResponseSchema = z.object({
  access_token: z.string().min(1),
  token_type: z.literal('bearer'),
  expires_in: z.number().int().positive(),
});

export const StepEventSchema = z.object({
  type: z.literal('step'),
  data: z.object({
    node: z.string().min(1),
    message: z.string().min(1),
  }),
});

export const TokenEventSchema = z.object({
  type: z.literal('token'),
  data: z.string(),
});

export const DoneEventSchema = z.object({
  type: z.literal('done'),
  data: z.object({
    run_id: z.string().uuid(),
    cost_usd: z.number().nonnegative(),
    latency_ms: z.number().int().nonnegative(),
  }),
});

export const AgentEventSchema = z.discriminatedUnion('type', [
  StepEventSchema,
  TokenEventSchema,
  DoneEventSchema,
]);

export const UsageStatsSchema = z.object({
  queries_today: z.number().int().nonnegative(),
  avg_latency_ms: z.number().nonnegative(),
  p95_latency_ms: z.number().nonnegative(),
  total_cost_usd: z.number().nonnegative(),
  avg_cost_per_query: z.number().nonnegative(),
  top_tools: z.array(z.string()),
});

export type QueryRequest = z.infer<typeof QueryRequestSchema>;
export type TokenRequest = z.infer<typeof TokenRequestSchema>;
export type TokenResponse = z.infer<typeof TokenResponseSchema>;
export type StepEvent = z.infer<typeof StepEventSchema>;
export type TokenEvent = z.infer<typeof TokenEventSchema>;
export type DoneEvent = z.infer<typeof DoneEventSchema>;
export type AgentEvent = z.infer<typeof AgentEventSchema>;
export type UsageStats = z.infer<typeof UsageStatsSchema>;
