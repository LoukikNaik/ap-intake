import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import App from "./App";
import ReviewQueue from "./pages/ReviewQueue";
import BillDetail from "./pages/BillDetail";
import Issues from "./pages/Issues";
import Config from "./pages/Config";
import "./index.css";

// Clean URLs (BrowserRouter). Deep links work on GitHub Pages via the 404.html copy created
// in the deploy workflow (Pages serves 404.html for unknown paths → the SPA boots and routes).
// basename comes from Vite's base ("/" with a custom domain, "/<repo>/" for a project site).
const router = createBrowserRouter(
  [
    {
      path: "/",
      element: <App />,
      children: [
        { index: true, element: <ReviewQueue /> },
        { path: "bills/:id", element: <BillDetail /> },
        { path: "issues", element: <Issues /> },
        { path: "config", element: <Config /> },
      ],
    },
  ],
  { basename: import.meta.env.BASE_URL }
);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>
);
