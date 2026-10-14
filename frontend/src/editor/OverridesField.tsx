import type { FieldProps } from "@rjsf/utils";
import { useEffect, useRef, useState } from "react";
import type { S } from "../api/client";
import { label } from "../ui";
import { conditionDrafts } from "./drafts";
import type { EditorContext } from "./SectionTemplate";

type MoveOverrides = {
  deltas?: Record<string, number>;
  [key: string]: any;
};

type OverridesData = {
  moves?: Record<string, MoveOverrides>;
  classifier_moves?: Record<string, boolean>;
  [key: string]: any;
};

export function OverridesField(props: FieldProps<OverridesData>) {
  const { formData, onChange, registry, fieldPathId } = props;
  const path = fieldPathId?.path ?? ["overrides"];
  const fieldId = fieldPathId?.$id ?? "root_overrides";
  const ctx = registry.formContext as EditorContext | undefined;
  const rulesData = ctx?.rulesData;
  const [showJson, setShowJson] = useState(false);
  const [jsonText, setJsonText] = useState("");
  const [jsonError, setJsonError] = useState<string>();
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    return () => {
      conditionDrafts.delete(fieldId);
    };
  }, [fieldId]);

  if (!rulesData) {
    return (
      <div className="field overrides">
        <p className="hint">Loading rules definitions…</p>
      </div>
    );
  }

  const moves = rulesData.moves ?? [];
  const dials = rulesData.dials ?? [];
  const currentMoves = formData?.moves ?? {};

  function getMoveDeltas(moveId: string): Record<string, number> | undefined {
    const raw = currentMoves[moveId];
    if (!raw) return undefined;
    if (raw.deltas && typeof raw.deltas === "object") return raw.deltas;
    return raw as Record<string, number>;
  }

  function handleDeltaChange(move: S["MoveOut"], dial: string, val: number) {
    const existing = getMoveDeltas(move.id) ?? {};
    const inheritedVal = move.deltas[dial] ?? 0;

    const nextDeltas = { ...existing };
    if (val === inheritedVal) {
      delete nextDeltas[dial];
    } else {
      nextDeltas[dial] = val;
    }

    const nextMoves = { ...currentMoves };
    if (Object.keys(nextDeltas).length === 0) {
      delete nextMoves[move.id];
    } else {
      nextMoves[move.id] = { deltas: nextDeltas };
    }

    const nextFormData = { ...formData };
    if (Object.keys(nextMoves).length === 0) {
      delete nextFormData.moves;
    } else {
      nextFormData.moves = nextMoves;
    }
    onChange(Object.keys(nextFormData).length > 0 ? nextFormData : undefined, path);
  }

  function handleReset(moveId: string) {
    const nextMoves = { ...currentMoves };
    delete nextMoves[moveId];
    const nextFormData = { ...formData };
    if (Object.keys(nextMoves).length === 0) {
      delete nextFormData.moves;
    } else {
      nextFormData.moves = nextMoves;
    }
    onChange(Object.keys(nextFormData).length > 0 ? nextFormData : undefined, path);
  }

  const classifierMoves = formData?.classifier_moves ?? {};

  function handleClassifierToggle(moveId: string, enabled: boolean) {
    const nextClassifier = { ...classifierMoves };
    if (enabled) {
      delete nextClassifier[moveId];
    } else {
      nextClassifier[moveId] = false;
    }
    const nextFormData = { ...formData };
    if (Object.keys(nextClassifier).length === 0) {
      delete nextFormData.classifier_moves;
    } else {
      nextFormData.classifier_moves = nextClassifier;
    }
    onChange(Object.keys(nextFormData).length > 0 ? nextFormData : undefined, path);
  }

  function toggleJson() {
    if (!showJson) {
      setJsonText(JSON.stringify(formData ?? {}, null, 2));
      setJsonError(undefined);
      conditionDrafts.delete(fieldId);
      setShowJson(true);
    } else {
      if (jsonError) {
        textareaRef.current?.focus();
        return;
      }
      conditionDrafts.delete(fieldId);
      setShowJson(false);
    }
  }

  function handleJsonChange(text: string) {
    setJsonText(text);
    const trimmed = text.trim();
    if (!trimmed) {
      setJsonError(undefined);
      conditionDrafts.delete(fieldId);
      onChange(undefined, path);
      return;
    }
    try {
      const parsed = JSON.parse(trimmed);
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        throw new Error("Overrides must be an object");
      }
      setJsonError(undefined);
      conditionDrafts.delete(fieldId);
      onChange(Object.keys(parsed).length > 0 ? parsed : undefined, path);
    } catch (err) {
      setJsonError((err as Error).message);
      conditionDrafts.set(fieldId, {
        valid: false,
        focus: () => textareaRef.current?.focus(),
      });
    }
  }

  return (
    <div className="field overrides">
      <div className="overrides-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
        <div>
          <h3 style={{ margin: "0 0 4px 0" }}>Behaviour for this scenario</h3>
          <p className="hint" style={{ margin: 0 }}>
            Custom dial deltas for this counterpart. Values replace the standard rules for this scenario only.
          </p>
        </div>
        <button type="button" className="small secondary" onClick={toggleJson}>
          {showJson ? "Back to table" : "Edit as JSON"}
        </button>
      </div>

      {showJson ? (
        <div>
          <textarea
            ref={textareaRef}
            className="condition-json"
            aria-label="Overrides JSON"
            aria-invalid={jsonError !== undefined}
            rows={8}
            value={jsonText}
            onChange={(e) => handleJsonChange(e.target.value)}
          />
          {jsonError && (
            <p role="alert" className="error" style={{ color: "var(--danger, #DA4167)" }}>
              {jsonError}
            </p>
          )}
        </div>
      ) : (

        <div style={{ overflowX: "auto" }}>
          <table className="rules scenario-overrides">
            <thead>
              <tr>
                <th>Move</th>
                {dials.map((dial) => (
                  <th key={dial}>{label(dial)}</th>
                ))}
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {moves.map((move) => {
                const moveDeltas = getMoveDeltas(move.id);
                const isOverridden = moveDeltas !== undefined && Object.keys(moveDeltas).length > 0;
                return (
                  <tr key={move.id} className={isOverridden ? "changed" : undefined}>
                    <th scope="row" title={move.id}>
                      {move.description}
                      {move.ends_session && " (ends the session)"}
                    </th>
                    {dials.map((dial) => {
                      const overriddenVal = moveDeltas?.[dial];
                      const isDialOverridden = overriddenVal !== undefined;
                      const displayVal = isDialOverridden ? overriddenVal : (move.deltas[dial] ?? 0);

                      return (
                        <td key={dial} className={isDialOverridden ? "overridden" : "inherited"}>
                          <input
                            type="number"
                            step={1}
                            aria-label={`${move.id} ${dial}`}
                            value={displayVal}
                            onChange={(e) => handleDeltaChange(move, dial, Number(e.target.value))}
                          />
                        </td>
                      );
                    })}
                    <td>
                      {isOverridden && (
                        <button
                          type="button"
                          className="small secondary"
                          onClick={() => handleReset(move.id)}
                          aria-label={`Reset ${move.id} to standard rules`}
                        >
                          Reset
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          <div className="classifier-moves-section" style={{ marginTop: "24px", paddingTop: "16px", borderTop: "1px solid var(--border, #333)" }}>
            <h4 style={{ margin: "0 0 4px 0" }}>Classifier move detection</h4>
            <p className="hint" style={{ margin: "0 0 12px 0" }}>
              Enable or disable specific classifier move detection for this scenario. Disabled moves will not be judged or triggered.
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "8px" }}>
              {moves.map((move) => {
                const isEnabled = classifierMoves[move.id] !== false;
                return (
                  <label
                    key={move.id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "10px",
                      padding: "8px 10px",
                      background: isEnabled ? "var(--bg-subtle, rgba(255,255,255,0.03))" : "rgba(255,0,0,0.05)",
                      border: "1px solid var(--border-color, rgba(255,255,255,0.1))",
                      borderRadius: "6px",
                      cursor: "pointer",
                    }}
                  >
                    <input
                      type="checkbox"
                      className="classifier-move-check"
                      checked={isEnabled}
                      onChange={(e) => handleClassifierToggle(move.id, e.target.checked)}
                      aria-label={`Toggle classifier detection for ${move.id}`}
                    />
                    <div>
                      <span className="mono" style={{ fontSize: "12px", fontWeight: 600, display: "block" }}>{move.id}</span>
                      <span className="hint" style={{ fontSize: "11px", margin: 0, display: "block" }}>
                        Detection: {isEnabled ? "enabled" : "disabled"}
                      </span>
                    </div>
                  </label>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
