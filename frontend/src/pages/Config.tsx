import { useEffect, useState } from "react";
import { api } from "@/api";
import type { AgentConfig, GLAccount } from "@/types";
import { Button, Card, Badge } from "@/components/ui";
import { Plus, Save, RotateCcw, Trash2 } from "lucide-react";

export default function Config() {
  return (
    <div className="mx-auto max-w-5xl space-y-8 p-8">
      <div>
        <h1 className="text-2xl font-semibold">Agent configuration</h1>
        <p className="text-sm text-muted-foreground">
          This is what the AP manager edits — no engineer required. Changing a GL description or
          the policy changes how the agent decides. Policy edits are versioned and revertible.
        </p>
      </div>
      <AgentPolicy />
      <GLAccounts />
    </div>
  );
}

function AgentPolicy() {
  const [cfg, setCfg] = useState<AgentConfig | null>(null);
  const [versions, setVersions] = useState<AgentConfig[]>([]);
  const [instructions, setInstructions] = useState("");
  const [routing, setRouting] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  const load = async () => {
    const c = await api.getAgentConfig();
    setCfg(c);
    setInstructions(c.instructions);
    setRouting(c.routing_rules);
    setVersions(await api.listAgentConfigs());
  };
  useEffect(() => {
    load();
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      await api.saveAgentConfig({ instructions, routing_rules: routing, note });
      setNote("");
      await load();
    } finally {
      setSaving(false);
    }
  };
  const revert = async (v: number) => {
    await api.activateAgentConfig(v);
    await load();
  };

  return (
    <Card>
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="font-medium">Agent policy</div>
        {cfg && <Badge className="bg-slate-100 text-slate-600">active v{cfg.version}</Badge>}
      </div>
      <div className="space-y-4 p-5">
        <div>
          <label className="mb-1 block text-xs font-medium uppercase text-muted-foreground">
            Instructions (how the agent should decide)
          </label>
          <textarea
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            rows={8}
            className="w-full rounded-md border border-border p-3 font-mono text-sm"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium uppercase text-muted-foreground">
            Routing rules
          </label>
          <textarea
            value={routing}
            onChange={(e) => setRouting(e.target.value)}
            rows={5}
            className="w-full rounded-md border border-border p-3 font-mono text-sm"
          />
        </div>
        <div className="flex items-center gap-2">
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Change note (optional)"
            className="flex-1 rounded-md border border-border px-3 py-2 text-sm"
          />
          <Button onClick={save} disabled={saving}>
            <Save size={15} /> {saving ? "Saving…" : "Save as new version"}
          </Button>
        </div>

        <div className="border-t border-border pt-3">
          <div className="mb-2 text-xs font-medium uppercase text-muted-foreground">History</div>
          <div className="space-y-1">
            {versions.map((v) => (
              <div
                key={v.id}
                className="flex items-center justify-between rounded-md px-2 py-1.5 text-sm hover:bg-muted"
              >
                <div>
                  <span className="font-medium">v{v.version}</span>{" "}
                  <span className="text-muted-foreground">{v.note || "—"}</span>
                  {v.is_active && (
                    <Badge className="ml-2 bg-emerald-100 text-emerald-700">active</Badge>
                  )}
                </div>
                {!v.is_active && (
                  <Button variant="ghost" size="sm" onClick={() => revert(v.version)}>
                    <RotateCcw size={13} /> Revert to this
                  </Button>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
}

function GLAccounts() {
  const [accounts, setAccounts] = useState<GLAccount[]>([]);
  const [draft, setDraft] = useState<Record<number, string>>({});
  const [adding, setAdding] = useState({ code: "", name: "", description: "" });

  const load = () => api.listGL().then(setAccounts);
  useEffect(() => {
    load();
  }, []);

  const saveDesc = async (a: GLAccount) => {
    const description = draft[a.id] ?? a.description;
    await api.updateGL(a.id, {
      code: a.code,
      name: a.name,
      description,
      is_active: a.is_active,
    });
    load();
  };
  const add = async () => {
    if (!adding.code || !adding.name) return;
    await api.createGL({ ...adding, is_active: true });
    setAdding({ code: "", name: "", description: "" });
    load();
  };
  const remove = async (id: number) => {
    await api.deleteGL(id);
    load();
  };

  return (
    <Card>
      <div className="border-b border-border px-5 py-3 font-medium">
        Chart of accounts (GL codes)
        <p className="text-xs font-normal text-muted-foreground">
          The description is the agent's classification signal — editing it retunes mapping.
        </p>
      </div>
      <div className="divide-y divide-border">
        {accounts.map((a) => (
          <div key={a.id} className={`p-4 ${a.is_active ? "" : "opacity-40"}`}>
            <div className="mb-1 flex items-center justify-between">
              <div className="font-medium">
                {a.code} — {a.name}
              </div>
              <Button variant="ghost" size="sm" onClick={() => remove(a.id)}>
                <Trash2 size={13} /> Deactivate
              </Button>
            </div>
            <div className="flex gap-2">
              <textarea
                defaultValue={a.description}
                onChange={(e) => setDraft((d) => ({ ...d, [a.id]: e.target.value }))}
                rows={2}
                className="flex-1 rounded-md border border-border p-2 text-sm"
              />
              <Button variant="outline" size="sm" onClick={() => saveDesc(a)}>
                <Save size={13} /> Save
              </Button>
            </div>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap items-end gap-2 border-t border-border bg-muted/30 p-4">
        <input
          value={adding.code}
          onChange={(e) => setAdding({ ...adding, code: e.target.value })}
          placeholder="Code"
          className="w-24 rounded-md border border-border px-2 py-1.5 text-sm"
        />
        <input
          value={adding.name}
          onChange={(e) => setAdding({ ...adding, name: e.target.value })}
          placeholder="Name"
          className="w-48 rounded-md border border-border px-2 py-1.5 text-sm"
        />
        <input
          value={adding.description}
          onChange={(e) => setAdding({ ...adding, description: e.target.value })}
          placeholder="Description"
          className="flex-1 rounded-md border border-border px-2 py-1.5 text-sm"
        />
        <Button onClick={add}>
          <Plus size={15} /> Add account
        </Button>
      </div>
    </Card>
  );
}
