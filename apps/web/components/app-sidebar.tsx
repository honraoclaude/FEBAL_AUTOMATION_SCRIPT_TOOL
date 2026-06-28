"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  Bug,
  Crosshair,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Network,
  PlayCircle,
  Radar,
  Search,
  Target,
  Users,
  Workflow,
  type LucideIcon,
} from "lucide-react";

import { api } from "@/lib/api/client";
import { NAV_HREFS, canSee } from "@/lib/rbac";
import { RoleBadge } from "@/components/dashboards/role-badge";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";

/**
 * Sidebar contract (01-04-PLAN interfaces / 01-UI-SPEC §2): a flat list of
 * nav items; active state derived from the route. Later phases APPEND items
 * (Explorations, Graph, Scenarios, Executions, Dashboards) — only render nav
 * items that exist.
 */
type NavItem = { icon: LucideIcon; label: string; href: string };

const NAV_ITEMS: NavItem[] = [
  { icon: Crosshair, label: "Targets", href: "/targets" },
  // EXPL-01: the Live Exploration View is reached at /explore/{runId}; the nav item points at
  // /explore (active via pathname.startsWith). A run-less /explore index is out of scope this
  // phase — a thin placeholder page directs the user to start a run from Targets.
  { icon: Radar, label: "Explorations", href: "/explore" },
  // KG-02 / D-05: the Knowledge Graph browse section (Pages/Flows/Element repository).
  // Positioned after Explorations (explore → graph). Active via pathname.startsWith("/graph").
  { icon: Workflow, label: "Knowledge graph", href: "/graph" },
  // GEN-02 / 06-UI-SPEC: the Scenario Review Queue. Positioned after Knowledge graph
  // (explore → graph → scenarios). Active via pathname.startsWith("/scenarios").
  { icon: ListChecks, label: "Scenarios", href: "/scenarios" },
  // EXEC-06 / 07-UI-SPEC: the Executions section (launcher + history + live view). Positioned
  // after Scenarios (explore → graph → scenarios → executions). Active via startsWith("/executions").
  { icon: PlayCircle, label: "Executions", href: "/executions" },
  // JIRA-02 / 09-UI-SPEC: the Defects review queue. Positioned after Executions (explore → graph
  // → scenarios → executions → defects). Active via pathname.startsWith("/defects").
  { icon: Bug, label: "Defects", href: "/defects" },
];

/**
 * PLAT-04 / 10-UI-SPEC: the Phase-10 nav items APPENDED after "Defects" (the pipeline order
 * explore → graph → scenarios → executions → defects → dashboards → coverage → traceability →
 * search → users). Each is ROLE-FILTERED off the /me role via canSee(role, href) — the UX mirror
 * of the API rbac.py matrix (NEVER the security boundary). The "Dashboards" item resolves to the
 * single dashboard href the role may open (the highest-privilege dashboard it has) so the flat-list
 * nav contract is preserved; a role with NO dashboard does not render the item. Plan 06 ships the
 * coverage/traceability/search/users PAGES; this plan owns the nav for ALL of them.
 */
const DASHBOARD_HREFS_BY_PRIORITY = [
  NAV_HREFS.dashboardExecutive,
  NAV_HREFS.dashboardQa,
  NAV_HREFS.dashboardDeveloper,
] as const;

const GATED_NAV_ITEMS: NavItem[] = [
  { icon: Target, label: "Coverage", href: NAV_HREFS.coverage },
  { icon: Network, label: "Traceability", href: NAV_HREFS.traceability },
  { icon: Search, label: "Search", href: NAV_HREFS.search },
  { icon: Users, label: "Users", href: NAV_HREFS.users },
];

type Me = { id: number; email: string; role: string };

export function AppSidebar() {
  const pathname = usePathname();

  const { data: me } = useQuery({
    queryKey: ["auth", "me"],
    queryFn: () => api.get<Me>("/api/auth/me"),
    staleTime: 5 * 60 * 1000,
  });

  // The role-appropriate "Dashboards" href: the highest-privilege dashboard the role may open
  // (Executive > QA > Developer). Undefined when the role has no dashboard (then the item is hidden).
  const role = me?.role;
  const dashboardHref = DASHBOARD_HREFS_BY_PRIORITY.find((href) =>
    canSee(role, href),
  );

  // The appended Phase-10 nav, role-filtered off /me. While /me is pending (role undefined),
  // canSee returns false for every href, so NO gated nav renders yet (10-UI-SPEC: render no gated
  // nav while /me is pending).
  const gatedItems: NavItem[] = [
    ...(dashboardHref
      ? [{ icon: LayoutDashboard, label: "Dashboards", href: dashboardHref }]
      : []),
    ...GATED_NAV_ITEMS.filter((item) => canSee(role, item.href)),
  ];

  const navItems: NavItem[] = [...NAV_ITEMS, ...gatedItems];

  async function handleLogout() {
    // Immediate action, no confirmation (UI-SPEC §2; non-destructive,
    // D-04 client-side logout). Full navigation clears client state.
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      window.location.assign("/login");
    }
  }

  return (
    <Sidebar>
      <SidebarHeader>
        <div className="px-2 py-1.5 text-sm font-semibold">Autonomous QA</div>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarMenu>
            {navItems.map((item) => {
              const active = pathname.startsWith(item.href);
              return (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton
                    asChild
                    isActive={active}
                    className="data-[active=true]:border-l-2 data-[active=true]:border-primary data-[active=true]:text-primary"
                  >
                    <Link href={item.href}>
                      <item.icon aria-hidden="true" />
                      <span>{item.label}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              );
            })}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        {me ? (
          <div className="flex flex-col gap-1 px-2">
            <div className="text-xs text-muted-foreground" data-testid="user-email">
              {me.email}
            </div>
            <RoleBadge role={me.role} />
          </div>
        ) : null}
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton onClick={handleLogout}>
              <LogOut aria-hidden="true" />
              <span>Log out</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}
