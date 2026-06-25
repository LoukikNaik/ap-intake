import { useEffect, useState } from "react";
import { api } from "@/api";
import type { Issue } from "@/types";
import { Button, Card } from "@/components/ui";
import { AlertTriangle, Check } from "lucide-react";

export default function Issues() {
  const [issues, setIssues] = useState<Issue[]>([]);

  const load = () => api.listIssues().then(setIssues);
  useEffect(() => {
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, []);

  const resolve = async (id: number) => {
    await api.resolveIssue(id);
    load();
  };

  return (
    <div className="mx-auto max-w-4xl p-8">
      <h1 className="text-2xl font-semibold">Issues</h1>
      <p className="mb-6 text-sm text-muted-foreground">
        Documents the agent decided were not invoices, plus processing failures — with the agent's
        reasoning attached.
      </p>

      <div className="space-y-3">
        {issues.map((i) => (
          <Card key={i.id} className={i.resolved ? "opacity-50" : ""}>
            <div className="flex items-start justify-between p-4">
              <div className="flex gap-3">
                <AlertTriangle
                  size={18}
                  className={i.kind === "error" ? "text-red-500" : "text-amber-500"}
                />
                <div>
                  <div className="text-sm font-medium capitalize">
                    {i.kind.replace(/_/g, " ")} · document #{i.document_id}
                  </div>
                  <p className="mt-1 text-sm text-slate-700">{i.reason}</p>
                  <a
                    href={api.pdfUrl(i.document_id)}
                    target="_blank"
                    className="mt-1 inline-block text-xs text-blue-600 hover:underline"
                  >
                    View document
                  </a>
                </div>
              </div>
              {!i.resolved && (
                <Button variant="outline" size="sm" onClick={() => resolve(i.id)}>
                  <Check size={14} /> Resolve
                </Button>
              )}
            </div>
          </Card>
        ))}
        {issues.length === 0 && (
          <Card>
            <div className="p-12 text-center text-muted-foreground">No issues. 🎉</div>
          </Card>
        )}
      </div>
    </div>
  );
}
