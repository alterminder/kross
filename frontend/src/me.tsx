import { createContext, useContext, useEffect, type ReactNode } from "react";
import { useNavigate } from "react-router";
import type { S } from "./api/client";
import { useLoad } from "./hooks";
import { Problem } from "./ui";

export const MeContext = createContext<S["MeOut"] | null>(null);

export function useMe(): S["MeOut"] {
  const me = useContext(MeContext);
  if (!me) throw new Error("useMe outside RequireMe");
  return me;
}

/** Route guards, matching the nav rules in Layout: the page (and its requests) never mounts without the role. */
export function ForOrgAdmins({ children }: { children: ReactNode }) {
  const org = useMe().active_org;
  if (org.role !== "admin" || org.personal) return <p>This page is for organisation admins.</p>;
  return children;
}

export function ForSuperadmins({ children }: { children: ReactNode }) {
  if (!useMe().is_superadmin) return <p>This page is for platform admins.</p>;
  return children;
}

const INVITE = "nlab.invite";

/** An invite link opened before sign-in: keep its token for after the sign-in round trip. */
export function rememberInvite(): void {
  try {
    if (location.pathname.endsWith("/invite") && location.hash.length > 1) sessionStorage.setItem(INVITE, location.hash.slice(1));
  } catch {
    // storage blocked: the user opens the link again after signing in
  }
}

function takeInvite(): string | null {
  try {
    const token = sessionStorage.getItem(INVITE);
    sessionStorage.removeItem(INVITE);
    return token;
  } catch {
    return null;
  }
}

/** Loads the signed-in user for the pages inside; a 401 sends the browser to the sign-in page (see api()). */
export function RequireMe({ children }: { children: ReactNode }) {
  const { data: me, error } = useLoad<S["MeOut"]>("me");
  const navigate = useNavigate();
  useEffect(() => {
    const token = me ? takeInvite() : null;
    if (token) navigate(`/invite#${token}`, { replace: true });
  }, [me, navigate]);
  if (error) return <Problem text={error} />;
  if (!me) return <p className="loading">Loading…</p>;
  return <MeContext.Provider value={me}>{children}</MeContext.Provider>;
}
