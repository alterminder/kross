import type { RouteObject } from "react-router";
import { ForOrgAdmins, ForSuperadmins, RequireMe } from "./me";
import { Account } from "./pages/Account";
import { Builder } from "./pages/Builder";
import { Debrief } from "./pages/Debrief";
import { ScenarioEditor } from "./pages/Editor";
import { Invite } from "./pages/Invite";
import { KnowledgeLibrary } from "./pages/KnowledgeLibrary";
import { Layout } from "./pages/Layout";
import { Library } from "./pages/Library";
import { OrgPage } from "./pages/Org";
import { Play } from "./pages/Play";
import { Privacy } from "./pages/Privacy";
import { RulesPage } from "./pages/Rules";
import { ScenarioPage } from "./pages/Scenario";
import { SignIn } from "./pages/SignIn";
import { UsagePage } from "./pages/Usage";
import { Watch } from "./pages/Watch";

/** The app's routes, guards included: main.tsx mounts them in the browser, the guard tests in a memory router. */
export const routes: RouteObject[] = [
  { path: "/signin", element: <SignIn /> },
  { path: "/privacy", element: <Privacy /> }, // public: Google checks this URL anonymously
  {
    element: (
      <RequireMe>
        <Layout />
      </RequireMe>
    ),
    children: [
      { path: "/", element: <Library /> },
      { path: "/knowledge", element: <KnowledgeLibrary /> },
      { path: "/knowledge/:id", element: <KnowledgeLibrary /> },
      { path: "/invite", element: <Invite /> },
      { path: "/scenarios/new", element: <Builder /> },
      { path: "/scenarios/:id", element: <ScenarioPage /> },
      { path: "/scenarios/:id/edit", element: <ScenarioEditor /> },
      { path: "/play/:id", element: <Play /> },
      { path: "/sessions/:id/debrief", element: <Debrief /> },
      { path: "/sessions/:id/watch", element: <Watch /> },
      {
        path: "/org",
        element: (
          <ForOrgAdmins>
            <OrgPage />
          </ForOrgAdmins>
        ),
      },
      {
        path: "/rules",
        element: (
          <ForOrgAdmins>
            <RulesPage />
          </ForOrgAdmins>
        ),
      },
      {
        path: "/usage",
        element: (
          <ForSuperadmins>
            <UsagePage />
          </ForSuperadmins>
        ),
      },
      { path: "/account", element: <Account /> },
      { path: "*", element: <p>Page not found.</p> },
    ],
  },
];
