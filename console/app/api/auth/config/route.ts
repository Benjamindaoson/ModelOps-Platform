import { NextResponse } from "next/server";
import { oidcEnabled } from "@/lib/oidc";

export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json({mode:oidcEnabled()?"oidc":process.env.MODELOPS_ENV==="production"?"unavailable":"development-token"}, {
    headers:{"Cache-Control":"no-store"},
  });
}
