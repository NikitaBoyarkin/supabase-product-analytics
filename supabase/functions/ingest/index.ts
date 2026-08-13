// Product Analytics event ingestion endpoint.
// POST {url}/functions/v1/ingest   header: `x-api-key: <key>`
// body: { user_id, event_name, properties?, timestamp? }
//
// The function hashes the API key and calls analytics.ingest_event(),
// a SECURITY DEFINER function that validates the key and writes the event.
// No service-role key is used here: anon + DB-level gating only.

import { createClient } from "@supabase/supabase-js";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type, x-api-key",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function json(body: Record<string, unknown>, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

async function sha256Hex(input: string): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(input),
  );
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }
  if (req.method !== "POST") {
    return json({ error: "method not allowed" }, 405);
  }

  const apiKey = req.headers.get("x-api-key");
  if (!apiKey) {
    return json({ error: "missing x-api-key header" }, 401);
  }

  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch {
    return json({ error: "invalid JSON body" }, 400);
  }

  const { user_id, event_name, properties, timestamp } = body ?? {};
  if (!user_id || typeof event_name !== "string" || !event_name) {
    return json({ error: "user_id and event_name are required" }, 400);
  }

  const keyHash = await sha256Hex(apiKey);

  const client = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_ANON_KEY")!,
  );

  const { data, error } = await client.schema("analytics").rpc("ingest_event", {
    p_key_hash: keyHash,
    p_external_id: String(user_id),
    p_event_name: event_name,
    p_properties:
      typeof properties === "object" && properties !== null ? properties : {},
    p_event_time:
      typeof timestamp === "string" && timestamp ? timestamp : new Date().toISOString(),
  });

  if (error) {
    const status = /invalid api key/i.test(error.message) ? 401 : 500;
    return json({ error: error.message }, status);
  }

  return json({ accepted: true, event_id: data }, 202);
});
