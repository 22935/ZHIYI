/** Choose one readable representation; the original output and its evidence stay intact. */
const reportKeys = ['final_report', 'report_markdown', 'final_answer', 'finalAnswer', 'report']
const narrativeAliases = new Set([...reportKeys, 'summary', 'overview', 'description', 'content', 'text', 'title', 'name'])
const record = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value)

export function reportContent(value: unknown): string {
  if (!record(value)) return ''
  const artifacts = [value.artifact, ...(Array.isArray(value.artifacts) ? value.artifacts : [])].filter(record)
  const bodies = artifacts.filter(item => item.artifactType === 'run_deliverable' || item.artifactKey === 'final')
    .map(item => typeof item.content === 'string' ? item.content.trim() : '').filter(Boolean)
  const distinct = [...new Set(bodies)]
  if (distinct.length === 1) return distinct[0]
  for (const key of reportKeys) {
    const content = value[key]
    if (typeof content === 'string' && content.trim()) return content.trim()
  }
  return ''
}

/** Only coalesce identical narrative aliases in one object, never repeated facts in different sections. */
export function documentEntries(value: Record<string, unknown>): Array<[string, unknown]> {
  const seen = new Set<string>()
  return Object.entries(value).filter(([key, item]) => {
    if (!narrativeAliases.has(key) || typeof item !== 'string' || !item.trim()) return true
    const signature = item.trim()
    if (seen.has(signature)) return false
    seen.add(signature)
    return true
  })
}

/** The document heading already appears in the editor; keep distinct subsection headings. */
export function withoutRepeatedTitle(content: string, title?: string): string {
  if (!title) return content
  const heading = content.match(/^\s*#{1,3}\s+([^\n]+)(?:\n|$)/)
  return heading?.[1].trim() === title.trim() ? content.slice(heading[0].length).trimStart() : content
}
