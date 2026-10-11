import { NextResponse } from "next/server";
import { oidcEnabled } from "@/lib/oidc";

export async function GET() {
  return NextResponse.json({mode:oidcEnabled()?"oidc":"development-token"}, {
    headers:{"Cache-Control":"no-store"},
  });
}
