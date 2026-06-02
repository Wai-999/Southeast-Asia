import type { Metadata } from "next";
import "@/styles/globals.css";
import Sidebar from "@/components/layout/Sidebar";

export const metadata: Metadata = {
  title: "SEA Change Intelligence Dashboard",
  description: "Southeast Asia Economic & Political Change Dashboard — 5 countries · 8 indicators",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <div className="flex h-screen overflow-hidden bg-white">
          <Sidebar />
          <main className="flex-1 overflow-y-auto bg-slate-50/50">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
