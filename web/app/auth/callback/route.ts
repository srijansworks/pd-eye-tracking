/**
 * GET /auth/callback?code=… — the link in Supabase's confirmation email lands here.
 * Exchanges the one-time code for a session cookie, then opens the dashboard.
 */
import { NextResponse } from "next/server";
import { userClient } from "@/lib/supabase/server";

export async function GET(req: Request) {
  const url = new URL(req.url);
  const code = url.searchParams.get("code");
  if (code) {
    const sb = await userClient();
    const { error } = await sb.auth.exchangeCodeForSession(code);
    if (!error) return NextResponse.redirect(new URL("/", url.origin));
    return NextResponse.redirect(new URL(`/login?error=${encodeURIComponent(error.message)}`, url.origin));
  }
  const err = url.searchParams.get("error_description") ?? "Missing confirmation code";
  return NextResponse.redirect(new URL(`/login?error=${encodeURIComponent(err)}`, url.origin));
}
