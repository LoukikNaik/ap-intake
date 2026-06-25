import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { cn } from "./lib";
import { FileText, Inbox, Settings, AlertTriangle, User } from "lucide-react";
import { getClerk, setClerk, clearClerk } from "./clerk";
import { Button, Card } from "./components/ui";

function NameGate({ onSet }: { onSet: () => void }) {
  const [name, setName] = useState("");
  return (
    <div className="flex h-screen items-center justify-center bg-muted">
      <Card className="w-[380px] p-6">
        <h1 className="text-lg font-semibold">Welcome to Lonestar AP</h1>
        <p className="mb-4 text-sm text-muted-foreground">
          Enter your name to start reviewing. It's stamped on each invoice you review so two
          clerks don't work the same one.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim()) {
              setClerk(name);
              onSet();
            }
          }}
          className="flex gap-2"
        >
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Maria Lopez"
            className="flex-1 rounded-md border border-border px-3 py-2 text-sm"
          />
          <Button type="submit" disabled={!name.trim()}>
            Continue
          </Button>
        </form>
      </Card>
    </div>
  );
}

function Nav({ clerk, onSwitch }: { clerk: string; onSwitch: () => void }) {
  const link = (to: string, label: string, Icon: any, end = false) => (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition",
          isActive ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"
        )
      }
    >
      <Icon size={16} />
      {label}
    </NavLink>
  );
  return (
    <aside className="flex w-56 flex-col gap-1 border-r border-border bg-white p-4">
      <div className="mb-4 px-2">
        <div className="text-lg font-semibold">Lonestar AP</div>
        <div className="text-xs text-muted-foreground">Invoice intake</div>
      </div>
      {link("/", "Review queue", Inbox, true)}
      {link("/issues", "Issues", AlertTriangle)}
      {link("/config", "Agent config", Settings)}
      <div className="mt-auto border-t border-border pt-3">
        <div className="flex items-center gap-2 px-2 text-sm">
          <User size={14} className="text-muted-foreground" />
          <span className="font-medium">{clerk}</span>
        </div>
        <button
          onClick={onSwitch}
          className="mt-1 px-2 text-xs text-muted-foreground hover:text-foreground"
        >
          Switch user
        </button>
      </div>
    </aside>
  );
}

export default function App() {
  const [clerk, setClerkState] = useState<string | null>(getClerk());

  if (!clerk) return <NameGate onSet={() => setClerkState(getClerk())} />;

  return (
    <div className="flex h-screen">
      <Nav
        clerk={clerk}
        onSwitch={() => {
          clearClerk();
          setClerkState(null);
        }}
      />
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
