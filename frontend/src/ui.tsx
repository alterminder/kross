import { Fragment, type ReactNode } from "react";
import { appUrl, apiUrl } from "./api/client";

export function label(key: string): string {
  const text = key.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function coverUrl(cover: string): string {
  return appUrl(`covers/${cover}.webp`);
}

/** A scenario card's cover: its painted cover when it is the chosen one and exists, else the theme image. The
 * version in the URL busts the cache whenever the image is saved. */
export function cardCover(card: { id: string; cover: string; cover_image_version?: string | null }): string {
  return card.cover === "custom" && card.cover_image_version
    ? apiUrl(`scenarios/${card.id}/cover-image?v=${encodeURIComponent(card.cover_image_version)}`)
    : coverUrl(card.cover === "custom" ? "field" : card.cover);
}

export function Problem({ text }: { text?: string }) {
  return text ? (
    <p role="alert" className="problem">
      {text}
    </p>
  ) : null;
}

/** Any JSON value, readably. The engine's and the model's dicts (briefs, events, scores, debriefs) have shapes the
 * UI should not hard-code. */
export function Value({ value }: { value: unknown }): ReactNode {
  if (value === null || value === undefined || value === "") return <span className="muted">—</span>;
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="muted">none</span>;
    return (
      <ul>
        {value.map((item, index) => (
          <li key={index}>
            <Value value={item} />
          </li>
        ))}
      </ul>
    );
  }
  if (typeof value === "object") {
    return (
      <dl>
        {Object.entries(value).map(([key, item]) => (
          <Fragment key={key}>
            <dt>{label(key)}</dt>
            <dd>
              <Value value={item} />
            </dd>
          </Fragment>
        ))}
      </dl>
    );
  }
  return <>{String(value)}</>;
}

/** A table of flat rows, columns from the first row's keys. Amounts in USD show two decimals. */
export function Table({ rows }: { rows: Record<string, unknown>[] }) {
  if (rows.length === 0) return <p className="muted">Nothing yet.</p>;
  const keys = Object.keys(rows[0]);
  return (
    <table>
      <thead>
        <tr>
          {keys.map((key) => (
            <th key={key}>{label(key)}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <tr key={index}>
            {keys.map((key) => (
              <td key={key}>{typeof row[key] === "number" && key.endsWith("usd") ? (row[key] as number).toFixed(2) : String(row[key] ?? "—")}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
