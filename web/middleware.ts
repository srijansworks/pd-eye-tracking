// Keeps the Supabase auth cookie fresh and sends signed-out users to /login.
import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

export async function middleware(req: NextRequest) {
  let res = NextResponse.next({ request: req });
  const sb = createServerClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!, {
    cookies: {
      getAll: () => req.cookies.getAll(),
      setAll: (list) => {
        list.forEach(({ name, value }) => req.cookies.set(name, value));
        res = NextResponse.next({ request: req });
        list.forEach(({ name, value, options }) => res.cookies.set(name, value, options));
      },
    },
  });
  const { data } = await sb.auth.getUser();
  const open = ["/login", "/auth/"].some((p) => req.nextUrl.pathname.startsWith(p));
  if (!data.user && !open) {
    return NextResponse.redirect(new URL("/login", req.url));
  }
  return res;
}

// API routes handle their own auth (device keys or cookies).
export const config = { matcher: ["/((?!api/|_next/|favicon.ico).*)"] };
