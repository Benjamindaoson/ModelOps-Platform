import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const declared = process.env.MODELOPS_PUBLIC_ORIGIN;
  const origin = declared ? new URL(declared).origin : req.nextUrl.origin;
  if (req.headers.get("origin") !== origin) {
    return NextResponse.json({ detail: "Origin rejected" }, { status: 403 });
  }
  const response = NextResponse.json({ authenticated: false });
  response.cookies.set("modelops_session", "", {
    httpOnly: true, secure: process.env.MODELOPS_PUBLIC_ORIGIN?.startsWith("https://") ?? false,
    sameSite: "strict", path: "/", maxAge: 0,
  });
  return response;
}
