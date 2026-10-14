/** Dials over time: one line per dial, dashed marks for twists (orange), overrides (grey) and flags (red).
 * A click selects the turn under review. Ported from the POC. */
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { TrainerView } from "./progress";

const DIAL_COLORS = ["#b8df83", "#56A3A6", "#F78764", "#c39bd3", "#e5d36e", "#8fd3c7"];
const DIAL_COLOR: Record<string, string> = { trust: "#b8df83", rigidity: "#56A3A6", hostility: "#DA4167", consistency: "#c39bd3" };
const MARK_KINDS = [
  { key: "twist", color: "#F78764" },
  { key: "override", color: "#cbd5cf" },
  { key: "flag", color: "#DA4167" },
] as const;

// The dials after each turn, one chart row per turn: the saved snapshot plus any dial events appended to that turn
// after the snapshot was written (trainer overrides and preset twist deltas land that way).
export function dialRows(view: TrainerView) {
  return view.dialsByTurn.map(({ turn, dials }) => {
    const row: Record<string, number> = { turn, ...dials };
    for (const event of view.state.log) {
      if (event.turn === turn && event.kind === "dial" && event.dial && event.after != null) row[event.dial] = event.after;
    }
    return row;
  });
}

// One dashed line per turn and kind, so several overrides in the same turn share a single label.
export function timelineMarks(view: TrainerView) {
  const { state } = view;
  const found: Record<(typeof MARK_KINDS)[number]["key"], string[]> = {
    twist: state.injections.map((item) => `${item.turn}|${item.label}`),
    override: state.log.filter((item) => item.source === "trainer" && item.dial).map((item) => `${item.turn}|${item.dial}`),
    flag: state.flags.map((item) => `${item.turn}|${item.id.replaceAll("_", " ")}`),
  };
  return MARK_KINDS.flatMap(({ key, color }, row) => {
    const byTurn = new Map<number, string[]>();
    found[key].forEach((entry) => {
      const [turn, text] = entry.split("|");
      byTurn.set(Number(turn), [...(byTurn.get(Number(turn)) || []), text.replaceAll("_", " ")]);
    });
    return [...byTurn].map(([turn, texts]) => ({
      turn,
      color,
      row,
      label: key === "override" ? `override: ${texts.join(", ")}` : texts.join("; "),
    }));
  });
}

export function DialChart({ view, turn, onPick }: { view: TrainerView; turn: number; onPick: (turn: number) => void }) {
  const rows = dialRows(view);
  const dials = [...new Set(rows.flatMap((row) => Object.keys(row)))].filter((key) => key !== "turn");
  return (
    <section className="card">
      <div className="eyebrow">Trajectory</div>
      <h2>Dials over time</h2>
      <ResponsiveContainer width="100%" height={360}>
        <LineChart
          data={rows}
          margin={{ top: 56, right: 28, bottom: 8, left: 0 }}
          style={{ cursor: "pointer" }}
          onClick={(event) => {
            const picked = Number(event?.activeLabel);
            if (Number.isFinite(picked)) onPick(picked);
          }}
        >
          <CartesianGrid stroke="#34463a" strokeDasharray="3 3" />
          <XAxis
            dataKey="turn"
            type="number"
            domain={[0, Math.max(1, view.state.turn)]}
            ticks={rows.map((row) => row.turn)}
            allowDecimals={false}
            stroke="#9bb09f"
          />
          <YAxis domain={[0, 100]} stroke="#9bb09f" />
          <Tooltip
            contentStyle={{ background: "#111c16", border: "1px solid #405448", borderRadius: 9 }}
            labelFormatter={(turn) => `Turn ${turn}`}
          />
          <Legend formatter={(value) => String(value).replaceAll("_", " ")} />
          {timelineMarks(view).map((mark) => (
            <ReferenceLine
              key={`${mark.row}-${mark.turn}`}
              x={mark.turn}
              stroke={mark.color}
              strokeDasharray="4 4"
              label={{ value: mark.label, position: "top", offset: 6 + mark.row * 16, fill: mark.color, fontSize: 11 }}
            />
          ))}
          <ReferenceLine x={turn} stroke="#ecf2e9" strokeOpacity={0.35} strokeWidth={10} />
          {dials.map((dial, i) => (
            <Line
              key={dial}
              type="linear"
              dataKey={dial}
              stroke={DIAL_COLOR[dial] ?? DIAL_COLORS[i % DIAL_COLORS.length]}
              strokeWidth={2.5}
              dot={{ r: 3 }}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
      <p className="hint">
        Click a turn to review it on the right. Dashed lines mark events: orange = injection, grey = trainer override,
        red = flag. Solid lines are the dials: hostility is red (higher is worse); consistency is violet and stays at
        100 while the trainee makes sense.
      </p>
    </section>
  );
}
