import { buttonId, canExpand, descriptionId, getTemplate, getUiOptions, titleId, type ObjectFieldTemplateProps } from "@rjsf/utils";
import type { ReactNode } from "react";
import type { S } from "../api/client";
import { labelFor } from "./labels";
import { inSection, normalisePath, covered, type Flag, type SectionId } from "./sections";
import { audienceText, shown as plain, FlagBadges } from "./templates";

type Node = Record<string, any>;

/** What the Editor passes to every field and template through rjsf's formContext. */
export type EditorContext = {
  section: SectionId;
  flags: Flag[];
  isOther: (path: string) => boolean;
  confirm: (raw: string) => void;
  moves: { id: string; description: string }[];
  issues: string[];
  rulesData?: S["RulesOut"];
  timingDefaults?: S["TimingDefaultsOut"];
  skillsVocabulary?: string[];
  coverPicker?: ReactNode;
};

/** Plumbing kept out of the trainer's way: these root properties live in the collapsed Advanced disclosure. */
const ADVANCED = new Set(["id", "generated", "review", "sources"]);

/** A property renders as a card when it is an object or a list; lists of objects are wide (they hold rows of fields). */
function blockKind(schema: Node | undefined, root: Node | undefined, name: string): "" | "card" | "wide" {
  const child = schema?.properties?.[name];
  if (!child) return "";
  if (child.$ref === "#/$defs/condition") return "";
  const defs = (root?.$defs ?? {}) as Record<string, Node>;
  const resolve = (node: Node): Node => (typeof node?.$ref === "string" ? defs[node.$ref.replace("#/$defs/", "")] ?? {} : node ?? {});
  const spec = resolve(child);
  if (spec.type === "array" || spec.items) {
    const items = resolve((spec.items ?? {}) as Node);
    return Boolean(items.properties) || items.type === "object" || Boolean(items.oneOf) || Boolean(items.anyOf) ? "wide" : "card";
  }
  return spec.type === "object" || spec.properties || spec.oneOf || spec.anyOf ? "card" : "";
}

/** rjsf's object template, mounting only the selected section's fields; the rest stays in the content untouched. */
export function SectionTemplate(props: ObjectFieldTemplateProps) {
  const { className, description, disabled, formData, fieldPathId, onAddProperty, optionalDataControl, properties, readonly, registry, schema, title, uiSchema } = props;
  const options = getUiOptions(uiSchema);
  const DescriptionFieldTemplate = getTemplate("DescriptionFieldTemplate", registry, options);
  const isPureUnionSchema = (schema.oneOf || schema.anyOf) && !schema.properties && properties.length === 0;
  if (isPureUnionSchema) return null;
  const showOptionalDataControlInTitle = !readonly && !disabled;
  const { ButtonTemplates } = registry.templates;
  const AddButton = ButtonTemplates.AddButton;
  const ctx = registry.formContext as EditorContext | undefined;
  const which: SectionId = ctx?.section ?? "basics";
  const isOther = ctx?.isOther ?? ((path: string) => !covered(path));
  const path = fieldPathId.path ?? [];
  const isRoot = path.length === 0;
  const isItem = typeof path.at(-1) === "number";
  const here = normalisePath(path);
  const entry = labelFor(here);

  const kids: ReactNode[] = [];
  const advanced: ReactNode[] = [];
  const groups = new Map<string, ReactNode[]>();
  properties.forEach((property) => {
    const raw = [...path, property.name].map(String).join(".");
    const field = normalisePath([...path, property.name]);
    if (!inSection(field, which, isOther)) return;
    const bank = formData?.bank;
    if (field === "sources.bank" && (bank == null || (typeof bank === "string" && !bank.trim()))) return;
    const own = labelFor(field);
    const kind = own.label === "" ? "" : own.wide ? "wide" : blockKind(schema, registry.rootSchema as Node, property.name);
    // an object with a group joins that group's card only when the group's simple fields are in this tab too
    const joins = isRoot && kind === "card" && own.group !== undefined && groups.has(own.group);
    const node = (
      <div key={property.name} className={joins ? undefined : kind === "wide" ? "card wide" : kind || undefined} data-path={field} data-index-path={raw} tabIndex={-1}>
        {property.content}
      </div>
    );
    // source references, conversion provenance and review details are folded away at the bottom of Basics
    if (isRoot && ADVANCED.has(property.name)) advanced.push(node);
    else if (isRoot && (!kind || joins)) {
      // root-level simple fields share a card per group ("The scenario")
      const key = own.group ?? `solo-${property.name}`;
      let slots = groups.get(key);
      if (!slots) {
        slots = [];
        groups.set(key, slots);
        kids.push(
          <section key={`group-${key}`} className="card group-card">
            {own.group && <h3 className="card-title">{own.group}</h3>}
            <div className="fields">{slots}</div>
          </section>,
        );
      }
      slots.push(node);
    } else kids.push(node);
  });

  const add = canExpand(schema, uiSchema, formData) && (
    <AddButton id={buttonId(fieldPathId, "add")} className="rjsf-object-property-expand" onClick={onAddProperty} disabled={disabled || readonly} uiSchema={uiSchema} registry={registry} />
  );

  if (isRoot && which === "basics" && ctx?.coverPicker) {
    const timingIdx = kids.findIndex((k) => typeof k === "object" && k !== null && "props" in k && (k as any).props?.["data-path"] === "timing");
    if (timingIdx >= 0) {
      kids.splice(timingIdx, 0, ctx.coverPicker);
    } else {
      kids.push(ctx.coverPicker);
    }
  }

  let renderedKids: ReactNode = kids;
  if (isRoot && which === "scoring") {
    const isChildWithPath = (k: ReactNode, p: string) =>
      typeof k === "object" && k !== null && "props" in k && (k as any).props?.["data-path"] === p;
    const reflectionNode = kids.find((k) => isChildWithPath(k, "reflection"));
    const debriefNode = kids.find((k) => isChildWithPath(k, "debrief"));
    const rubricNode = kids.find((k) => isChildWithPath(k, "rubric"));
    const others = kids.filter((k) => !isChildWithPath(k, "reflection") && !isChildWithPath(k, "debrief") && !isChildWithPath(k, "rubric"));

    renderedKids = (
      <>
        <div className="scoring-main-col">{reflectionNode}</div>
        <div className="scoring-side-col">
          {debriefNode}
          {rubricNode}
          {others}
        </div>
      </>
    );
  }

  if (isRoot) {
    return (
      <fieldset className={className} id={fieldPathId.$id}>
        {!showOptionalDataControlInTitle ? optionalDataControl : undefined}
        <div className={`cards cards-${which}`}>
          {renderedKids}
          {advanced.length > 0 && (
            <details className="advanced">
              <summary>Advanced</summary>
              {advanced}
            </details>
          )}
        </div>
        {add}
      </fieldset>
    );
  }

  // a card's heading row: the plain name, any flag to confirm, and, when the map says so, who reads this
  const heading = !isItem ? (
    <legend className="card-head" id={titleId(fieldPathId)}>
      <span className="card-title">{plain(title)}</span>
      <FlagBadges path={here} registry={registry} />
      {entry.audience && <span className={`audience ${entry.audience}`}>{audienceText(entry)}</span>}
    </legend>
  ) : null;

  return (
    <fieldset className={className} id={fieldPathId.$id}>
      {heading}
      {description && <DescriptionFieldTemplate id={descriptionId(fieldPathId)} description={description} schema={schema} uiSchema={uiSchema} registry={registry} />}
      {!showOptionalDataControlInTitle ? optionalDataControl : undefined}
      <div className="fields">{kids}</div>
      {add}
    </fieldset>
  );
}
