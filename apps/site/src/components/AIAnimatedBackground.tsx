/** Gemini-style aurora behind the hero. Hidden from assistive tech. */
export function AIAnimatedBackground() {
  return (
    <div className="ai-ambient" aria-hidden="true">
      <div className="ai-ambient-mesh" />
      <div className="ai-ambient-field ai-ambient-orange" />
      <div className="ai-ambient-field ai-ambient-violet" />
      <div className="ai-ambient-field ai-ambient-blue" />
      <div className="ai-ambient-field ai-ambient-amber" />
      <div className="ai-ambient-grain" />
    </div>
  );
}
