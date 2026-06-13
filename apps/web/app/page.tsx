import { redirect } from "next/navigation";

/**
 * Root route: the app's only home is /targets. proxy.ts has already
 * redirected unauthenticated visitors to /login before this renders.
 */
export default function Home() {
  redirect("/targets");
}
