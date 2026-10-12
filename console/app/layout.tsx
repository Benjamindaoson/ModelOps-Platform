import type { Metadata } from "next";
import "./globals.css";
import Shell from "@/components/Shell";

export const metadata: Metadata = {
  title: "ModelOps · Model Infrastructure",
  description: "Enterprise AI model lifecycle control plane",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en"><body><Shell>{children}</Shell></body></html>
  );
}
