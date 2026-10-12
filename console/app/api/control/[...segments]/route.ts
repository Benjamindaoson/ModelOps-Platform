import { NextRequest, NextResponse } from "next/server";

type Context = { params: Promise<{ segments: string[] }> };
const MAX_MUTATION_BYTES = 512 * 1024;

class PayloadTooLarge extends Error {}

/** Stream and bound tenant-provided JSON before buffering it in the Node proxy. */
async function boundedBody(req: NextRequest): Promise<string | undefined> {
  if (req.method === "GET" || req.method === "HEAD" || !req.body) return undefined;
  const supplied = req.headers.get("content-length");
  if (supplied) {
    const size = Number(supplied);
    if (!Number.isSafeInteger(size) || size < 0 || size > MAX_MUTATION_BYTES) {
      throw new PayloadTooLarge();
    }
  }
  const decoder = new TextDecoder();
  const chunks: string[] = [];
  const reader = req.body.getReader();
  let total = 0;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > MAX_MUTATION_BYTES) {
      await reader.cancel();
      throw new PayloadTooLarge();
    }
    chunks.push(decoder.decode(value, { stream: true }));
  }
  chunks.push(decoder.decode());
  return chunks.join("");
}

async function forward(req: NextRequest, context: Context) {
  const api = process.env.MODELOPS_API_URL;
  if (!api) return NextResponse.json({ detail: "Control API not configured" }, { status: 503 });
  const token = req.cookies.get("modelops_session")?.value;
  if (!token) return NextResponse.json({ detail: "Not signed in" }, { status: 401 });

  if (req.method !== "GET" && req.method !== "HEAD") {
    const declared = process.env.MODELOPS_PUBLIC_ORIGIN;
    const allowed = declared ? new URL(declared).origin : req.nextUrl.origin;
    if (req.headers.get("origin") !== allowed) {
      return NextResponse.json({ detail: "Origin rejected" }, { status: 403 });
    }
  }

  const { segments } = await context.params;
  if (!segments.length || !segments.every(s => /^[a-zA-Z0-9_-]{1,100}$/.test(s))) {
    return NextResponse.json({ detail: "Invalid API path" }, { status: 400 });
  }
  try {
    const endpoint = new URL("/api/v1/" + segments.join("/") + req.nextUrl.search, api);
    const headers: Record<string, string> = { Authorization: "Bearer " + token };
    const requestBody = await boundedBody(req);
    if (requestBody !== undefined) headers["Content-Type"] = "application/json";
    const upstream = await fetch(endpoint, {
      method: req.method,
      headers,
      body: requestBody,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(15000),
    });
    const result = await upstream.text();
    return new Response(result, {
      status: upstream.status,
      headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
    });
  } catch (error) {
    if (error instanceof PayloadTooLarge) {
      return NextResponse.json({ detail: "JSON request exceeds 512 KiB" }, { status: 413 });
    }
    return NextResponse.json({ detail: "ModelOps API unreachable" }, { status: 502 });
  }
}

export async function GET(req: NextRequest, ctx: Context) { return forward(req, ctx); }
export async function POST(req: NextRequest, ctx: Context) { return forward(req, ctx); }
export async function PATCH(req: NextRequest, ctx: Context) { return forward(req, ctx); }
export async function DELETE(req: NextRequest, ctx: Context) { return forward(req, ctx); }
