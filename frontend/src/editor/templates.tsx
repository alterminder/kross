import { getDefaultRegistry } from "@rjsf/core";
import { getTemplate, getUiOptions, titleId, type ArrayFieldItemTemplateProps, type ArrayFieldTitleProps, type FieldTemplateProps, type TitleFieldProps, type WidgetProps } from "@rjsf/utils";
import type { ReactNode } from "react";
import { labelFor } from "./labels";
import { normalisePath } from "./sections";
import type { EditorContext } from "./SectionTemplate";

const RAW_KEY = /^[a-z0-9_]+$/;
type Node = Record<string, any>;
type Registry = FieldTemplateProps["registry"];

const AUDIENCE: Record<string, string> = { trainee: "Trainee sees this", hidden: "Trainee never sees this" };

/** The badge text: the map's own wording when it has one (revealable facts are hidden only at the start). */
export function audienceText(entry: { audience?: string; audienceAs?: string }): string | undefined {
  if (!entry.audience) return undefined;
  return entry.audienceAs ?? AUDIENCE[entry.audience];
}

/** The fallback for anything the map misses: humanise the key; a raw key never reaches the screen. */
export function shown(title: ReactNode): string | undefined {
  if (title === undefined || title === null || title === "") return undefined;
  const text = String(title);
  return RAW_KEY.test(text) ? humanise(text) : text;
}

/** "skills_tested" -> "Skills tested"; the fallback for any unmapped key. */
export function humanise(key: string): string {
  const text = key.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** The row title for an array item: the map's singular plus the row number ("Skill 2"). */
export function rowTitle(path: (string | number)[] | undefined, title: ReactNode): string | undefined {
  const at = path?.at(-1);
  const one = shown(title);
  if (!one) return undefined;
  return typeof at === "number" ? `${one} ${at + 1}` : one;
}

const DEFAULTS = getDefaultRegistry();

/** YAML content can put an object where text belongs. React coerces control values to text and throws on objects
 *  with no primitive form; show those as an empty control and keep the content itself until the trainer edits. */
function safeValue(value: unknown): unknown {
  if (value == null || typeof value === "string" || typeof value === "number" || typeof value === "boolean") return value;
  if (Array.isArray(value)) return value.filter((item) => typeof item === "string" || typeof item === "number");
  return "";
}

export const EditorInputTemplate = (props: WidgetProps) => <DEFAULTS.templates.BaseInputTemplate {...props} value={safeValue(props.value)} />;

export const EditorWidgets = {
  textarea: (props: WidgetProps) => <DEFAULTS.widgets.TextareaWidget {...props} value={safeValue(props.value)} />,
  select: (props: WidgetProps) => <DEFAULTS.widgets.SelectWidget {...props} value={safeValue(props.value)} />,
};

/** The "⚑ ICRC to confirm" badge and its Confirm button, beside the field label it belongs to. */
export function FlagBadges({ path, registry }: { path: string; registry?: Registry }) {
  const ctx = registry?.formContext as EditorContext | undefined;
  const flags = (ctx?.flags ?? []).filter((flag) => flag.path === path);
  if (flags.length === 0) return null;
  return (
    <>
      {flags.map((flag) => (
        <span key={`${flag.path}:${flag.reason}`} className="flag-badge">
          <em>{`⚑ ${flag.reason}`}</em>
          {flag.raw && (
            <button type="button" className="small" onClick={() => ctx?.confirm(flag.raw!)}>
              Confirm
            </button>
          )}
        </span>
      ))}
    </>
  );
}

/** rjsf's field wrapper: plain label (no required asterisk) with its flag badge, the field, then the one-line hint. */
export function EditorFieldTemplate(props: FieldTemplateProps) {
  const { id, label, children, errors, help, description, hidden, displayLabel, registry, uiSchema, fieldPathId } = props;
  const WrapIfAdditionalTemplate = getTemplate("WrapIfAdditionalTemplate", registry, getUiOptions(uiSchema));
  if (hidden) return <div className="hidden">{children}</div>;
  const chips = Boolean((uiSchema as Record<string, unknown> | undefined)?.["ui:chips"]);
  const custom = Boolean((uiSchema as Record<string, unknown> | undefined)?.["ui:field"]);
  const spec = (props.schema ?? {}) as Node;
  // objects and arrays carry their flags on the card/list heading instead
  const headingFlags = spec.type === "object" || spec.type === "array" || Boolean(spec.properties) || Boolean(spec.items) || Boolean(spec.oneOf) || Boolean(spec.anyOf);
  const path = normalisePath(fieldPathId?.path ?? []);
  const text = rowTitle(fieldPathId?.path, label);
  return (
    <WrapIfAdditionalTemplate {...props}>
      {displayLabel && text ? (
        <div className="label-line">
          <label className={chips ? "sr-only" : "control-label"} htmlFor={id}>
            {text}
          </label>
          <FlagBadges path={path} registry={registry} />
        </div>
      ) : null}
      {!displayLabel && (custom || !headingFlags) && (
        <div className="label-line">
          <FlagBadges path={path} registry={registry} />
        </div>
      )}
      {children}
      {displayLabel && description ? description : null}
      {errors}
      {help}
    </WrapIfAdditionalTemplate>
  );
}

/** rjsf's object/array title: uppercase card heading, humanised if unmapped, never a required asterisk. */
export function EditorTitleFieldTemplate(props: TitleFieldProps) {
  const { id, title, optionalDataControl } = props;
  return (
    <legend className="card-head" id={id}>
      <span className="card-title">{shown(title)}</span>
      {optionalDataControl && <span className="pull-right">{optionalDataControl}</span>}
    </legend>
  );
}

/** The title row of a list: plain name, flags to confirm and the audience badge. */
export function EditorArrayTitleTemplate(props: ArrayFieldTitleProps) {
  const { fieldPathId, title, uiSchema, registry, optionalDataControl } = props;
  const options = getUiOptions(uiSchema, registry.globalUiOptions);
  if (!title || options.label === false) return null;
  const path = normalisePath(fieldPathId.path ?? []);
  const entry = labelFor(path);
  const audience = audienceText(entry);
  return (
    <legend className="card-head" id={titleId(fieldPathId)}>
      <span className="card-title">{shown(title)}</span>
      <FlagBadges path={path} registry={registry} />
      {audience && <span className={`audience ${entry.audience}`}>{audience}</span>}
      {optionalDataControl && <span className="pull-right">{optionalDataControl}</span>}
    </legend>
  );
}

/**
 * Array rows: object items get a "Goal 1" row heading with quiet controls, scalars a slim input row,
 * short lists (map `chips`) a pill with an "x". The row wording comes from the map's `item`.
 */
export function EditorArrayItemTemplate(props: ArrayFieldItemTemplateProps) {
  const { children, buttonsProps, hasToolbar, registry, schema, uiSchema } = props;
  const options = getUiOptions(uiSchema);
  const Buttons = getTemplate("ArrayFieldItemButtonsTemplate", registry, options);
  const raw = (uiSchema as Record<string, unknown> | undefined) ?? {};
  const tools = hasToolbar ? (
    <div className="row-tools">
      <Buttons {...buttonsProps} />
    </div>
  ) : null;
  if (raw["ui:chips"]) {
    return (
      <span className="chip">
        {children}
        {hasToolbar && <Buttons {...buttonsProps} hasMoveUp={false} hasMoveDown={false} hasCopy={false} />}
      </span>
    );
  }
  const spec = (schema ?? {}) as Node;
  const object = spec.type === "object" || Boolean(spec.properties) || Boolean(spec.oneOf) || Boolean(spec.anyOf);
  if (object) {
    const title = rowTitle(buttonsProps?.fieldPathId?.path, options.title);
    return (
      <div className="array-row">
        {(title || tools) && (
          <div className="array-row-head">
            {title && <span className="array-row-title">{title}</span>}
            {tools}
          </div>
        )}
        {children}
      </div>
    );
  }
  return (
    <div className="array-row slim">
      {children}
      {tools}
    </div>
  );
}
