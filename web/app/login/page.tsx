import { headers } from "next/headers";
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

async function signUp(form: FormData) {
  "use server";
  const sb = await userClient();
  const h = await headers();
  const origin = h.get("origin") ?? `http://${h.get("host")}`;
  const { data, error } = await sb.auth.signUp({
    email: String(form.get("email")),
    password: String(form.get("password")),
    // The confirmation email links back here; /auth/callback finishes the sign-in.
    options: { emailRedirectTo: `${origin}/auth/callback` },
  });
  if (error) redirect(`/login?error=${encodeURIComponent(error.message)}`);
  if (data.session) redirect("/"); // email confirmation is turned off in this project
  redirect(`/login?notice=${encodeURIComponent("Check your email and click the confirmation link, then sign in.")}`);
}

export default async function Login({ searchParams }: { searchParams: Promise<{ error?: string; notice?: string }> }) {
  const { error, notice } = await searchParams;
  return (
    <form style={{ display: "grid", gap: 8, maxWidth: 320 }}>
      <h2>Sign in</h2>
      <label htmlFor="email">Email</label>
      <input id="email" name="email" type="email" autoComplete="email" required />
      <label htmlFor="password">Password</label>
      <input id="password" name="password" type="password" autoComplete="current-password" minLength={8} required />
      <button type="submit" formAction={signIn}>Sign in</button>
      <button type="submit" formAction={signUp}>Create account</button>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      {notice && <p style={{ color: "#0b7a3e" }}>{notice}</p>}
      <p className="muted">
        New team members: create an account, then ask a study owner to add you to the study.
        You will see no sessions until you are a member.
      </p>
    </form>
  );
}
