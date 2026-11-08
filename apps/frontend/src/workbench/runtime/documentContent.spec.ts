import { describe, expect, it } from 'vitest'
import { documentEntries, reportContent, withoutRepeatedTitle } from './documentContent'

describe('workspace document presentation', () => {
  it('uses the formal final artifact when a report also has mirrored output fields', () => {
    const report = '# 故障恢复方案\n\n只展示这份正文。'
    expect(reportContent({ artifact: { artifactType: 'run_deliverable', content: report },
      artifacts: [{ artifactType: 'run_deliverable', content: report }], final_answer: report, summary: '另一份摘要' })).toBe(report)
  })
  it('only removes identical narrative aliases within one object', () => {
    const object = { summary: '相同摘要', overview: '相同摘要', description: '不同说明', count: 3, limit: 3,
      first: { rule: '共同约束' }, second: { rule: '共同约束' } }
    expect(documentEntries(object).map(([key]) => key)).toEqual(['summary', 'description', 'count', 'limit', 'first', 'second'])
    expect(object.overview).toBe('相同摘要')
  })
  it('does not choose one document arbitrarily when multiple final bodies differ', () => {
    const value = { artifacts: [
      { artifactType: 'run_deliverable', content: '第一份报告' },
      { artifactType: 'run_deliverable', content: '另一份报告' }
    ] }
    expect(reportContent(value)).toBe('')
    expect(documentEntries(value)).toEqual([['artifacts', value.artifacts]])
  })
  it('removes only a matching leading title, preserving distinct and later headings', () => {
    expect(withoutRepeatedTitle('# 同一标题\n\n## 内容\n正文', '同一标题')).toBe('## 内容\n正文')
    expect(withoutRepeatedTitle('# 另一标题\n正文', '主标题')).toBe('# 另一标题\n正文')
    expect(withoutRepeatedTitle('正文\n\n# 同一标题', '同一标题')).toBe('正文\n\n# 同一标题')
  })
})
