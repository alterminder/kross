import type { FieldProps } from "@rjsf/utils";
import { useEffect, useId, useRef, useState, type ReactNode, type Ref } from "react";
import {
  ConditionGroup,
  ConditionRow,
  type BuilderContext,
  KINDS,
  isGroup,
  rowComplete,
  rowLabel,
} from "./conditionRows";
import { DraftContext, conditionDrafts, useDraft, type DraftReport } from "./drafts";

export type { BuilderContext };

type Props = Pick<FieldProps, "schema" | "formData" | "onChange" | "fieldPathId"> & {
  name?: string;
  registry?: FieldProps["registry"];
  formContext?: BuilderContext;
};

const DESCRIPTION = "Every test here must hold for this to apply.";

function humanise(name: string): string {
  const words = name.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Which kind of condition site this is; its empty texts follow the engine, not a generic rule. */
type Site = "reveal" | "auto" | "rule" | "plain";

function siteOf(path: string[]): Site {
  const last = path[path.length - 1];
  const parent = path[path.length - 2];
  if (last === "reveal_when") return "reveal";
  if (last === "when" && parent === "auto") return "auto";
  if (last === "when" && (path.includes("triggers") || path.includes("outcomes"))) return "rule";
  return "plain";
}

const SITE_TEXTS: Record<Site, { absent: string; empty: string }> = {
  // reveal_when and auto.when treat an empty object as no rule (the default reveal rule; at_turn only)
  reveal: { absent: "Default reveal rule", empty: "Default reveal rule" },
  auto: { absent: "Only at the turn above, if set", empty: "Only at the turn above, if set" },
  // triggers and outcomes require a condition; an outcome's empty object is left to the server's Check
  rule: { absent: "Missing: add a test", empty: "Always" },
  plain: { absent: "No condition (never fires)", empty: "Always" },
};

/** One row of the builder: a test (key + value) or an All/Any group of member conditions. `scalar` keeps a value that is not a condition object. */
type Entry = { id: string; key: string; raw?: unknown; members?: Node[]; scalar?: boolean };
/** One condition object: its keys all must hold (AND). `fromData` keeps an empty object ("Always") from data. */
type Node = { id: string; fromData: boolean; entries: Entry[] };

let nextId = 0;
const uid = () => `x${++nextId}`;
const ROOT = "root";

/** A value that is not a condition object (bad YAML) is kept as one unsupported row, never dropped. */
function nodeFrom(value: unknown, id = uid()): Node {
  if (value !== null && typeof value === "object" && !Array.isArray(value)) {
    return {
      id,
      fromData: true,
      entries: Object.entries(value as Record<string, unknown>).map(([key, item]) =>
        isGroup(key) && Array.isArray(item) ? { id: uid(), key, members: item.map((member) => nodeFrom(member)) } : { id: uid(), key, raw: item },
      ),
    };
  }
  return { id, fromData: true, entries: [{ id: uid(), key: "", raw: value, scalar: true }] };
}

/** The condition the tree holds: complete tests only, in key order; undefined when the condition is absent. */
function project(node: Node | undefined): Record<string, unknown> | undefined {
  if (!node) return undefined;
  const out: Record<string, unknown> = {};
  for (const entry of node.entries) {
    if (entry.scalar) return entry.raw as Record<string, unknown>;
    if (entry.members) {
      const members = entry.members.map(project).filter((member) => member !== undefined);
      if (members.length > 0) out[entry.key] = members;
    } else if (rowComplete(entry.key, entry.raw)) out[entry.key] = entry.raw;
  }
  return Object.keys(out).length > 0 ? out : node.fromData ? {} : undefined;
}

/** Applies `fn` to the node with `id` anywhere in the tree; fn returning undefined drops the node (and its now-empty group). */
function mapNode(node: Node | undefined, id: string, fn: (node: Node) => Node | undefined): Node | undefined {
  if (!node) return undefined;
  if (node.id === id) return fn(node);
  let hit = false;
  const entries: Entry[] = [];
  for (const entry of node.entries) {
    if (!entry.members) {
      entries.push(entry);
      continue;
    }
    const members: Node[] = [];
    for (const member of entry.members) {
      const next = mapNode(member, id, fn);
      if (next !== member) hit = true;
      if (next) members.push(next);
    }
    if (members.length === 0 && entry.members.length > 0) hit = true; // the group lost its last member: drop the group
    else entries.push(members.every((member, at) => member === entry.members?.[at]) ? entry : { ...entry, members });
  }
  // the removal cascades like dropEntry: a node left with no entries is absence, never {} (which would mean "always")
  return hit ? (entries.length > 0 ? { ...node, entries } : undefined) : node;
}

const setEntry = (node: Node, entryId: string, patch: Partial<Entry>): Node => ({
  ...node,
  entries: node.entries.map((entry) => (entry.id === entryId ? { ...entry, ...patch } : entry)),
});
const dropEntry = (node: Node, entryId: string): Node | undefined => {
  const entries = node.entries.filter((entry) => entry.id !== entryId);
  return entries.length > 0 ? { ...node, entries } : undefined;
};

type Ops = {
  addEntry: (nodeId: string, key: string) => void;
  addGroup: (nodeId: string, groupKey: string) => void;
  addMember: (nodeId: string, entryId: string, key: string) => void;
  setValue: (nodeId: string, entryId: string, raw: unknown) => void;
  rename: (nodeId: string, entryId: string, key: string) => void;
  removeEntry: (nodeId: string, entryId: string) => void;
  focus: (chain: (string | null)[]) => void;
};

/** Where a removal leaves focus: the next row, the next member, then the nearest surviving Add button. */
const FOCUSABLE = "input, select, textarea, button, [tabindex]";

type Parent = { groupEntryId: string; parentNodeId: string; nextMemberId?: string };

/** A condition site: the structured builder over the condition object, with an advanced JSON mode. */
export function ConditionField({ schema, name, formData, onChange, fieldPathId, registry, formContext }: Props) {
  const ctx: BuilderContext = formContext ?? registry?.formContext ?? { moves: [], issues: [] };
  const problems = useRef(new Map<string, () => void>());
  const id = fieldPathId.$id;
  const report: DraftReport = (key, invalid, focus) => {
    const map = problems.current;
    if (invalid) map.set(key, focus);
    else map.delete(key);
    conditionDrafts.set(id, { valid: map.size === 0, focus: () => map.values().next().value?.() });
  };
  useEffect(() => {
    conditionDrafts.set(id, { valid: problems.current.size === 0, focus: () => problems.current.values().next().value?.() });
    return () => {
      conditionDrafts.delete(id);
      problems.current.clear();
    };
  }, [id]);

  const [root, setRoot] = useState<Node | undefined>(() => (formData === undefined ? undefined : nodeFrom(formData, ROOT)));
  const sent = useRef(JSON.stringify(formData ?? null));
  const field = useRef<HTMLFieldSetElement>(null);
  const [focusChain, setFocusChain] = useState<(string | null)[] | null>(null);
  useEffect(() => {
    if (!focusChain) return;
    setFocusChain(null);
    for (const selector of focusChain) {
      const found = selector && field.current?.querySelector<HTMLElement>(selector);
      if (!found) continue;
      (found.matches(FOCUSABLE) ? found : found.querySelector<HTMLElement>(FOCUSABLE) ?? found).focus();
      break;
    }
  }, [focusChain]);
  useEffect(() => {
    const incoming = JSON.stringify(formData ?? null);
    if (incoming !== sent.current) {
      // a change from outside the builder (the YAML box): rebuild the tree
      sent.current = incoming;
      setRoot(formData === undefined ? undefined : nodeFrom(formData, ROOT));
    }
  }, [formData]);

  function apply(next: Node | undefined) {
    setRoot(next);
    const value = project(next);
    const wire = JSON.stringify(value ?? null);
    if (wire !== sent.current) {
      sent.current = wire;
      onChange(value, fieldPathId.path);
    }
  }

  /** The JSON box's parsed value becomes the tree and the form data at once. */
  function commitRaw(value: unknown) {
    setRoot(value === undefined ? undefined : nodeFrom(value, ROOT));
    const wire = JSON.stringify(value ?? null);
    if (wire !== sent.current) {
      sent.current = wire;
      onChange(value, fieldPathId.path);
    }
  }

  const ops: Ops = {
    addEntry: (nodeId, key) =>
      apply(mapNode(root, nodeId, (node) => ({ ...node, entries: [...node.entries, { id: uid(), key }] })) ?? { id: ROOT, fromData: false, entries: [{ id: uid(), key }] }),
    addGroup: (nodeId, groupKey) =>
      apply(mapNode(root, nodeId, (node) => ({ ...node, entries: [...node.entries, { id: uid(), key: groupKey, members: [] }] })) ?? { id: ROOT, fromData: false, entries: [{ id: uid(), key: groupKey, members: [] }] }),
    addMember: (nodeId, entryId, key) =>
      apply(
        mapNode(root, nodeId, (node) =>
          setEntry(node, entryId, {
            members: [...(node.entries.find((entry) => entry.id === entryId)?.members ?? []), { id: uid(), fromData: false, entries: [{ id: uid(), key }] }],
          }),
        ),
      ),
    setValue: (nodeId, entryId, raw) => apply(mapNode(root, nodeId, (node) => setEntry(node, entryId, { raw }))),
    rename: (nodeId, entryId, key) => apply(mapNode(root, nodeId, (node) => setEntry(node, entryId, { key }))),
    removeEntry: (nodeId, entryId) => apply(mapNode(root, nodeId, (node) => dropEntry(node, entryId))),
    focus: (chain) => setFocusChain(chain),
  };

  const [json, setJson] = useState(false);
  const [problem, setProblem] = useState<string>();
  const path = fieldPathId.path.map(String);
  const site = siteOf(path);
  // the legend comes from the field's name, humanised: "Reveal when", "When", "Auto-fire when"
  const title = site === "auto" ? "Auto-fire when" : name ? humanise(name) : (schema.title ?? "Condition");
  const hint = schema.description ?? DESCRIPTION;

  return (
    <DraftContext.Provider value={report}>
      <fieldset className="field condition" ref={field}>
        <legend className="card-title">{title}</legend>
        <div className="condition-meta">
          <p className="hint">{hint}</p>
          <button
            type="button"
            className="small ghost condition-json-btn"
            aria-pressed={json}
            onClick={() => {
              if (problems.current.size > 0) {
                // the same guard as the YAML switch: an unfinished draft is never thrown away silently
                setProblem("Fix the condition marked in red before checking or saving");
                problems.current.values().next().value?.();
                return;
              }
              setProblem(undefined);
              setJson(!json);
            }}
          >
            {json ? "Back to the rows" : "Edit as JSON"}
          </button>
        </div>
        {problem && (
          <p role="alert" className="problem">
            {problem}
          </p>
        )}
        {json ? (
          <JsonBox value={project(root)} onCommit={commitRaw} />
        ) : (
          <NodeView node={root} nodeId={ROOT} emptyText={SITE_TEXTS[site].absent} objectText={SITE_TEXTS[site].empty} ctx={ctx} ops={ops} />
        )}
      </fieldset>
    </DraftContext.Provider>
  );
}

const HINT = 'Condition as JSON, for example {"trust_gte": 60} or {"any": [...]}';

/** The advanced JSON box (Plan I's): every change parses into the form data; text that does not parse is kept as typed and blocks Check, Save and the YAML switch. */
function JsonBox({ value, onCommit }: { value: unknown; onCommit: (next: Record<string, unknown> | undefined) => void }) {
  const [text, setText] = useState(value === undefined ? "" : JSON.stringify(value, null, 2));
  const [error, setError] = useState<string>();
  const box = useRef<HTMLTextAreaElement>(null);
  const describedBy = useId();
  useDraft("json", error !== undefined, () => box.current?.focus());

  return (
    <div className="field">
      <textarea
        ref={box}
        className="yaml condition"
        aria-label="Condition JSON"
        aria-invalid={error !== undefined}
        aria-describedby={describedBy}
        spellCheck={false}
        value={text}
        onChange={(event) => {
          const next = event.target.value;
          setText(next);
          const trimmed = next.trim();
          if (!trimmed) {
            setError(undefined);
            onCommit(undefined);
            return;
          }
          try {
            onCommit(JSON.parse(trimmed));
            setError(undefined);
          } catch (failure) {
            setError(`Not valid JSON: ${(failure as Error).message}`);
          }
        }}
      />
      <small id={describedBy} role={error ? "alert" : undefined} className={error ? "problem" : "hint"}>
        {error ?? HINT}
      </small>
    </div>
  );
}

/** The Add controls: a menu of the test kinds this object does not have yet, and the All/Any group buttons. */
function AddControls({
  taken,
  groups = true,
  addRef,
  dataAdd,
  dataAddMember,
  onAdd,
  onAddGroup,
}: {
  taken: Set<string>;
  groups?: boolean;
  addRef?: Ref<HTMLButtonElement>;
  dataAdd?: string;
  dataAddMember?: string;
  onAdd: (key: string) => void;
  onAddGroup?: (groupKey: string) => void;
}) {
  const [menu, setMenu] = useState(false);
  return (
    <div className="condition-add">
      <button ref={addRef} type="button" aria-expanded={menu} data-add={dataAdd} data-add-member={dataAddMember} onClick={() => setMenu(!menu)}>
        Add test
      </button>
      {menu && (
        <div className="add-menu">
          {KINDS.filter((kind) => !taken.has(kind)).map((kind) => (
            <button
              key={kind}
              type="button"
              onClick={() => {
                setMenu(false);
                onAdd(kind);
              }}
            >
              {rowLabel(kind)}
            </button>
          ))}
        </div>
      )}
      {groups && onAddGroup && !taken.has("all") && (
        <button type="button" onClick={() => onAddGroup("all")}>
          Add 'all of' group
        </button>
      )}
      {groups && onAddGroup && !taken.has("any") && (
        <button type="button" onClick={() => onAddGroup("any")}>
          Add 'any of' group
        </button>
      )}
    </div>
  );
}

/** An All/Any group: its member conditions and the Add controls; an empty group is an incomplete draft. */
function GroupView({ entry, nodeId, ctx, ops, onRemove }: { entry: Entry; nodeId: string; ctx: BuilderContext; ops: Ops; onRemove: () => void }) {
  const add = useRef<HTMLButtonElement>(null);
  const members = entry.members ?? [];
  useDraft(`${entry.id}:group`, members.length === 0, () => add.current?.focus());
  return (
    <ConditionGroup groupKey={entry.key} onRemove={onRemove}>
      {members.map((member, index) => (
        <NodeView
          key={member.id}
          node={member}
          nodeId={member.id}
          emptyText="Always"
          objectText="Always"
          ctx={ctx}
          ops={ops}
          parent={{ groupEntryId: entry.id, parentNodeId: nodeId, nextMemberId: members[index + 1]?.id }}
        />
      ))}
      <AddControls taken={new Set()} addRef={add} dataAddMember={entry.id} onAdd={(key) => ops.addMember(nodeId, entry.id, key)} />
    </ConditionGroup>
  );
}
/** One condition object: its rows and groups, "All of these" when there is more than one, and the Add controls. */
function NodeView({ node, nodeId, emptyText, objectText, ctx, ops, parent }: { node: Node | undefined; nodeId: string; emptyText: string; objectText: string; ctx: BuilderContext; ops: Ops; parent?: Parent }) {
  const entries = node?.entries ?? [];
  const taken = new Set(entries.map((entry) => entry.key));

  /** Focus after a removal: the next row, the next member, the group's Add button, the parent's Add button. */
  function removed(index: number) {
    const next = entries[index + 1];
    ops.focus([
      next ? `[data-entry="${next.id}"]` : null,
      parent?.nextMemberId ? `[data-node="${parent.nextMemberId}"]` : null,
      `[data-add="${nodeId}"]`,
      parent ? `[data-add-member="${parent.groupEntryId}"]` : null,
      parent ? `[data-add="${parent.parentNodeId}"]` : null,
      `[data-add="${ROOT}"]`,
    ]);
  }

  const nodes: ReactNode[] = entries.map((entry, index) => (
    <div key={entry.id} data-entry={entry.id}>
      {entry.members ? (
        <GroupView
          entry={entry}
          nodeId={nodeId}
          ctx={ctx}
          ops={ops}
          onRemove={() => {
            removed(index);
            ops.removeEntry(nodeId, entry.id);
          }}
        />
      ) : (
        <ConditionRow
          draftId={entry.id}
          name={entry.key}
          value={entry.raw}
          ctx={ctx}
          taken={taken}
          onValue={(raw) => ops.setValue(nodeId, entry.id, raw)}
          onRename={(key) => ops.rename(nodeId, entry.id, key)}
          onRemove={() => {
            removed(index);
            ops.removeEntry(nodeId, entry.id);
          }}
        />
      )}
    </div>
  ));

  let main: ReactNode;
  if (nodes.length === 0) main = <p className="hint">{node === undefined ? emptyText : objectText}</p>;
  else if (nodes.length === 1) main = nodes[0];
  else
    main = (
      <fieldset className="condition-group">
        <legend>All of these</legend>
        {nodes}
      </fieldset>
    );

  return (
    <div className="condition-body" data-node={nodeId}>
      {main}
      <AddControls
        taken={taken}
        dataAdd={nodeId}
        onAdd={(key) => ops.addEntry(nodeId, key)}
        onAddGroup={(groupKey) => ops.addGroup(nodeId, groupKey)}
      />
    </div>
  );
}
