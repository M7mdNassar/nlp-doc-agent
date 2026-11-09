import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Folio — A little more clarity",
  description:
    "A thoughtful workspace for your documents. Ask questions, compare ideas, and trace every answer back to its source.",
  icons: { icon: "/mark.svg" },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
