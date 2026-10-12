import { NextRequest, NextResponse } from "next/server";

const SESSION = "modelops_session";

function sameOrigin(req: NextRequest): boolean {
  const declared = process.env.MODELOPS_PUBLIC_ORIGIN;
  const allowed = declared ? new URL(declared).origin : req.nextUrl.origin;
  return req.headers.get("origin") === allowed;
}

export async function POST(req: NextRequest) {
  if (process.env.MODELOPS_ENV === "production" && process.env.MODELOPS_CONSOLE_AUTH !== "oidc") {
    return NextResponse.json({detail:"OIDC login required in production"},{status:503});
  }
  if (process.env.MODELOPS_CONSOLE_AUTH === "oidc") {
    return NextResponse.json({detail:"Manual token login disabled; use SSO"},{status:403});
  }
  if (!sameOrigin(req)) return NextResponse.json({ detail: "Origin rejected" }, { status: 403 });
  const api = process.env.MODELOPS_API_URL;
  if (!api) return NextResponse.json({ detail: "Control API not configured" }, { status: 503 });
  let token: unknown;
  try {
    ({ token } = await req.json());
  } catch {
    return NextResponse.json({ detail: "Invalid JSON" }, { status: 400 });
  }
  if (typeof token !== "string" || token.length > 8192 || token.length < 20) {
    return NextResponse.json({ detail: "Invalid OIDC bearer token" }, { status: 400 });
  }
  try {
    const check = await fetch(new URL("/api/v1/me", api), {
      headers: { Authorization: "Bearer " + token }, cache: "no-store",
    });
    if (!check.ok) return NextResponse.json({ detail: "Bearer token rejected by ModelOps API" }, { status: 401 });
    const principal = await check.json();
    if (!principal?.tenant || !principal?.role) {
      return NextResponse.json({ detail: "Incomplete identity" }, { status: 401 });
    }
    const response = NextResponse.json({ user: principal });
    response.cookies.set(SESSION, token, {
      httpOnly: true, secure: process.env.MODELOPS_PUBLIC_ORIGIN?.startsWith("https://") ?? false,
      sameSite: "strict", path: "/", maxAge: 60 * 60,
    });
    return response;
  } catch {
    return NextResponse.json({ detail: "Control API unavailable" }, { status: 503 });
  }
}
