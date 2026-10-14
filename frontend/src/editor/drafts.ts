import { createContext, useContext, useEffect } from "react";

export type ConditionDraft = { valid: boolean; focus: () => void };

/** Every condition box registers its draft here, keyed by the field id; the Editor refuses Check, Save, the YAML switch and a section switch while any draft is invalid. */
export const conditionDrafts = new Map<string, ConditionDraft>();

export type DraftReport = (id: string, invalid: boolean, focus: () => void) => void;

export const DraftContext = createContext<DraftReport>(() => {});

/** Reports one draft (a row control or a JSON box) as invalid while incomplete; the report is dropped on unmount. */
export function useDraft(id: string, invalid: boolean, focus: () => void): DraftReport {
  const report = useContext(DraftContext);
  useEffect(() => {
    report(id, invalid, focus);
    return () => report(id, false, focus);
  });
  return report;
}
