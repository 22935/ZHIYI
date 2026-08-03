const escapeHtml = (raw: string) => raw
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#39;')

const isSafeUrl = (url: string) => /^(https?:\/\/|mailto:|\/)/i.test(url)

const renderInline = (raw: string) => {
  let text = escapeHtml(raw)
  text = text.replace(/\[([^\]]+)]\(([^)]+)\)/g, (_all, label, url) => {
    const safeUrl = String(url || '').trim()
    if (!isSafeUrl(safeUrl)) return label
    return `<a href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer">${label}</a>`
  })
  text = text.replace(/`([^`]+)`/g, '<code>$1</code>')
  text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  text = text.replace(/__([^_]+)__/g, '<strong>$1</strong>')
  text = text.replace(/\*([^*]+)\*/g, '<em>$1</em>')
  return text
}

const tableCells = (line: string) => line
  .trim()
  .replace(/^\|/, '')
  .replace(/\|$/, '')
  .split('|')
  .map(cell => cell.trim())

const isTableDivider = (line: string) => {
  const cells = tableCells(line)
  return cells.length > 0 && cells.every(cell => /^:?-{3,}:?$/.test(cell))
}

/**
 * Render the Markdown subset emitted by workflow reports without trusting raw HTML.
 * All source text is escaped before inline formatting is applied.
 */
export const renderMarkdown = (raw: string): string => {
  if (!raw) return ''

  const codeBlocks: string[] = []
  const stripped = raw.replace(/```([a-zA-Z0-9_-]+)?\n?([\s\S]*?)```/g, (_match, lang, code) => {
    const language = String(lang || '').trim()
    const className = language ? ` class="language-${escapeHtml(language)}"` : ''
    const token = `@@CODE_BLOCK_${codeBlocks.length}@@`
    codeBlocks.push(`<pre><code${className}>${escapeHtml(String(code || '').replace(/\n$/, ''))}</code></pre>`)
    return token
  })

  const lines = stripped.split(/\r?\n/)
  const output: string[] = []
  let listType: 'ul' | 'ol' | null = null

  const closeList = () => {
    if (!listType) return
    output.push(`</${listType}>`)
    listType = null
  }

  const openList = (type: 'ul' | 'ol') => {
    if (listType === type) return
    closeList()
    output.push(`<${type}>`)
    listType = type
  }

  for (let index = 0; index < lines.length; index += 1) {
    const trimmed = lines[index].trim()
    if (!trimmed) {
      closeList()
      continue
    }

    if (/^@@CODE_BLOCK_\d+@@$/.test(trimmed)) {
      closeList()
      output.push(trimmed)
      continue
    }

    if (trimmed.includes('|') && index + 1 < lines.length && isTableDivider(lines[index + 1])) {
      closeList()
      const headers = tableCells(trimmed)
      const rows: string[][] = []
      index += 2
      while (index < lines.length && lines[index].trim() && lines[index].includes('|')) {
        rows.push(tableCells(lines[index]))
        index += 1
      }
      index -= 1
      output.push(
        '<div class="markdown-table-wrap"><table><thead><tr>',
        ...headers.map(cell => `<th>${renderInline(cell)}</th>`),
        '</tr></thead><tbody>',
        ...rows.map(row => `<tr>${headers.map((_, cellIndex) => `<td>${renderInline(row[cellIndex] || '')}</td>`).join('')}</tr>`),
        '</tbody></table></div>'
      )
      continue
    }

    const heading = trimmed.match(/^(#{1,6})\s+(.+)$/)
    if (heading) {
      closeList()
      const level = heading[1].length
      output.push(`<h${level}>${renderInline(heading[2])}</h${level}>`)
      continue
    }

    if (/^(-{3,}|\*{3,})$/.test(trimmed)) {
      closeList()
      output.push('<hr>')
      continue
    }

    const unorderedItem = trimmed.match(/^[-*+]\s+(.+)$/)
    if (unorderedItem) {
      openList('ul')
      output.push(`<li>${renderInline(unorderedItem[1])}</li>`)
      continue
    }

    const orderedItem = trimmed.match(/^\d+[.)]\s+(.+)$/)
    if (orderedItem) {
      openList('ol')
      output.push(`<li>${renderInline(orderedItem[1])}</li>`)
      continue
    }

    const quote = trimmed.match(/^>\s?(.*)$/)
    if (quote) {
      closeList()
      output.push(`<blockquote>${renderInline(quote[1])}</blockquote>`)
      continue
    }

    closeList()
    output.push(`<p>${renderInline(trimmed)}</p>`)
  }

  closeList()
  let html = output.join('\n')
  codeBlocks.forEach((block, index) => {
    html = html.replace(`@@CODE_BLOCK_${index}@@`, block)
  })
  return html
}
