import { useState } from "react";
import { Link } from "react-router";
import { api, apiUrl, appUrl, nav, type S } from "../api/client";
import { useLoad } from "../hooks";
import { Problem } from "../ui";

export function SignIn() {
  const { data: providers, error } = useLoad<S["ProviderOut"][]>("auth/providers");
  const { data: guest } = useLoad<S["GuestOptionsOut"]>("auth/guest");
  const choices = providers?.filter((provider) => provider.name !== "dev"); // dev is a test login (dev-server injected), never a visible choice
  const [starting, setStarting] = useState(false);
  const [problem, setProblem] = useState<string>();

  async function tryAsGuest() {
    setStarting(true);
    setProblem(undefined);
    try {
      await api("auth/guest", { method: "POST" });
      nav.to(appUrl());
    } catch (failure) {
      setProblem((failure as Error).message);
      setStarting(false);
    }
  }

  return (
    <main className="signin">
      <div className="signin-card card">
        <div className="signin-brand">
          <div className="brand signin-logo" aria-label="KROSS: Humanitarian Dialogue Lab">
            <span className="brand-mark" aria-hidden="true">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 3v18M3 12h18" />
              </svg>
            </span>
            <div className="brand-text">
              <h1>KROSS</h1>
              <small>Humanitarian Dialogue Lab</small>
            </div>
          </div>
        </div>
        <Problem text={error ?? problem} />
        <div className="signin-actions">
          {guest?.enabled && (
            <>
              <button type="button" onClick={tryAsGuest} disabled={starting}>
                Try it now, no account
              </button>
              <p className="muted">Guests can play the curated scenarios alone, a few times a day. Sessions are deleted after a day.</p>
            </>
          )}
          {choices?.map((provider) =>
            provider.name === "google" ? (
              <a key={provider.name} className="button google-button" href={apiUrl(`auth/${provider.name}/login`)} aria-label="Sign in with Google">
                Sign in with{" "}
                <svg width="20" height="20" viewBox="0 0 24 24" fill="#fff" aria-hidden="true">
                  <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                  <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                  <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                  <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                </svg>
              </a>
            ) : (
              <a key={provider.name} className="button" href={apiUrl(`auth/${provider.name}/login`)}>
                Sign in with {provider.label}
              </a>
            ),
          )}
          {providers?.length === 0 && <p className="muted">No sign-in provider is configured. See docs/deployment.md.</p>}
        </div>
        <p className="muted signin-privacy">
          <Link to="/privacy">Privacy</Link>
        </p>
      </div>
    </main>
  );
}

