import { NextRequest, NextResponse } from "next/server";
import { ADMIN_SESSION_COOKIE, verifyAdminSessionToken } from "@/lib/adminAuth";

const GATED_API_ROUTES = new Set(["/api/run", "/api/purge-source", "/api/purge-off-scope-jobs"]);

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (pathname === "/admin/login") {
    return NextResponse.next();
  }

  const isAdminPage = pathname === "/admin" || pathname.startsWith("/admin/");
  const isGatedApiRoute = GATED_API_ROUTES.has(pathname);
  if (!isAdminPage && !isGatedApiRoute) {
    return NextResponse.next();
  }

  const token = request.cookies.get(ADMIN_SESSION_COOKIE)?.value;
  const authorized = await verifyAdminSessionToken(token);
  if (authorized) {
    return NextResponse.next();
  }

  if (isGatedApiRoute) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const loginUrl = new URL("/admin/login", request.url);
  loginUrl.searchParams.set("next", pathname);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/admin", "/admin/:path*", "/api/run", "/api/purge-source", "/api/purge-off-scope-jobs"],
};
