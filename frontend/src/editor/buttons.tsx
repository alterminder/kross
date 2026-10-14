import { getUiOptions, type IconButtonProps } from "@rjsf/utils";

type Props = IconButtonProps & { title?: string };

/** The list a button acts on and its item number, from rjsf's button id (root_counterparts_0_hidden_interests_1__remove). */
function listOf(id?: string): { list?: string; index?: number } {
  const parts = (id ?? "").replace(/_+[a-zA-Z]+$/, "").split("_");
  let at = parts.length - 1;
  if (!/^\d+$/.test(parts[at] ?? "")) return { list: parts[at] }; // no item index (e.g. the Add button)
  const index = Number(parts[at]);
  let start = at; // the list name is what sits between the previous index and this one
  while (start > 0 && !/^\d+$/.test(parts[start - 1]) && parts[start - 1] !== "root") start--;
  return { list: parts.slice(start, at).join("_") || undefined, index };
}

/** The map's row wording ("Hidden fact"), else the humanised list name; plus the row number -> "Hidden fact 2". */
function itemLabel(id?: string, title?: string): string {
  const { list, index } = listOf(id);
  const human = title ?? (list ? list.split("_").join(" ").replace(/s$/, "") : "item");
  return index === undefined ? human : `${human} ${index + 1}`;
}

/** The row name the buttons act on: the item's uiSchema title from the labels map wins over the id guess. */
function itemOf(props: Props): string {
  const title = getUiOptions(props.uiSchema).title as string | undefined;
  return itemLabel(props.id, title ?? props.title);
}

/** rjsf's default icon buttons draw Bootstrap glyphicons this app does not ship: readable text buttons instead. */
function readable({ text, name, danger, icon, iconType, uiSchema, registry, className, title, ...rest }: Omit<Props, "children"> & { text: string; name: string; danger?: boolean }) {
  return (
    <button type="button" aria-label={name} title={name} className={`small ${danger ? "danger" : "ghost"} ${className ?? ""}`} {...rest}>
      {text}
    </button>
  );
}

export const ButtonTemplates = {
  AddButton: (props: Props) => {
    const wanted = (props.uiSchema as Record<string, unknown> | undefined)?.["ui:addButtonText"];
    const label = typeof wanted === "string" ? wanted : `Add ${itemLabel(props.id)}`;
    return readable({ ...props, text: `+ ${label}`, name: `+ ${label}` });
  },
  MoveUpButton: (props: Props) => readable({ ...props, text: "↑", name: `Move ${itemOf(props)} up` }),
  MoveDownButton: (props: Props) => readable({ ...props, text: "↓", name: `Move ${itemOf(props)} down` }),
  RemoveButton: (props: Props) => readable({ ...props, text: "×", name: `Remove ${itemOf(props)}` }),
  CopyButton: (props: Props) => readable({ ...props, text: "⧉ Copy", name: `Copy ${itemOf(props)}` }),
  ClearButton: (props: Props) => readable({ ...props, text: "Clear", name: "Clear" }),
};
