import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import "@fontsource/dm-sans/400.css";
import "@fontsource/dm-sans/700.css";
import "@fontsource-variable/google-sans-flex";
import "./index.css";
import { rememberInvite } from "./me";
import { routes } from "./routes";

rememberInvite();
const basename = new URL(document.baseURI).pathname.replace(/\/$/, ""); // the mount path, from <base href>

const router = createBrowserRouter(routes, { basename: basename || undefined });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
