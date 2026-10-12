import { createHash, randomBytes, timingSafeEqual } from "node:crypto";

export type OidcMetadata = { issuer: string; authorization_endpoint: string; token_endpoint: string };

export function oidcEnabled(): boolean {
  return process.env.MODELOPS_CONSOLE_AUTH === "oidc";
}

export function getOidcEnv() {
  const issuer = process.env.MODELOPS_OIDC_ISSUER?.replace(/\/$/, "");
  const client = process.env.MODELOPS_OIDC_CLIENT_ID;
  const origin = process.env.MODELOPS_PUBLIC_ORIGIN;
  if (!issuer || !client || !origin ||
      !issuer.startsWith("https://") || !origin.startsWith("https://")) {
    throw new Error("Production OIDC needs HTTPS issuer, client ID and public origin");
  }
  return { issuer, client, origin };
}

export async function discoverOidc(): Promise<OidcMetadata> {
  const { issuer } = getOidcEnv();
  // HTTPS origins are operator configuration, not user-supplied URLs.
  const discovery = await fetch(issuer + "/.well-known/openid-configuration",
    { cache: "no-store", redirect: "error", signal: AbortSignal.timeout(5000) });
  if (!discovery.ok) throw new Error("OIDC discovery unavailable");
  const metadata = await discovery.json() as OidcMetadata;
  if (metadata.issuer !== issuer) throw new Error("OIDC issuer mismatch");
  for (const endpoint of [metadata.authorization_endpoint, metadata.token_endpoint]) {
    if (new URL(endpoint).protocol !== "https:" ||
        new URL(endpoint).origin !== new URL(issuer).origin) {
      throw new Error("OIDC endpoint origin mismatch");
    }
  }
  return metadata;
}

export function randomValue(): string { return randomBytes(32).toString("base64url"); }
export function sha256(value: string): string {
  return createHash("sha256").update(value).digest("base64url");
}
export function constantTimeEqual(a: string, b: string): boolean {
  const x = Buffer.from(a), y = Buffer.from(b);
  return x.length === y.length && timingSafeEqual(x,y);
}
