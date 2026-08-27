export function NotBuilt({ task, what, blocks }: { task: string; what: string; blocks: string }) {
  return (
    <div className="not-built" role="status">
      <strong>Not yet implemented</strong>
      <span>{what}</span>
      <small>{task} · Requires: {blocks}</small>
    </div>
  )
}
