import type { Metadata } from "next";
import localFont from "next/font/local";
import Link from "next/link";
import "./globals.css";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: "ITS-BO Test Platform",
  description: "C-ITS Network Test Platform – ITS Back Office",
};

const NAV_ITEMS = [
  { href: "/test",      label: "Test Panel",  icon: "⚡" },
  { href: "/results",   label: "Results",     icon: "📊" },
  { href: "/analytics", label: "Analytics",   icon: "📈" },
];

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-lab-bg text-lab-text`}
      >
        <div className="flex h-screen overflow-hidden">
          {/* ── Sidebar ── */}
          <aside className="w-[220px] flex-shrink-0 bg-lab-surface border-r border-lab-border flex flex-col">
            {/* Logo */}
            <div className="px-5 py-5 border-b border-lab-border">
              <Link href="/test" className="flex items-center gap-2.5 group">
                <div className="w-8 h-8 rounded-lg bg-primary/20 flex items-center justify-center text-primary font-bold text-sm group-hover:bg-primary group-hover:text-white transition-all">
                  BO
                </div>
                <div>
                  <p className="text-sm font-semibold text-lab-text leading-tight">ITS-BO</p>
                  <p className="text-[10px] text-lab-muted leading-tight">Test Platform</p>
                </div>
              </Link>
            </div>

            {/* Nav links */}
            <nav className="flex-1 px-3 py-4 space-y-1">
              {NAV_ITEMS.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-lab-muted hover:text-lab-text hover:bg-lab-card transition-all group"
                >
                  <span className="text-base">{item.icon}</span>
                  <span>{item.label}</span>
                </Link>
              ))}
            </nav>

            {/* Footer / system indicator */}
            <div className="px-4 py-4 border-t border-lab-border">
              <div className="flex items-center gap-2 text-xs text-lab-muted">
                <span className="status-dot status-dot-idle" id="system-status-dot" />
                <span>Backend</span>
              </div>
              <p className="text-[10px] text-lab-muted/60 mt-1">v1.0.0 · :8000</p>
            </div>
          </aside>

          {/* ── Main content ── */}
          <main className="flex-1 overflow-y-auto">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
