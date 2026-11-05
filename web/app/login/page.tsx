import { redirect } from "next/navigation";
import { userClient } from "@/lib/supabase/server";

async function signIn(form: FormData) {
  "use server";
  const sb = await userClient();
  const { error } = await sb.auth.signInWithPassword({
    email: String(form.get("email")), password: String(form.get("password")),
  });
  if (error) redirect(`/login?error=${encodeURIComponent(error.message)}`);
  redirect("/");
}

export default async function Login({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const { error } = await searchParams;
  return (
    <form action={signIn} style={{ display: "grid", gap: 8, maxWidth: 320 }}>
      <h2>Sign in</h2>
      <input name="email" type="email" placeholder="email" required />
      <input name="password" type="password" placeholder="password" required />
      <button type="submit">Sign in</button>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      <p className="muted">Local dev: accounts come from <code>supabase/seed.sql</code>.</p>
    </form>
  );
}
