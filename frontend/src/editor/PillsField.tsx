import type { FieldProps } from "@rjsf/utils";
import { useRef, useState } from "react";
import { IconX } from "../icons";
import { labelFor } from "./labels";
import { normalisePath } from "./sections";

export function PillsField({ formData, onChange, fieldPathId, disabled, readonly }: FieldProps) {
  const [query, setQuery] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const items = Array.isArray(formData) ? formData.filter((item) => typeof item === "string") : [];
  const selected = (item: string) => items.some((value) => value.trim().toLowerCase() === item.toLowerCase());
  const path = normalisePath(fieldPathId.path);
  const label = labelFor(path);
  const id = fieldPathId.$id;
  const locked = disabled || readonly;
  const itemName = label.item?.toLowerCase() ?? "item";

  function add() {
    const text = query.trim();
    if (!text) return;
    if (!selected(text)) onChange([...items, text], fieldPathId.path);
    setQuery("");
    input.current?.focus();
  }

  return (
    <div className="field skills-field pills-field">
      <label className="card-title" htmlFor={id}>{label.label}</label>
      <p className="hint">{label.hint}</p>
      <div className="skills-input">
        {items.map((item, index) => (
          <span className="chip" key={`${index}:${item}`}>
            <span>{item}</span>
            <button
              type="button"
              aria-label={`Remove ${item}`}
              disabled={locked}
              onClick={() => {
                onChange(items.filter((_, at) => at !== index), fieldPathId.path);
                input.current?.focus();
              }}
            >
              <IconX size={12} />
            </button>
          </span>
        ))}
        <input
          ref={input}
          id={id}
          aria-describedby={`${id}__help`}
          placeholder={`Type a ${itemName}…`}
          value={query}
          disabled={locked}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.nativeEvent.isComposing) {
              event.preventDefault();
              add();
            }
          }}
        />
      </div>
      <p className="hint" id={`${id}__help`}>Press Enter to add a {itemName}.</p>
    </div>
  );
}
