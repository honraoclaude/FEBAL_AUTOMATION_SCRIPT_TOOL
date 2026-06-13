"use client";

import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AppSidebar } from "@/components/app-sidebar";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { Toaster } from "@/components/ui/sonner";

export default function DashboardLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // One QueryClient per browser tab, stable across re-renders.
  const [queryClient] = useState(() => new QueryClient());

  return (
    <QueryClientProvider client={queryClient}>
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset>
          {/* lg (24px) content padding per 01-UI-SPEC §2 */}
          <main className="flex-1 p-6">{children}</main>
        </SidebarInset>
        {/* Success-only toasts, bottom-right (UI-SPEC interaction defaults). */}
        <Toaster theme="dark" position="bottom-right" />
      </SidebarProvider>
    </QueryClientProvider>
  );
}
