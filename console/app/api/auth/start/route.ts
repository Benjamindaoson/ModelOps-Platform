import { NextRequest, NextResponse } from "next/server";
import { discoverOidc, getOidcEnv, randomValue, sha256, oidcEnabled } from "@/lib/oidc";

export async function GET(req: NextRequest) {
  if (!oidcEnabled()) return NextResponse.json({ detail: "OIDC is not configured" }, {status:404});
  try {
    const { client, origin } = getOidcEnv();
    const metadata = await discoverOidc();
    const state = randomValue();
    const verifier = randomValue();
    const challenge = sha256(verifier);
    const redirectUri = new URL("/api/auth/callback", origin);
    const uri = new URL(metadata.authorization_endpoint);
    uri.searchParams.set("response_type", "code");
    uri.searchParams.set("client_id", client);
    uri.searchParams.set("redirect_uri", redirectUri.toString());
    uri.searchParams.set("scope", "openid profile");
    uri.searchParams.set("state", state);
    uri.searchParams.set("code_challenge", challenge);
    uri.searchParams.set("code_challenge_method", "S256");
    const response = NextResponse.redirect(uri);
    for(const [name,value] of [["modelops_pkce_state",state],["modelops_pkce_verifier",verifier]]) {
      response.cookies.set(name,value,{httpOnly:true,secure:true,sameSite:"lax",path:"/api/auth",maxAge:300});
    }
    response.headers.set("Cache-Control","no-store");
    return response;
  } catch {
    return NextResponse.json({detail:"OIDC identity provider unavailable or invalid configuration"},{status:503});
  }
}
