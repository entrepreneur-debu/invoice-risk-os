/**
 * Service-to-service authentication for calling a private Cloud Run API.
 *
 * When API_ID_TOKEN_AUDIENCE is set (the API's Cloud Run URL), the web server fetches a
 * Google-signed identity token for that audience from the metadata server (available
 * only inside Google Cloud), caches it, and sends it as a Bearer token. Cloud Run IAM
 * validates it; the API itself still authenticates users by session cookie.
 * Locally (variable unset) no header is added.
 */
const METADATA_URL =
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity";
const REFRESH_MARGIN_MS = 5 * 60 * 1000;
const TOKEN_LIFETIME_MS = 60 * 60 * 1000;

let cached: { token: string; expiresAt: number; audience: string } | null = null;

export function resetIdTokenCache(): void {
  cached = null;
}

export async function apiAuthHeaders(): Promise<Record<string, string>> {
  const audience = process.env.API_ID_TOKEN_AUDIENCE?.trim();
  if (!audience) return {};
  const now = Date.now();
  if (!cached || cached.audience !== audience || cached.expiresAt - REFRESH_MARGIN_MS <= now) {
    const response = await fetch(
      `${METADATA_URL}?audience=${encodeURIComponent(audience)}&format=full`,
      {
        headers: { "Metadata-Flavor": "Google" },
        cache: "no-store",
        signal: AbortSignal.timeout(3000),
      },
    );
    if (!response.ok) throw new Error(`identity token request failed (${response.status})`);
    cached = {
      token: (await response.text()).trim(),
      expiresAt: now + TOKEN_LIFETIME_MS,
      audience,
    };
  }
  return { Authorization: `Bearer ${cached.token}` };
}
