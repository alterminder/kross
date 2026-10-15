import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import { SPENT, api, appUrl, nav, type S } from "../api/client";
import { useLoad } from "../hooks";
import { useMe } from "../me";

/** The header's daily personal token allowance: compact, read-only, one request per refresh.
 * Unlimited (null limit) is never shown as 0%. Refreshes when navigation or a model request finishes. */
function TokenBar() {
  // shortcut: async per-turn evaluator charges appear at the next action/navigation refresh (accepted: server limits always use the live ledger, and the Debrief terminal refresh covers final charges); add a scoring-completion signal if immediate accounting is required
  const { data, reload } = useLoad<S["AllowanceOut"]>("me/allowance");
  const path = useLocation().pathname;
  const seen = useRef(path);
  useEffect(() => {
    if (seen.current === path) return; // useLoad already fetched on mount
    seen.current = path;
    void reload();
  }, [path, reload]);
  useEffect(() => {
    const refresh = () => void reload();
    window.addEventListener(SPENT, refresh);
    return () => window.removeEventListener(SPENT, refresh);
  }, [reload]);
  if (!data) return null; // no allowance (or not signed in): nothing to show
  const { used_tokens, limit_tokens, remaining_percent } = data;
  const unlimited = limit_tokens === null || remaining_percent === null;
  const left = Math.round(remaining_percent ?? 0); // a compact whole percent; the meter keeps the real value
  return (
    <p className="token-bar" title={unlimited ? "Unlimited token use" : `${used_tokens} of ${limit_tokens} tokens used today`}>
      {unlimited ? (
        <span>Daily limit: unlimited</span>
      ) : (
        <>
          <span>Daily limit</span>
          <meter min={0} max={100} low={25} value={remaining_percent} aria-label={`${left}% of today's tokens left`} />
          <span>{left}% left</span>
        </>
      )}
    </p>
  );
}

export function Layout() {
  const me = useMe();
  const org = me.active_org;
  const adminOfRealOrg = org.role === "admin" && !org.personal;
  const profile = useRef<HTMLDetailsElement>(null);
  const switcher = useRef<HTMLDetailsElement>(null);
  const [switcherOpen, setSwitcherOpen] = useState(false);
  const [compact, setCompact] = useState(false);
  const header = useRef<HTMLElement>(null);
  const expanded = useRef(0);
  const [reserve, setReserve] = useState(0);

  useEffect(() => {
    function onScroll() {
      const bar = header.current;
      if (bar && !bar.classList.contains("compact")) expanded.current = bar.offsetHeight; // fresh before every shrink
      const y = window.scrollY;
      setCompact((was) => (was ? y > 4 : y > 40)); // hysteresis: the shrinking header cannot make it flicker
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // The compact bar keeps the height it gave up as space below itself, so the page never moves under the pointer.
  // ponytail: a window resize while compact can leave the reserve a few px off until the bar next expands.
  useLayoutEffect(() => {
    setReserve(compact && header.current ? Math.max(0, expanded.current - header.current.offsetHeight) : 0);
  }, [compact]);

  function closeProfile() {
    if (profile.current) profile.current.open = false;
  }

  useEffect(() => {
    function dismiss(event: PointerEvent | KeyboardEvent) {
      for (const menu of [profile.current, switcher.current]) {
        if (!menu?.open) continue;
        if (event instanceof KeyboardEvent) {
          if (event.key !== "Escape") continue;
          menu.open = false;
          menu.querySelector("summary")?.focus();
        } else if (!menu.contains(event.target as Node)) {
          menu.open = false;
        }
      }
    }
    document.addEventListener("pointerdown", dismiss);
    document.addEventListener("keydown", dismiss);
    return () => {
      document.removeEventListener("pointerdown", dismiss);
      document.removeEventListener("keydown", dismiss);
    };
  }, []);

  async function switchOrg(orgId: string) {
    if (orgId === org.id) return; // choosing the active org just closes the popup
    await api("orgs/active", { method: "POST", body: { org_id: orgId } });
    nav.to(appUrl()); // a full reload: every page now reads the new org
  }

  function chooseOrg(orgId: string) {
    if (switcher.current) switcher.current.open = false;
    void switchOrg(orgId);
  }

  async function signOut() {
    closeProfile();
    await api("auth/logout", { method: "POST" });
    nav.to(appUrl("signin"));
  }

  return (
    <>
      <header ref={header} className={compact ? "topbar compact" : "topbar"} style={{ marginBottom: reserve }}>
        <Link to="/" className="brand" aria-label="KROSS: back to the main page">
          <span className="brand-mark" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 3v18M3 12h18" />
            </svg>
          </span>
          <div>
            <strong>KROSS</strong>
            <small>Humanitarian Dialogue Lab</small>
          </div>
        </Link>

        <div className="top-actions">
          <TokenBar />
          <nav>
            <NavLink to="/" end>
              Scenarios
            </NavLink>
            <NavLink to="/knowledge">Library</NavLink>
            {adminOfRealOrg && (
              <>
                <NavLink to="/org">Organisation</NavLink>
                <NavLink to="/rules">Rules</NavLink>
              </>
            )}
            {me.is_superadmin && <NavLink to="/usage">Usage</NavLink>}
          </nav>
          {me.orgs.length > 1 && (
            <details
              className="framework-dropdown org-switcher"
              ref={switcher}
              onToggle={(event) => setSwitcherOpen(event.currentTarget.open)}
            >
              <summary
                className="filter-btn framework-dropdown-toggle org-switcher-toggle"
                role="button"
                aria-label={`Organisation: ${org.personal ? "Personal" : org.name}`}
                aria-haspopup="true"
                aria-expanded={switcherOpen}
              >
                <span className="org-switcher-name">{org.personal ? "Personal" : org.name}</span> ▾
              </summary>
              <div className="framework-dropdown-menu" role="group" aria-label="Choose organisation">
                {me.orgs.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className="framework-option org-switcher-option"
                    aria-current={item.id === org.id ? "true" : undefined}
                    onClick={() => chooseOrg(item.id)}
                  >
                    <span>{item.personal ? "Personal" : item.name}</span>{" "}
                    {!item.personal && (
                      <span className="framework-option-count">{item.role === "admin" ? "Admin" : "Member"}</span>
                    )}
                  </button>
                ))}
              </div>
            </details>
          )}
          <details className="profile-menu" ref={profile}>
            <summary className="profile-trigger" role="button" aria-label="Profile menu">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <circle cx="12" cy="8" r="4" />
                <path d="M5 21v-2a7 7 0 0 1 14 0v2" />
              </svg>
            </summary>
            <div className="profile-dropdown">
              <p className="profile-identity">{me.is_guest ? "Guest" : me.display_name}</p>
              {me.is_guest ? (
                <Link to="/signin" onClick={closeProfile}>Sign in</Link>
              ) : (
                <Link to="/account" onClick={closeProfile}>My account</Link>
              )}
              <Link to="/privacy" onClick={closeProfile}>Privacy</Link>
              <button type="button" onClick={signOut}>
                {me.is_guest ? "Leave" : "Sign out"}
              </button>
            </div>
          </details>
        </div>
      </header>
      {me.is_guest && (
        <p className="guest-banner" role="note">
          You are playing as a guest. Your sessions are deleted after a day; sign in to keep them and to build your own scenarios.
        </p>
      )}
      <main>
        <Outlet />
      </main>
    </>
  );
}
