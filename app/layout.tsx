import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Token Security Scanner",
  description: "AI-powered token contract security scanner on GenLayer.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
