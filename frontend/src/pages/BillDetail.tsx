import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "@/api";
import type { Bill, GLAccount, LineItem } from "@/types";
import { Button, Card, StatusBadge, ConfidenceBar } from "@/components/ui";
import { money } from "@/lib";
import { clerkId } from "@/clerk";
import { ArrowLeft, AlertTriangle, Check, X, Save, Lock, RotateCw, RotateCcw, Info } from "lucide-react";

interface Header {
  vendor: string;
  invoice_number: string;
  invoice_date: string;
  due_date: string;
  tax: string;
  other_charges: string;
  total: string;
  is_credit_memo: boolean;
}

export default function BillDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const clerk = clerkId();
  const [bill, setBill] = useState<Bill | null>(null);
  const [gl, setGl] = useState<GLAccount[]>([]);
  const [lines, setLines] = useState<LineItem[]>([]);
  const [header, setHeader] = useState<Header | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [lockedBy, setLockedBy] = useState<string | null>(null);
  const [pdfMode, setPdfMode] = useState<"sync" | "pinned">("sync");
  const [rotations, setRotations] = useState<Record<number, number>>({}); // page -> degrees
  const rotatePage = (p: number) =>
    setRotations((r) => ({ ...r, [p]: ((r[p] || 0) + 90) % 360 }));

  const hydrate = (b: Bill) => {
    setBill(b);
    setLines(b.line_items);
    setHeader({
      vendor: b.vendor || "",
      invoice_number: b.invoice_number || "",
      invoice_date: b.invoice_date || "",
      due_date: b.due_date || "",
      tax: String(b.tax),
      other_charges: String(b.other_charges),
      total: String(b.total),
      is_credit_memo: b.is_credit_memo,
    });
    setDirty(false);
  };

  useEffect(() => {
    let released = false;
    const bid = Number(id);
    (async () => {
      const b = await api.getBill(bid);
      hydrate(b);
      api.listGL().then(setGl);
      try {
        await api.claimBill(bid, clerk); // acquire the review lease
      } catch (e) {
        const m = String(e).match(/being reviewed by ([\w-]+)/);
        setLockedBy(m ? m[1] : "another clerk");
      }
    })();
    return () => {
      // best-effort release of the lease when leaving the page
      if (!released) {
        released = true;
        api.releaseBill(bid, clerk);
      }
    };
  }, [id]);

  if (!bill || !header) return <div className="p-8 text-muted-foreground">Loading…</div>;

  const readOnly = !!lockedBy;

  const setField = (patch: Partial<Header>) => {
    setHeader((h) => ({ ...h!, ...patch }));
    setDirty(true);
  };
  const setLine = (lid: number, patch: Partial<LineItem>) => {
    setLines((prev) => prev.map((l) => (l.id === lid ? { ...l, ...patch } : l)));
    setDirty(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      await api.editBill(bill.id, {
        vendor: header.vendor,
        invoice_number: header.invoice_number,
        invoice_date: header.invoice_date,
        due_date: header.due_date,
        tax: Number(header.tax),
        other_charges: Number(header.other_charges),
        total: Number(header.total),
        is_credit_memo: header.is_credit_memo,
        line_items: lines.map((l) => ({
          id: l.id,
          gl_code: l.gl_code,
          description: l.description,
          quantity: l.quantity,
          unit_price: l.unit_price,
          amount: Number(l.amount),
          needs_review: l.needs_review,
        })),
        reviewed_by: clerk,
      });
      const b = await api.getBill(bill.id);
      hydrate(b);
    } finally {
      setSaving(false);
    }
  };

  const approve = async () => {
    if (dirty) await save();
    await api.approveBill(bill.id, clerk);
    nav("/");
  };
  const reject = async () => {
    await api.rejectBill(bill.id, clerk);
    nav("/");
  };
  const reopen = async () => {
    await api.reopenBill(bill.id, clerk);
    const b = await api.getBill(bill.id);
    hydrate(b);
  };

  const lineSum = lines.reduce((s, l) => s + (Number(l.amount) || 0), 0);
  const reconciles =
    Math.abs(lineSum + Number(header.tax) + Number(header.other_charges) - Number(header.total)) <=
    0.01;

  const pdfPages: number[] = (() => {
    try {
      const p = JSON.parse(bill.pages || "[]");
      return Array.isArray(p) && p.length ? p : [1];
    } catch {
      return [1];
    }
  })();

  return (
    <div className="mx-auto max-w-7xl p-8">
      <button
        onClick={() => nav("/")}
        className="mb-4 flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft size={15} /> Back to queue
      </button>

      <div className="mb-4 flex items-start justify-between">
        <div>
          <h1 className="flex items-center gap-3 text-2xl font-semibold">
            {header.vendor || "Unknown vendor"}
            <StatusBadge status={bill.status} />
            {header.is_credit_memo && (
              <span className="rounded bg-purple-100 px-2 py-0.5 text-sm text-purple-700">
                credit memo
              </span>
            )}
          </h1>
          <p className="text-sm text-muted-foreground">
            Invoice {header.invoice_number || "—"} · pages {bill.pages} · reviewing as{" "}
            <span className="font-medium">{clerk}</span>
          </p>
        </div>
        <div className="flex gap-2">
          {dirty && !readOnly && (
            <Button variant="outline" onClick={save} disabled={saving}>
              <Save size={15} /> {saving ? "Saving…" : "Save edits"}
            </Button>
          )}
          {bill.status === "approved" || bill.status === "rejected" ? (
            <Button variant="outline" onClick={reopen} disabled={readOnly}>
              <RotateCcw size={15} /> Reopen
            </Button>
          ) : (
            <>
              <Button variant="destructive" onClick={reject} disabled={readOnly}>
                <X size={15} /> Reject
              </Button>
              <Button variant="success" onClick={approve} disabled={readOnly}>
                <Check size={15} /> Approve
              </Button>
            </>
          )}
        </div>
      </div>

      {readOnly && (
        <Card className="mb-4 border-slate-300 bg-slate-50">
          <div className="flex items-center gap-2 p-3 text-sm text-slate-700">
            <Lock size={15} /> This bill is currently being reviewed by{" "}
            <span className="font-medium">{lockedBy}</span>. It's read-only until they finish.
          </div>
        </Card>
      )}

      {bill.review_flags.length > 0 && (
        <Card className="mb-4 border-amber-300 bg-amber-50">
          <div className="p-4">
            <div className="mb-2 flex items-center gap-2 font-medium text-amber-900">
              <AlertTriangle size={16} /> The agent flagged this for review
            </div>
            <ul className="list-disc space-y-1 pl-6 text-sm text-amber-900">
              {bill.review_flags.map((f, i) => (
                <li key={i}>{renderFlag(f)}</li>
              ))}
            </ul>
          </div>
        </Card>
      )}

      <div className="grid grid-cols-[5fr_7fr] items-start gap-6">
        {/* Left: original document.
            "sync"  = pages rendered as stacked images in normal flow → scrolls together
                       with the fields on the right.
            "pinned" = single iframe pinned in place (its own internal scroll). */}
        <Card className={pdfMode === "pinned" ? "sticky top-6 self-start overflow-hidden" : "overflow-hidden"}>
          <div className="flex items-center justify-between border-b border-border px-4 py-2">
            <span className="text-xs font-medium uppercase text-muted-foreground">
              Original document
            </span>
            <div className="flex items-center gap-1 text-xs">
              <button
                onClick={() => setPdfMode("sync")}
                className={`rounded px-2 py-0.5 ${
                  pdfMode === "sync" ? "bg-primary text-primary-foreground" : "hover:bg-muted"
                }`}
              >
                Scroll together
              </button>
              <button
                onClick={() => setPdfMode("pinned")}
                className={`rounded px-2 py-0.5 ${
                  pdfMode === "pinned" ? "bg-primary text-primary-foreground" : "hover:bg-muted"
                }`}
              >
                Pin
              </button>
            </div>
          </div>
          {pdfMode === "sync" ? (
            <div className="bg-slate-100">
              {pdfPages.map((p) => (
                <div key={p} className="group relative border-b border-border">
                  {/* small overlay control on each page */}
                  <button
                    onClick={() => rotatePage(p)}
                    title="Rotate this page 90°"
                    className="absolute right-2 top-2 z-10 flex items-center gap-1 rounded-md bg-black/55 px-2 py-1 text-xs text-white opacity-70 backdrop-blur-sm transition hover:bg-black/75 group-hover:opacity-100"
                  >
                    <RotateCw size={12} /> Rotate page {p}
                  </button>
                  <img
                    src={api.pageUrl(bill.document_id, p, rotations[p] || 0)}
                    alt={`page ${p}`}
                    className="w-full"
                  />
                </div>
              ))}
            </div>
          ) : (
            <iframe
              title="pdf"
              src={`${api.pdfUrl(bill.document_id)}#toolbar=0&navpanes=0&view=FitH`}
              className="h-[calc(100vh-140px)] w-full"
            />
          )}
        </Card>

        {/* Right: editable extracted data */}
        <div className="space-y-4">
          <Card>
            <div className="grid grid-cols-2 gap-4 p-4 text-sm">
              <EditField
                label="Vendor"
                value={header.vendor}
                onChange={(v) => setField({ vendor: v })}
                disabled={readOnly}
              />
              <EditField
                label="Invoice #"
                value={header.invoice_number}
                onChange={(v) => setField({ invoice_number: v })}
                disabled={readOnly}
              />
              <EditField
                label="Invoice date"
                value={header.invoice_date}
                onChange={(v) => setField({ invoice_date: v })}
                disabled={readOnly}
              />
              <EditField
                label="Due date"
                value={header.due_date}
                onChange={(v) => setField({ due_date: v })}
                disabled={readOnly}
              />
              <EditField
                label={`Total (${bill.currency})`}
                value={header.total}
                onChange={(v) => setField({ total: v })}
                disabled={readOnly}
              />
              <ReadField label="Currency" value={bill.currency} />
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={header.is_credit_memo}
                  disabled={readOnly}
                  onChange={(e) => setField({ is_credit_memo: e.target.checked })}
                />
                Credit memo
              </label>
              <div>
                <div className="text-xs uppercase text-muted-foreground">Confidence</div>
                <ConfidenceBar value={bill.confidence} />
              </div>
              {bill.is_duplicate && bill.duplicate_of_bill_id && (
                <div>
                  <div className="text-xs uppercase text-muted-foreground">Duplicate of</div>
                  <Link
                    to={`/bills/${bill.duplicate_of_bill_id}`}
                    className="font-medium text-blue-600 hover:underline"
                  >
                    Bill #{bill.duplicate_of_bill_id} →
                  </Link>
                </div>
              )}
              {bill.applies_to_invoice && (
                <ReadField label="Applies to invoice" value={bill.applies_to_invoice} />
              )}
            </div>
          </Card>

          {bill.agent_reasoning && (
            <Card>
              <div className="p-4">
                <div className="mb-1 text-xs uppercase text-muted-foreground">Agent reasoning</div>
                <p className="whitespace-pre-wrap text-sm text-slate-700">{bill.agent_reasoning}</p>
              </div>
            </Card>
          )}

          <Card>
            <div className="border-b border-border px-4 py-2 text-xs font-medium uppercase text-muted-foreground">
              Line items — map each to a GL account
            </div>
            <table className="w-full table-fixed text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr>
                  <th className="w-[34%] px-3 py-2">Description</th>
                  <th className="w-[9%] px-3 py-2 text-right">Qty</th>
                  <th className="w-[15%] px-3 py-2 text-right">Unit price ({bill.currency})</th>
                  <th className="w-[16%] px-3 py-2 text-right">Amount ({bill.currency})</th>
                  <th className="w-[26%] px-3 py-2">GL account</th>
                </tr>
              </thead>
              <tbody>
                {lines.map((l) => (
                  <tr
                    key={l.id}
                    className={`border-t border-border/60 ${l.needs_review ? "bg-amber-50" : ""}`}
                  >
                    <td className="px-3 py-2 align-top">
                      <div className="flex items-start gap-1.5">
                        <textarea
                          value={l.description}
                          disabled={readOnly}
                          rows={2}
                          onChange={(e) => setLine(l.id, { description: e.target.value })}
                          className="w-full resize-y rounded border border-border bg-white px-1.5 py-1 disabled:bg-muted"
                        />
                        {l.reasoning && (
                          <span className="group/rsn relative inline-flex">
                            <Info
                              size={14}
                              className="shrink-0 cursor-help text-muted-foreground hover:text-foreground"
                              aria-label="Why this GL code"
                            />
                            {/* Floating card on hover — overlays, doesn't shift layout */}
                            <span className="pointer-events-none absolute right-0 top-6 z-30 hidden w-72 rounded-md border border-border bg-white p-2.5 text-xs leading-relaxed text-slate-700 shadow-lg group-hover/rsn:block">
                              <span className="mb-1 block font-medium text-slate-500">
                                Agent reasoning
                              </span>
                              {l.reasoning}
                            </span>
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2 align-top text-right">
                      <input
                        value={l.quantity ?? ""}
                        disabled={readOnly}
                        onChange={(e) =>
                          setLine(l.id, {
                            quantity: e.target.value === "" ? null : Number(e.target.value),
                          })
                        }
                        className="w-full rounded border border-border bg-white px-1.5 py-1 text-right tabular-nums disabled:bg-muted"
                      />
                    </td>
                    <td className="px-3 py-2 align-top text-right">
                      <input
                        value={l.unit_price ?? ""}
                        disabled={readOnly}
                        onChange={(e) =>
                          setLine(l.id, {
                            unit_price: e.target.value === "" ? null : Number(e.target.value),
                          })
                        }
                        className="w-full rounded border border-border bg-white px-1.5 py-1 text-right tabular-nums disabled:bg-muted"
                      />
                    </td>
                    <td className="px-3 py-2 align-top text-right">
                      <input
                        value={String(l.amount)}
                        disabled={readOnly}
                        onChange={(e) => setLine(l.id, { amount: Number(e.target.value) || 0 })}
                        className="w-full rounded border border-border bg-white px-1.5 py-1 text-right tabular-nums disabled:bg-muted"
                      />
                    </td>
                    <td className="px-3 py-2 align-top">
                      <select
                        value={l.gl_code || ""}
                        disabled={readOnly}
                        onChange={(e) =>
                          setLine(l.id, {
                            gl_code: e.target.value || null,
                            // Clearing the code sends the line back to "needs review";
                            // picking a code clears the flag.
                            needs_review: e.target.value ? false : true,
                          })
                        }
                        className={`w-full rounded border px-2 py-1 text-sm ${
                          l.gl_code ? "border-border" : "border-amber-400 bg-amber-50"
                        }`}
                      >
                        <option value="">⚠ Needs review — pick a code</option>
                        {gl
                          .filter((g) => g.is_active)
                          .map((g) => (
                            <option key={g.code} value={g.code}>
                              {g.code} — {g.name}
                            </option>
                          ))}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot className="text-sm">
                <tr className="border-t border-border">
                  <td colSpan={3} className="px-3 py-1.5 text-right text-muted-foreground">
                    Line items
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{money(lineSum)}</td>
                  <td />
                </tr>
                <tr>
                  <td colSpan={3} className="px-3 py-1.5 text-right text-muted-foreground">
                    Tax
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    <input
                      value={header.tax}
                      disabled={readOnly}
                      onChange={(e) => setField({ tax: e.target.value })}
                      className="w-24 rounded border border-border px-1 py-0.5 text-right tabular-nums disabled:bg-muted"
                    />
                  </td>
                  <td />
                </tr>
                <tr>
                  <td colSpan={3} className="px-3 py-1.5 text-right text-muted-foreground">
                    Other charges
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    <input
                      value={header.other_charges}
                      disabled={readOnly}
                      onChange={(e) => setField({ other_charges: e.target.value })}
                      className="w-24 rounded border border-border px-1 py-0.5 text-right tabular-nums disabled:bg-muted"
                    />
                  </td>
                  <td />
                </tr>
                <tr className="border-t border-border font-medium">
                  <td colSpan={3} className="px-3 py-2 text-right">
                    Total
                    {!reconciles && <span className="ml-2 text-red-600">⚠ doesn't reconcile</span>}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{money(Number(header.total))}</td>
                  <td />
                </tr>
              </tfoot>
            </table>
          </Card>
        </div>
      </div>
    </div>
  );
}

// Linkify a "bill #N" reference inside a flag string so the reviewer can jump to it.
function renderFlag(flag: string) {
  const m = flag.match(/bill #(\d+)/i);
  if (!m) return flag;
  const id = m[1];
  const [before, after] = flag.split(m[0]);
  return (
    <>
      {before}
      <Link to={`/bills/${id}`} className="font-medium text-blue-700 underline">
        bill #{id}
      </Link>
      {after}
    </>
  );
}

function EditField({
  label,
  value,
  onChange,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <div>
      <div className="text-xs uppercase text-muted-foreground">{label}</div>
      <input
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded border border-border px-2 py-1 font-medium disabled:bg-muted disabled:text-muted-foreground"
      />
    </div>
  );
}

function ReadField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs uppercase text-muted-foreground">{label}</div>
      <div className="font-medium">{value}</div>
    </div>
  );
}
