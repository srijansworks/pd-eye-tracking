import type { ReactNode } from "react";

export const metadata = { title: "PD multi-sensor assessment — research prototype" };

const css = `
  body { font-family: system-ui, sans-serif; margin: 0; color: #1d1d1f; background: #fafafa; }
  header { padding: 12px 24px; background: #fff; border-bottom: 1px solid #e5e5e5; display: flex; gap: 16px; align-items: baseline; }
  header a { color: inherit; text-decoration: none; font-weight: 600; }
  main { padding: 24px; max-width: 1100px; }
  table { border-collapse: collapse; width: 100%; background: #fff; font-size: 14px; }
  th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid #eee; }
  th { font-weight: 600; color: #555; }
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  .flag { display: inline-block; font-size: 11px; padding: 1px 6px; border-radius: 8px; background: #fff3cd; margin-right: 4px; }
  .muted { color: #777; font-size: 13px; }
  .banner { background: #eef4ff; border: 1px solid #cfe0ff; padding: 8px 12px; border-radius: 6px; font-size: 13px; margin-bottom: 16px; }
  a { color: #0b5cff; }
`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <style>{css}</style>
        <header>
          <a href="/">Assessment sessions</a>
          <span className="muted">Research prototype · synthetic data · not a medical device</span>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
