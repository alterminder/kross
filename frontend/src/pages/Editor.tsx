import Form from "@rjsf/core";
import type { RJSFSchema } from "@rjsf/utils";
import { useEffect, useMemo, useState, type KeyboardEvent } from "react";
import { useParams } from "react-router";
import { parse, stringify } from "yaml";
import { ApiError, api, type S } from "../api/client";
import { ConditionField } from "../editor/ConditionField";
import { CchnReferencesField } from "../editor/CchnReferencesField";
import { OverridesField } from "../editor/OverridesField";
import { PillsField } from "../editor/PillsField";
import { TimingField } from "../editor/TimingField";
import { SkillsField } from "../editor/SkillsField";
import { ButtonTemplates } from "../editor/buttons";
import { conditionUiSchema } from "../editor/conditions";
import { conditionDrafts } from "../editor/drafts";
import { formSchemaOf, validatorFor } from "../editor/formSchema";
import { labelUiSchema, mergeUi } from "../editor/labels";
import { SectionTemplate, type EditorContext } from "../editor/SectionTemplate";
import { EditorArrayItemTemplate, EditorArrayTitleTemplate, EditorFieldTemplate, EditorInputTemplate, EditorTitleFieldTemplate, EditorWidgets } from "../editor/templates";
import { SECTIONS, flagsOf, normalisePath, otherPaths, schemaPaths, sectionOf, type SectionId } from "../editor/sections";
import { useLoad } from "../hooks";
import { hidePrep } from "../prep";
import { Problem, cardCover, coverUrl } from "../ui";

type Content = Record<string, unknown>;

function parseScenario(text: string): Content {
  const parsed: unknown = parse(text);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("the top level must be a mapping");
  return parsed as Content;
}

/** Preview text with shapes validated: YAML content is caller data and may put an object where text belongs. */
function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function list(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && item !== "") : [];
}

function lineTexts(value: unknown): string[] {
  return Array.isArray(value)
    ? value
        .map((line) => (line && typeof line === "object" ? (line as Content).text : undefined))
        .filter((text): text is string => typeof text === "string" && text !== "")
    : [];
}

export function ScenarioEditor() {
  const { id } = useParams();
  const schema = useLoad<RJSFSchema & { "x-skills-vocabulary"?: string[] }>("scenarios/schema");
  const covers = useLoad<string[]>("scenarios/covers");
  const rules = useLoad<S["RulesOut"]>("rules");
  const timingDefaults = useLoad<S["TimingDefaultsOut"]>("scenarios/timing-defaults");
  const existing = useLoad<S["ScenarioDetail"]>(`scenarios/${id}`);
  const [content, setContent] = useState<Content | null>(null);
  const [cover, setCover] = useState("field");
  const [dirty, setDirty] = useState(false);
  const [yamlText, setYamlText] = useState<string | null>(null); // null while the form shows
  const [issues, setIssues] = useState<S["IssueOut"][] | null>(null);
  const [problem, setProblem] = useState<string>();
  const [focusPath, setFocusPath] = useState<string>();
  const sections = hidePrep() ? SECTIONS.filter((item) => item.id !== "cchn_prep") : SECTIONS; // prep is hidden; its data stays
  const [active, setActive] = useState<SectionId>(() => {
    try {
      const stored = sessionStorage.getItem(`nlab-editor-section:${id}`) as SectionId | null;
      return stored && sections.some((item) => item.id === stored) ? stored : "basics";
    } catch {
      return "basics";
    }
  });

  useEffect(() => {
    if (existing.data?.content) {
      setContent(existing.data.content);
      setCover(existing.data.cover);
      setDirty(false);
    }
  }, [existing.data]);

  const formSchema = useMemo(() => (schema.data ? formSchemaOf(schema.data) : null), [schema.data]);
  const validator = useMemo(() => (formSchema ? validatorFor(formSchema) : null), [formSchema]);

  const uiSchema = useMemo(
    () =>
      mergeUi(mergeUi(conditionUiSchema(formSchema), labelUiSchema(formSchema)), {
        overrides: { "ui:field": "overrides" },
        timing: { "ui:field": "timing" },
        skills_tested: { "ui:field": "skills" },
        degradation_cues: { "ui:field": "pills" },
        sources: { cchn_tools: { "ui:field": "cchnReferences" } },
        "ui:submitButtonOptions": { norender: true },
      }),
    [formSchema],
  );

  const isOther = useMemo(() => otherPaths(formSchema), [formSchema]);
  const fields = useMemo(() => schemaPaths(formSchema), [formSchema]);
  const flags = useMemo(() => (content ? flagsOf(content, new Set(Object.keys(formSchema?.properties ?? {}))) : []), [content, formSchema]);

  const formContext: EditorContext = {
    section: active,
    flags,
    isOther,
    moves: (rules.data?.moves ?? []).map((move) => ({ id: move.id, description: move.description })),
    issues: (((content?.issues ?? []) as Content[]).map((issue) => String(issue.id))).filter(Boolean),
    rulesData: rules.data,
    timingDefaults: timingDefaults.data,
    skillsVocabulary: schema.data?.["x-skills-vocabulary"] ?? [],
    confirm: (raw) => {
      setDirty(true);
      setContent((old) => {
        if (!old) return old;
        const review = { ...((old.review ?? {}) as Content) };
        const list = [...((review.needs_icrc_confirmation as string[] | undefined) ?? [])];
        const at = list.indexOf(raw);
        if (at >= 0) list.splice(at, 1); // exactly one entry, even when the list repeats it
        review.needs_icrc_confirmation = list;
        return { ...old, review };
      });
    },
    coverPicker:
      existing.data && active === "basics" ? (
        <section key="cover-picker" className="covers compact card">
          <div className="card-head">
            <span className="card-title">Cover</span>
          </div>
          <div className="cover-row">
            {existing.data.cover_image_version && (
              <label key="painted">
                <input
                  type="radio"
                  name="cover"
                  value="custom"
                  checked={cover === "custom"}
                  onChange={() => {
                    setCover("custom");
                    setDirty(true);
                  }}
                />
                <img
                  src={cardCover({ id: existing.data.id, cover: "custom", cover_image_version: existing.data.cover_image_version })}
                  alt="Painted for this scenario"
                />
              </label>
            )}
            {covers.data?.map((name) => (
              <label key={name}>
                <input
                  type="radio"
                  name="cover"
                  value={name}
                  checked={cover === name}
                  onChange={() => {
                    setCover(name);
                    setDirty(true);
                  }}
                />
                <img src={coverUrl(name)} alt={name} />
              </label>
            ))}
          </div>
        </section>
      ) : undefined,
  };

  function switchTo(next: SectionId): boolean {
    if (blocked()) return false;
    setActive(next);
    try {
      sessionStorage.setItem(`nlab-editor-section:${id}`, next);
    } catch {
      // private mode: the choice just does not persist
    }
    return true;
  }

  /** The rendered field an issue path maps to (sub-paths under a condition site map to that site), keeping indices. */
  function linkPath(path: string): string | null {
    const parts = path.split(".");
    for (let i = parts.length; i > 0; i--) {
      const prefix = parts.slice(0, i).join(".");
      if (fields.has(normalisePath(prefix))) return prefix;
    }
    return null;
  }

  /** An issue that maps to a field opens its section and focuses the field; a refused switch leaves focus alone. */
  function openField(path: string) {
    if (!switchTo(sectionOf(normalisePath(path)) ?? "other")) return;
    setFocusPath(path);
  }

  useEffect(() => {
    if (!focusPath) return;
    // rjsf commits its own subtree a tick after the section switch; the field is only then in the DOM
    const timer = setTimeout(() => {
      const at = `[data-index-path="${focusPath}"]`;
      const wrap = document.querySelector<HTMLElement>(at);
      for (let node = wrap?.parentElement; node; node = node.parentElement) {
        if (node instanceof HTMLDetailsElement) node.open = true; // folded-away fields (Advanced) must show before they can take focus
      }
      const target = document.querySelector<HTMLElement>(`${at} input, ${at} select, ${at} textarea, ${at} button, ${at} [tabindex]`) ?? wrap;
      target?.focus();
      target?.scrollIntoView?.({ block: "center" });
      setFocusPath(undefined);
    }, 0);
    return () => clearTimeout(timer);
  }, [focusPath, active]);

  if (existing.error || schema.error) return <Problem text={existing.error ?? schema.error} />;
  if (!formSchema || !validator || !existing.data) return <p className="loading">Loading…</p>;
  if (!existing.data.can_edit) return <p>Only the scenario's editors can change it.</p>;
  if (!content) return <p className="loading">Loading…</p>; // the effect above is about to fill it

  function current(): Content | null {
    if (yamlText === null) return content; // the YAML tab's text wins while it is open
    try {
      return parseScenario(yamlText);
    } catch (failure) {
      setProblem(`The YAML does not parse: ${(failure as Error).message}`);
      return null;
    }
  }

  /** An invalid condition draft blocks Check, Save and the YAML switch; the first invalid box takes focus. */
  function blocked(): boolean {
    for (const draft of conditionDrafts.values()) {
      if (!draft.valid) {
        setProblem("Fix the condition marked in red before checking or saving");
        draft.focus();
        return true;
      }
    }
    return false;
  }

  function toggleYaml() {
    if (blocked()) return;
    if (yamlText === null) {
      setYamlText(stringify(content));
      return;
    }
    const parsed = current();
    if (parsed) {
      setContent(parsed);
      setYamlText(null);
    }
  }

  async function validate() {
    if (blocked()) return;
    const body = current();
    if (!body) return;
    setProblem(undefined);
    try {
      setIssues(await api<S["IssueOut"][]>("scenarios/validate", { method: "POST", body: { content: body } }));
    } catch (failure) {
      setProblem((failure as Error).message);
    }
  }

  async function save() {
    if (blocked()) return;
    const body = current();
    if (!body) return;
    setProblem(undefined);
    try {
      await api<S["ScenarioDetail"]>(`scenarios/${id}`, {
        method: "PUT",
        body: { content: body, cover },
      });
      setDirty(false); // a save stays in the editor
    } catch (failure) {
      setProblem((failure as Error).message);
      if (failure instanceof ApiError && failure.status === 422) await validate();
    }
  }

  const visible = sections.filter((item) => item.id !== "other" || [...fields].some(isOther));
  const at = visible.findIndex((item) => item.id === active);
  const prev = at > 0 ? visible[at - 1] : undefined;
  const next = at >= 0 && at < visible.length - 1 ? visible[at + 1] : undefined;
  const heading = str(content.title) || str(existing.data.title) || "Untitled scenario";
  const brief = (content.trainee_brief ?? {}) as Content;
  const facts = list(brief.facts);
  const redLines = lineTexts(brief.red_lines);

  /** Left/Right arrows move between tabs (and activate them); the tablist keeps roving focus. */
  function onTabsKey(event: KeyboardEvent) {
    let to = -1;
    if (event.key === "ArrowRight") to = (at + 1) % visible.length;
    else if (event.key === "ArrowLeft") to = (at - 1 + visible.length) % visible.length;
    else return;
    event.preventDefault();
    const target = visible[to].id;
    if (switchTo(target)) document.getElementById(`tab-${target}`)?.focus();
  }

  return (
    <article>
      <header className="editor-head">
        <div>
          <p className="eyebrow">{`EDIT SCENARIO · STEP ${at + 1} OF ${visible.length}`}</p>
          <h1>{heading}</h1>
        </div>
        <div className="actions editor-actions">
          <span className={dirty ? "save-state dirty" : "save-state"}>{dirty ? "Unsaved changes" : "All changes saved"}</span>
          <button type="button" className="ghost" onClick={toggleYaml}>
            {yamlText === null ? "Edit as YAML" : "Back to the form"}
          </button>
          <button type="button" className="secondary" onClick={validate}>
            Check
          </button>
          <button type="button" className="primary" onClick={save}>
            Save
          </button>
        </div>
      </header>
      <Problem text={problem} />
      {issues &&
        (issues.length === 0 ? (
          <p>No problems found.</p>
        ) : (
          <ul className="issues">
            {issues.map((issue) => {
              const target = issue.path ? linkPath(issue.path) : null;
              return (
                <li key={`${issue.path}:${issue.message}`}>
                  {target ? (
                    <button type="button" className="small secondary" onClick={() => openField(target)}>
                      <code>{issue.path}</code>
                    </button>
                  ) : (
                    <code>{issue.path || "(top level)"}</code>
                  )}{" "}
                  {issue.message}
                </li>
              );
            })}
          </ul>
        ))}
      {yamlText === null ? (
        <>
          <div className="tabs editor-tabs" role="tablist" aria-label="Sections" onKeyDown={onTabsKey}>
            {visible.map((item) => {
              // a container flag counts in the one section that owns it, not in every section showing the container
              const count = flags.filter((flag) => (sectionOf(flag.path) ?? "other") === item.id).length;
              const selected = active === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  role="tab"
                  id={`tab-${item.id}`}
                  aria-selected={selected}
                  aria-controls={`panel-${item.id}`}
                  tabIndex={selected ? 0 : -1}
                  className={selected ? "tab active" : "tab"}
                  onClick={() => switchTo(item.id)}
                >
                  {item.label}
                  {count > 0 && (
                    <>
                      <span aria-hidden="true">{` ⚑ ${count}`}</span>
                      <span className="sr-only">{` ${count} to confirm`}</span>
                    </>
                  )}
                </button>
              );
            })}
          </div>
          <div className="editor-panel" role="tabpanel" id={`panel-${active}`} aria-labelledby={`tab-${active}`} tabIndex={0}>
            <div className={active === "brief" ? "brief-layout" : undefined}>
              <Form
                schema={formSchema}
                formData={content}
                validator={validator}
                noValidate
                fields={{ condition: ConditionField, overrides: OverridesField, timing: TimingField, skills: SkillsField, pills: PillsField, cchnReferences: CchnReferencesField }}
                templates={{
                  ObjectFieldTemplate: SectionTemplate,
                  ArrayFieldItemTemplate: EditorArrayItemTemplate,
                  ArrayFieldTitleTemplate: EditorArrayTitleTemplate,
                  ButtonTemplates,
                  FieldTemplate: EditorFieldTemplate,
                  TitleFieldTemplate: EditorTitleFieldTemplate,
                  BaseInputTemplate: EditorInputTemplate,
                }}
                widgets={EditorWidgets}
                formContext={formContext}
                uiSchema={uiSchema}
                onChange={(event) => {
                  setContent(event.formData as Content);
                  setDirty(true);
                }}
              />
              {active === "brief" && (
                <aside className="card preview" aria-label="Preview as the trainee will see it">
                  <p className="preview-label">Preview — as the trainee will see it</p>
                  <div className="preview-paper">
                    <p className="preview-eyebrow">Your mission</p>
                    <h3>{heading}</h3>
                    {str(brief.situation) && <p>{str(brief.situation)}</p>}
                    {str(brief.objective) && <p className="preview-objective">{str(brief.objective)}</p>}
                    {facts.length > 0 && (
                      <>
                        <p className="preview-eyebrow">What you know</p>
                        <ul className="preview-list">
                          {facts.map((fact, index) => (
                            <li key={index}>{fact}</li>
                          ))}
                        </ul>
                      </>
                    )}
                    {redLines.length > 0 && (
                      <>
                        <p className="preview-eyebrow">Red lines</p>
                        <ul className="preview-list">
                          {redLines.map((line, index) => (
                            <li key={index}>{line}</li>
                          ))}
                        </ul>
                      </>
                    )}
                  </div>
                </aside>
              )}
            </div>
            <nav className="step-nav" aria-label="Steps">
              {prev ? (
                <button type="button" className="ghost" onClick={() => switchTo(prev.id)}>{`← Previous: ${prev.label}`}</button>
              ) : (
                <span />
              )}
              {next && (
                <button type="button" className="ghost" onClick={() => switchTo(next.id)}>{`Next: ${next.label} →`}</button>
              )}
            </nav>
          </div>
        </>
      ) : (
        <textarea
          className="yaml"
          aria-label="Scenario YAML"
          spellCheck={false}
          value={yamlText}
          onChange={(event) => {
            setYamlText(event.target.value);
            setDirty(true);
          }}
        />
      )}
    </article>
  );
}
