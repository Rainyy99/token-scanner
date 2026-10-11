import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Token Security Scanner",
  description: "Token security scanner for EVM chains and Solana, run by validators on GenLayer.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
