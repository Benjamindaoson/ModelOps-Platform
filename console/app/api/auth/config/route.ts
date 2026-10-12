import { NextResponse } from "next/server";
import { oidcEnabled } from "@/lib/oidc";

export const dynamic = "force-dynamic";

export async function GET() {
  const isProduction = process.env.MODELOPS_ENV === "production" ||
    (process.env.NODE_ENV === "production" && process.env.MODELOPS_ENV !== "development");
  return NextResponse.json({mode:oidcEnabled()?"oidc":isProduction?"unavailable":"development-token"}, {
    headers:{"Cache-Control":"no-store"},
  });
}
