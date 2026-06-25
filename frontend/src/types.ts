export interface LineItem {
  id: number;
  description: string;
  quantity: number | null;
  unit_price: number | null;
  amount: number;
  gl_code: string | null;
  gl_confidence: number;
  needs_review: boolean;
  reasoning: string | null;
}

export interface Bill {
  id: number;
  document_id: number;
  vendor: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  due_date: string | null;
  currency: string;
  is_credit_memo: boolean;
  applies_to_invoice: string | null;
  subtotal: number;
  tax: number;
  other_charges: number;
  total: number;
  status: string;
  is_duplicate: boolean;
  duplicate_of_bill_id: number | null;
  confidence: number;
  agent_reasoning: string | null;
  review_flags: string[];
  pages: string | null;
  segment_index: number;
  created_at: string;
  locked_by: string | null;
  locked_at: string | null;
  line_items: LineItem[];
}

export interface Issue {
  id: number;
  document_id: number;
  kind: string;
  reason: string;
  resolved: boolean;
  created_at: string;
}

export interface GLAccount {
  id: number;
  code: string;
  name: string;
  description: string;
  is_active: boolean;
}

export interface AgentConfig {
  id: number;
  version: number;
  instructions: string;
  routing_rules: string;
  is_active: boolean;
  note: string | null;
  created_at: string;
}
