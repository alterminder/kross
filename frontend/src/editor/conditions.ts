import type { UiSchema } from "@rjsf/utils";

type Node = Record<string, any>;

const CONDITION_REF = "#/$defs/condition";

/**
 * A uiSchema that renders every condition site (any node that is `$ref: #/$defs/condition` under `properties` or
 * `items`) as the `condition` field. Sites are found by walking the served schema, so a new site is covered by
 * this walk alone. The walk resolves `$ref`s to other defs and never descends into `$defs/condition` itself.
 */
export function conditionUiSchema(schema: unknown): UiSchema {
  const root = (schema ?? {}) as Node;
  const defs = (root.$defs ?? {}) as Record<string, Node>;

  /** Fills `target` with the marks under `node`'s properties and items; `visited` stops def recursion. */
  function walk(node: Node, target: Node, visited: Set<string>) {
    function each(key: string, child: Node) {
      if (child.$ref === CONDITION_REF) {
        target[key] = { "ui:field": "condition" };
        return;
      }
      let resolved = child;
      let next = visited;
      if (typeof child.$ref === "string") {
        const name = child.$ref.replace("#/$defs/", "");
        if (visited.has(name)) return;
        resolved = defs[name];
        if (!resolved) return;
        next = new Set(visited).add(name);
      }
      const sub: Node = {};
      walk(resolved, sub, next);
      if (Object.keys(sub).length > 0) target[key] = sub;
    }

    for (const [key, child] of Object.entries((node.properties ?? {}) as Record<string, Node>)) each(key, child);
    if (node.items) each("items", node.items as Node);
  }

  const out: Node = {};
  walk(root, out, new Set());
  return out as UiSchema;
}
