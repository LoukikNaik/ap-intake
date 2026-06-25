// Clerk identity for the demo (no real auth). The user enters their name/id on first
// load; it's persisted in localStorage and stamped on the review lease (locked_by).
const KEY = "ap_clerk_id";

export function getClerk(): string | null {
  return localStorage.getItem(KEY);
}

export function setClerk(name: string) {
  localStorage.setItem(KEY, name.trim());
}

export function clearClerk() {
  localStorage.removeItem(KEY);
}

// Convenience accessor used by pages; the name gate guarantees this is set.
export function clerkId(): string {
  return getClerk() || "unknown";
}
