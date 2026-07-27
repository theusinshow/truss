import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Truss Agent",
  description: "Revisao grafica local de projetos estruturais em PDF"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
