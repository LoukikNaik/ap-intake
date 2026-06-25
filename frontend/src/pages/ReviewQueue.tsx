import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api";
import type { Bill } from "@/types";
import { Button, Card, StatusBadge, ConfidenceBar } from "@/components/ui";
import { money } from "@/lib";
import { Upload, RefreshCw, Lock } from "lucide-react";

const FILTERS = [
  { key: "", label: "All" },
  { key: "needs_review", label: "Needs review" },
  { key: "ready_to_approve", label: "Ready" },
  { key: "duplicate", label: "Duplicates" },
  { key: "approved", label: "Approved" },
  { key: "rejected", label: "Rejected" },
];

export default function ReviewQueue() {
  const [bills, setBills] = useState<Bill[]>([]);
  const [filter, setFilter] = useState("");
  const [uploading, setUploading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    try {
      setBills(await api.listBills(filter || undefined));
    } catch (e) {
      setMsg(String(e));
    }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 3000); // poll so processing bills appear
    return () => clearInterval(t);
  }, [filter]);

  const onUpload = async (files: FileList | null) => {
    if (!files?.length) return;
    // Snapshot now — the FileList is live and gets cleared when we reset the input below.
    const selected = Array.from(files);
    const n = selected.length;
    setUploading(true);
    setMsg(null);
    try {
      const ids: number[] = [];
      for (const f of selected) {
        const r = await api.uploadInvoice(f);
        ids.push(r.document_id);
      }
      setMsg(`Uploaded ${n} file(s). Processing…`);

      // Poll the uploaded documents until they finish, then report the real outcome
      // and clear the banner (so "Processing…" never sticks — e.g. for duplicates).
      const poll = async () => {
        const docs = await Promise.all(ids.map((id) => api.getDocument(id).catch(() => null)));
        const pending = docs.filter((d) => d && (d.status === "queued" || d.status === "processing"));
        await load();
        if (pending.length === 0) {
          setMsg(`Done — ${n} file(s) processed. Check the queue and Issues.`);
          setTimeout(() => setMsg(null), 4000);
        } else {
          setTimeout(poll, 2000);
        }
      };
      poll();
    } catch (e) {
      setMsg(`Upload failed: ${e}`);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <div className="mx-auto max-w-6xl p-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Review queue</h1>
          <p className="text-sm text-muted-foreground">
            The agent extracted these. Verify, edit, and approve or reject.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load}>
            <RefreshCw size={15} /> Refresh
          </Button>
          <Button onClick={() => fileRef.current?.click()} disabled={uploading}>
            <Upload size={15} /> {uploading ? "Uploading…" : "Upload invoice"}
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept="application/pdf"
            multiple
            hidden
            onChange={(e) => onUpload(e.target.files)}
          />
        </div>
      </div>

      {msg && (
        <div className="mb-4 rounded-md border border-border bg-white px-4 py-2 text-sm">{msg}</div>
      )}

      <div className="mb-4 flex gap-1">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`rounded-md px-3 py-1.5 text-sm ${
              filter === f.key ? "bg-primary text-primary-foreground" : "hover:bg-muted"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <Card>
        <table className="w-full text-sm">
          <thead className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-4 py-3">Vendor</th>
              <th className="px-4 py-3">Invoice #</th>
              <th className="px-4 py-3">Date</th>
              <th className="px-4 py-3 text-right">Total</th>
              <th className="px-4 py-3">Confidence</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Flags</th>
            </tr>
          </thead>
          <tbody>
            {bills.map((b) => (
              <tr key={b.id} className="border-b border-border/60 last:border-0 hover:bg-muted/40">
                <td className="px-4 py-3">
                  <Link to={`/bills/${b.id}`} className="font-medium hover:underline">
                    {b.vendor || <span className="text-muted-foreground">Unknown</span>}
                  </Link>
                  {b.is_credit_memo && (
                    <span className="ml-2 rounded bg-purple-100 px-1.5 py-0.5 text-xs text-purple-700">
                      credit memo
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-muted-foreground">{b.invoice_number || "—"}</td>
                <td className="px-4 py-3 text-muted-foreground">{b.invoice_date || "—"}</td>
                <td className="px-4 py-3 text-right tabular-nums">{money(b.total, b.currency)}</td>
                <td className="px-4 py-3">
                  <ConfidenceBar value={b.confidence} />
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <StatusBadge status={b.status} />
                    {b.locked_by && (
                      <span
                        title={`Being reviewed by ${b.locked_by}`}
                        className="inline-flex items-center gap-1 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600"
                      >
                        <Lock size={11} /> {b.locked_by}
                      </span>
                    )}
                  </div>
                </td>
                <td className="px-4 py-3">
                  {b.review_flags.length > 0 ? (
                    <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800">
                      {b.review_flags.length}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </td>
              </tr>
            ))}
            {bills.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center text-muted-foreground">
                  No bills yet. Upload an invoice to get started.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
