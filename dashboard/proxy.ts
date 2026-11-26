import { NextRequest, NextResponse } from "next/server";

const STATIC_ASSET = /^\/(?:_next\/static\/|_next\/image(?:\/|$)|logo\.svg$|favicon\.ico$)/;
const encoder = new TextEncoder();

async function digest(value: string): Promise<Uint8Array> {
  return new Uint8Array(await crypto.subtle.digest("SHA-256", encoder.encode(value)));
}

function constantTimeEqual(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false;
  let difference = 0;
  for (let index = 0; index < a.length; index += 1) {
    difference |= a[index] ^ b[index];
  }
  return difference === 0;
}

function denied(status: 401 | 503, message: string): NextResponse {
  const headers = new Headers({
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
  });
  if (status === 401) {
    headers.set("WWW-Authenticate", 'Basic realm="HookFlow", charset="UTF-8"');
  }
  return new NextResponse(message, { status, headers });
}

export async function proxy(request: NextRequest): Promise<NextResponse> {
  if (STATIC_ASSET.test(request.nextUrl.pathname)) return NextResponse.next();
  const username = process.env.DASHBOARD_USERNAME || "admin";
  const password = process.env.DASHBOARD_PASSWORD;

  if (!password) {
    return denied(
      503,
      "Dashboard authentication is not configured. Set DASHBOARD_PASSWORD.",
    );
  }

  const authorization = request.headers.get("authorization");
  const match = authorization?.match(/^Basic\s+(.+)$/i);
  if (!match || match[1].length > 1024) {
    return denied(401, "Authentication required.");
  }

  let supplied: string;
  try {
    const bytes = Uint8Array.from(atob(match[1]), (character) =>
      character.charCodeAt(0),
    );
    supplied = new TextDecoder().decode(bytes);
  } catch {
    return denied(401, "Authentication required.");
  }

  const [expectedDigest, suppliedDigest] = await Promise.all([
    digest(`${username}:${password}`),
    digest(supplied),
  ]);

  if (!constantTimeEqual(expectedDigest, suppliedDigest)) {
    return denied(401, "Authentication required.");
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static/|_next/image(?:/|$)|logo\\.svg$|favicon\\.ico$).*)"],
};
