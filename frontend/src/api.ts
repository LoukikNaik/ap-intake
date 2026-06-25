import type { AgentConfig, Bill, GLAccount, Issue } from "./types";

const BASE = (import.meta as any).env?.VITE_API_URL || "http://localhost:8000";

// Sent on every request so ngrok's free-tier browser-warning interstitial is skipped
// (otherwise it returns HTML and breaks JSON parsing). Harmless when not behind ngrok.
const COMMON_HEADERS = { "ngrok-skip-browser-warning": "true" };

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: { "Content-Type": "application/json", ...COMMON_HEADERS, ...(opts?.headers || {}) },
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  base: BASE,

  uploadInvoice: async (file: File): Promise<{ document_id: number; status: string }> => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${BASE}/invoices?source=ui`, {
      method: "POST",
      body: fd,
      headers: { ...COMMON_HEADERS },
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  getDocument: (id: number) =>
    req<{ id: number; status: string; filename: string }>(`/documents/${id}`),

  listBills: (status?: string) =>
    req<Bill[]>(`/bills${status ? `?status=${status}` : ""}`),
  getBill: (id: number) => req<Bill>(`/bills/${id}`),
  editBill: (id: number, body: any) =>
    req<Bill>(`/bills/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  approveBill: (id: number, clerk: string) =>
    req<Bill>(`/bills/${id}/approve?reviewed_by=${encodeURIComponent(clerk)}`, { method: "POST" }),
  rejectBill: (id: number, clerk: string) =>
    req<Bill>(`/bills/${id}/reject?reviewed_by=${encodeURIComponent(clerk)}`, { method: "POST" }),
  claimBill: (id: number, clerk: string) =>
    req<Bill>(`/bills/${id}/claim?clerk=${encodeURIComponent(clerk)}`, { method: "POST" }),
  releaseBill: (id: number, clerk: string) =>
    fetch(`${BASE}/bills/${id}/release?clerk=${encodeURIComponent(clerk)}`, {
      method: "POST",
      headers: { ...COMMON_HEADERS },
    }),

  listIssues: () => req<Issue[]>(`/issues`),
  resolveIssue: (id: number) => req<Issue>(`/issues/${id}/resolve`, { method: "POST" }),

  listGL: () => req<GLAccount[]>(`/config/gl-accounts`),
  createGL: (body: any) =>
    req<GLAccount>(`/config/gl-accounts`, { method: "POST", body: JSON.stringify(body) }),
  updateGL: (id: number, body: any) =>
    req<GLAccount>(`/config/gl-accounts/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteGL: (id: number) => req<void>(`/config/gl-accounts/${id}`, { method: "DELETE" }),

  getAgentConfig: () => req<AgentConfig>(`/config/agent`),
  listAgentConfigs: () => req<AgentConfig[]>(`/config/agent/versions`),
  saveAgentConfig: (body: any) =>
    req<AgentConfig>(`/config/agent`, { method: "PUT", body: JSON.stringify(body) }),
  activateAgentConfig: (version: number) =>
    req<AgentConfig>(`/config/agent/${version}/activate`, { method: "POST" }),

  pdfUrl: (documentId: number) => `${BASE}/documents/${documentId}/pdf`,
  pageUrl: (documentId: number, page: number, rotate = 0) =>
    `${BASE}/documents/${documentId}/page/${page}.png${rotate ? `?rotate=${rotate}` : ""}`,
};
