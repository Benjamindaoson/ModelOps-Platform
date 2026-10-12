import { NextRequest, NextResponse } from "next/server";
import { constantTimeEqual, discoverOidc, getOidcEnv, oidcEnabled } from "@/lib/oidc";

export async function GET(req: NextRequest) {
  if (!oidcEnabled()) return NextResponse.json({detail:"OIDC not configured"},{status:404});
  const state = req.nextUrl.searchParams.get("state");
  const code = req.nextUrl.searchParams.get("code");
  const stored = req.cookies.get("modelops_pkce_state")?.value;
  const verifier = req.cookies.get("modelops_pkce_verifier")?.value;
  if (!state || !code || !stored || !verifier || !constantTimeEqual(state,stored) ||
      code.length > 4096 || verifier.length < 32) {
    return NextResponse.json({detail:"OIDC callback state or PKCE verifier invalid"},{status:401});
  }
  try {
    const { client, origin } = getOidcEnv();
    const metadata = await discoverOidc();
    const form = new URLSearchParams({
      grant_type:"authorization_code",
      code,
      client_id:client,
      redirect_uri:new URL("/api/auth/callback",origin).toString(),
      code_verifier:verifier,
    });
    // Confidential OIDC clients can supply their secret *server side*, never
    // to the browser. Public PKCE clients do not require one.
    if(process.env.MODELOPS_OIDC_CLIENT_SECRET){
      form.set("client_secret",process.env.MODELOPS_OIDC_CLIENT_SECRET);
    }
    const tokenResp = await fetch(metadata.token_endpoint,{
      method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},
      body:form,cache:"no-store",redirect:"error",signal:AbortSignal.timeout(10000),
    });
    if(!tokenResp.ok) throw new Error("OIDC token exchange failed");
    const token = await tokenResp.json() as {access_token?:unknown;expires_in?:unknown};
    if(typeof token.access_token !== "string" || token.access_token.length > 12000 ||
       token.access_token.length < 20) throw new Error("Invalid identity token response");
    const api = process.env.MODELOPS_API_URL;
    if(!api) throw new Error("Control API missing");
    const verify = await fetch(new URL("/api/v1/me",api),{
      headers:{Authorization:"Bearer "+token.access_token},
      cache:"no-store",redirect:"error",signal:AbortSignal.timeout(7000),
    });
    if(!verify.ok) throw new Error("API rejected identity claims");
    const principal = await verify.json() as {tenant?:unknown;role?:unknown};
    if(!principal.tenant || !principal.role) throw new Error("OIDC claims lack tenant/role");
    const response = NextResponse.redirect(new URL("/dashboard",origin));
    const expiry = typeof token.expires_in === "number" && Number.isFinite(token.expires_in)
      ? Math.max(1,Math.min(3600, Math.floor(token.expires_in)-30)) : 300;
    response.cookies.set("modelops_session",token.access_token,{
      httpOnly:true,secure:true,sameSite:"strict",path:"/",maxAge:expiry,
    });
    response.cookies.set("modelops_pkce_state","",{httpOnly:true,secure:true,sameSite:"lax",path:"/api/auth",maxAge:0});
    response.cookies.set("modelops_pkce_verifier","",{httpOnly:true,secure:true,sameSite:"lax",path:"/api/auth",maxAge:0});
    response.headers.set("Cache-Control","no-store");
    return response;
  }catch{
    return NextResponse.json({detail:"OIDC authorization could not be verified"},{status:401});
  }
}
