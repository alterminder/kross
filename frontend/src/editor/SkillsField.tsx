import type { FieldProps } from "@rjsf/utils";
import { useRef, useState } from "react";
import { IconX } from "../icons";
import type { EditorContext } from "./SectionTemplate";
import { labelFor } from "./labels";

export function SkillsField({ formData, onChange, registry, fieldPathId, disabled, readonly }: FieldProps) {
  const [query, setQuery] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const skills = Array.isArray(formData) ? formData.filter((skill) => typeof skill === "string") : [];
  const vocabulary = (registry.formContext as EditorContext | undefined)?.skillsVocabulary ?? [];
  const selected = (skill: string) => skills.some((value) => value.trim().toLowerCase() === skill.toLowerCase());
  const label = labelFor("skills_tested");
  const id = fieldPathId.$id;
  const locked = disabled || readonly;
  const suggestions = query.trim()
    ? vocabulary.filter((skill) => !selected(skill) && skill.toLowerCase().includes(query.trim().toLowerCase()))
    : [];

  function add(value = query) {
    const text = value.trim();
    if (!text) return;
    const skill = vocabulary.find((value) => value.toLowerCase() === text.toLowerCase()) ?? text;
    if (!selected(skill)) onChange([...skills, skill], fieldPathId.path);
    setQuery("");
    input.current?.focus();
  }

  return (
    <div className="field skills-field">
      <label className="card-title" htmlFor={id}>{label.label}</label>
      <p className="hint">{label.hint}</p>
      <div className="skills-input">
        {skills.map((skill, index) => (
          <span className="chip" key={`${index}:${skill}`}>
            <span>{skill}</span>
            <button
              type="button"
              aria-label={`Remove ${skill}`}
              disabled={locked}
              onClick={() => {
                onChange(skills.filter((_, at) => at !== index), fieldPathId.path);
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
          placeholder="Type a skill…"
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
        {suggestions.length > 0 && (
          <div className="skills-suggestions" role="group" aria-label="Suggested skills">
            {suggestions.map((skill) => (
              <button type="button" className="small secondary" key={skill} disabled={locked} onClick={() => add(skill)}>{skill}</button>
            ))}
          </div>
        )}
      </div>
      <p className="hint" id={`${id}__help`}>Choose a suggestion, or press Enter to add a custom skill.</p>
    </div>
  );
}
