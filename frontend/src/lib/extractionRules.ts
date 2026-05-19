/**
 * TS mirror of app/customer/extraction_rules.py. Keep in sync.
 * Used by the ObjectToggleGrid for live cascade preview.
 */

export interface ObjectsState {
  contacts: boolean;
  companies: boolean;
  deals: boolean;
  leads: boolean;
  owners: boolean;
  deal_pipelines: boolean;
  lead_pipelines: boolean;
  activities: {
    calls: boolean;
    meetings: boolean;
    emails: boolean;
    notes: boolean;
    tasks: boolean;
  };
  campaigns: boolean;
  forms: boolean;
  form_submissions: boolean;
}

export const DEFAULT_OBJECTS: ObjectsState = {
  contacts: true,
  companies: true,
  deals: true,
  leads: true,
  owners: true,
  deal_pipelines: true,
  lead_pipelines: true,
  activities: { calls: true, meetings: true, emails: true, notes: true, tasks: true },
  campaigns: true,
  forms: true,
  form_submissions: true,
};

export const DEPENDENCIES: Record<string, string[]> = {
  leads: ["lead_pipelines"],
  forms: ["form_submissions"],
};

export function applyCascade(input: ObjectsState): ObjectsState {
  const out: ObjectsState = JSON.parse(JSON.stringify(input));
  if (!out.activities) {
    out.activities = { calls: true, meetings: true, emails: true, notes: true, tasks: true };
  }
  let changed = true;
  while (changed) {
    changed = false;
    for (const trigger of Object.keys(DEPENDENCIES)) {
      const t = trigger as keyof ObjectsState;
      if ((out[t] as boolean) === false) {
        for (const off of DEPENDENCIES[trigger]) {
          const o = off as keyof ObjectsState;
          if ((out[o] as boolean) !== false) {
            (out as any)[o] = false;
            changed = true;
          }
        }
      }
    }
  }
  return out;
}

export interface ObjectGroup {
  name: string;
  children: string[];
  expandable: boolean;
  containerKey?: keyof ObjectsState;
}

export const OBJECT_GROUPS: ObjectGroup[] = [
  { name: "CRM", children: ["contacts", "companies", "deals", "leads"], expandable: false },
  {
    name: "Activities",
    children: ["calls", "meetings", "emails", "notes", "tasks"],
    expandable: true,
    containerKey: "activities",
  },
  { name: "Marketing", children: ["campaigns", "forms", "form_submissions"], expandable: false },
  { name: "Other", children: ["owners", "deal_pipelines", "lead_pipelines"], expandable: false },
];

export function describeImpact(disabledKey: string): string[] {
  const out: string[] = [];
  const forced = DEPENDENCIES[disabledKey] || [];
  for (const f of forced) out.push(f);
  // Surface common downstream impacts for the tooltip
  const downstream: Record<string, string[]> = {
    leads: ["dim_leads", "bridge_lead_*", "agg_lead_health"],
    forms: ["fact_form_submissions"],
    deals: ["dim_deals", "agg_deal_*"],
    contacts: ["dim_contacts", "all bridge_*_contact"],
    companies: ["dim_companies", "all bridge_*_company"],
  };
  if (downstream[disabledKey]) {
    out.push(...downstream[disabledKey]);
  }
  return out;
}
