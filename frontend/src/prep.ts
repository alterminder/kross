/** Strategic preparation (Naivasha Grid) visibility, in one place.
 *
 * Build-time flag: preparation controls are hidden unless the build sets VITE_HIDE_PREP=0
 * (`VITE_HIDE_PREP=0 npm run build`, or in `vite dev`'s environment). Any other value, or no
 * value, hides them. The flag hides authoring and play controls only: saved preparation data
 * and its debrief section are kept and still shown. */
export function hidePrep(): boolean {
  return import.meta.env.VITE_HIDE_PREP !== "0";
}
