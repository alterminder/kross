import type { FieldProps } from "@rjsf/utils";
import { labelFor } from "./labels";

export const CCHN_TOOL_NAMES: Record<number, string> = {
  1: "Gathering Quality Information About the Context",
  2: "Drawing the Island of Agreements",
  3: "Fostering Legitimacy and Building Trust",
  4: "Determining the Typology of a Humanitarian Negotiation",
  5: "Drawing the Pathway of a Normative Negotiation",
  6: "Creating a Conducive Environment for a Transaction",
  7: "Clarifying the Terms of the Transaction",
  8: "Addressing the Human Elements of the Transaction",
  9: "Analyzing the Position of the Counterpart (the Iceberg)",
  10: "Identifying Own Priorities and Objectives (Your Own Iceberg)",
  11: "Exploring the Common Shared Space",
  12: "Network Mapping and Leveraging Influence Among Stakeholders",
  13: "Identifying the Shared Benefit of the Negotiation",
  14: "Evaluating Cost-Benefit of Options",
  15: "Design of the Mandate",
  16: "External Communication Around the Negotiation Process",
  17: "Identification of Red Lines",
};

export function CchnReferencesField({ formData, fieldPathId }: FieldProps) {
  const label = labelFor("sources.cchn_tools");
  const tools = Array.isArray(formData) ? formData : [];
  const labelId = `${fieldPathId.$id}__label`;
  return (
    <div className="field">
      <span className="card-title" id={labelId}>{label.label}</span>
      <p className="hint">{label.hint}</p>
      {tools.length > 0 ? (
        <ul className="cchn-references-list" aria-labelledby={labelId}>
          {tools.map((tool, index) => {
            const title = typeof tool === "number" ? CCHN_TOOL_NAMES[tool] : null;
            const text = typeof tool === "number"
              ? (title ? `Tool ${tool}: ${title}` : `Tool ${tool}`)
              : "Invalid CCHN reference";
            return <li key={index}>{text}</li>;
          })}
        </ul>
      ) : (
        <p className="hint">No CCHN references recorded.</p>
      )}
    </div>
  );
}

