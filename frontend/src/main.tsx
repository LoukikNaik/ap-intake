import React from "react";
import ReactDOM from "react-dom/client";
import { createHashRouter, RouterProvider } from "react-router-dom";
import App from "./App";
import ReviewQueue from "./pages/ReviewQueue";
import BillDetail from "./pages/BillDetail";
import Issues from "./pages/Issues";
import Config from "./pages/Config";
import "./index.css";

// HashRouter keeps client-side routes (e.g. #/bills/1) working on GitHub Pages, which
// has no SPA fallback — direct loads/refreshes of deep links won't 404.
const router = createHashRouter([
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
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>
);
