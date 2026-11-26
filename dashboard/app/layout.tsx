import type { Metadata } from "next";
import "./globals.css";
import { Navigation } from "@/components/Navigation";

export const metadata: Metadata = {
  title: {
    default: "HookFlow — Webhook operations",
    template: "%s · HookFlow",
  },
  description:
    "Inspect webhook deliveries, manage endpoints and respond to failures in HookFlow.",
  applicationName: "HookFlow",
  icons: {
    icon: [{ url: "/logo.svg", type: "image/svg+xml" }],
    apple: [{ url: "/logo.svg" }],
  },
  robots: { index: false, follow: false },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const environment =
    process.env.HOOKFLOW_ENVIRONMENT === "production" ? "production" : "development";

  return (
    <html lang="en">
      <body>
        <a href="#main-content" className="skip-link">
          Skip to content
        </a>
        <Navigation environment={environment} />
        <main
          id="main-content"
          className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 sm:py-10 lg:px-8"
        >
          {children}
        </main>
        <footer className="mx-auto w-full max-w-[1440px] px-4 pb-8 text-xs text-slate-600 sm:px-6 lg:px-8">
          HookFlow operator console · Server-side credentials only
        </footer>
      </body>
    </html>
  );
}
