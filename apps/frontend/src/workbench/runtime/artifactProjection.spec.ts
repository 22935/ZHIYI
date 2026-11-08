import { describe, expect, it } from 'vitest'
import type { WorkspaceEntry } from '@/services/api/agentos'
import { projectArtifactDocument, renderArtifactDocument, resolveArtifactKind } from './artifactProjection'

const entry: WorkspaceEntry = {
  entryId: 'task:requirements',
  kind: 'task',
  name: '硬约束需求',
  title: '硬约束需求',
  group: 'steps',
  displayOrder: 0,
  semanticTaskKey: 'requirement_analysis',
  objective: '将15项硬约束转化为可测试需求与验收标准。',
  dependencyKeys: ['input:constraints'],
  metadata: { outputRef: 'output:requirements' }
}

const output = {
  requirements: [{
    id: 'REQ-03',
    requirement: '试生产及爬坡周期不超过 6 周，并给出逐周产量与节拍目标。',
    priority: '高',
    source: 'constraint:03'
  }],
  acceptance_criteria: [{
    requirement_id: 'REQ-03',
    metric: '试生产 + 爬坡周数',
    target: '≤ 6 周',
    criterion: '逐周产量与节拍目标均已给出。',
    evidence_ref: 'evidence:constraint:03'
  }],
  assumptions: ['周定义采用自然周']
}

describe('artifactProjection', () => {
  it('keeps verification separate from execution and deduplicates nested source references', () => {
    const document = projectArtifactDocument({ entry: { ...entry, semanticTaskKey: 'final_report' }, output: {
      final_answer: '# 报告\n正文',
      verification: { status: 'partial', checks: [{ criterion: '恢复测试', result: '未执行', evidence: '仅有测试设计' }], unresolvedGaps: ['缺少实测结果'] },
      deliverable: { sourceRefs: ['source:1', 'source:2'] },
      artifact: { structuredData: { sourceRefs: ['source:1', 'source:3'] } },
      artifacts: [{ structuredData: { sourceRefs: ['source:3'] } }]
    } })
    expect(document.verification).toEqual({ status: 'partial', checks: [{ criterion: '恢复测试', result: '未执行', evidence: '仅有测试设计' }], unresolvedGaps: ['缺少实测结果'] })
    expect(document.inspector.evidenceRefs).toEqual(['source:1', 'source:2', 'source:3'])
    expect(renderArtifactDocument(document)).toBe('# 报告\n正文')
    expect(projectArtifactDocument({ entry, output: {} }).verification).toBeNull()
  })

  it('associates confidence and sources with each claim instead of treating the first as global', () => {
    const document = projectArtifactDocument({ entry: { ...entry, semanticTaskKey: 'evidence_assessment' }, output: { evidence_analysis: [
      { claim: '高置信结论', assessment: '有输入依据', confidence: 0.9, evidence_ref: 'source:high' },
      { claim: '低置信结论', assessment: '尚待确认', confidence: 0.3, evidence_ref: 'source:low' },
      { claim: '零置信结论', assessment: '无证据', confidence: 0 },
    ] } })
    const markdown = renderArtifactDocument(document)
    expect(markdown).toMatch(/高置信结论[\s\S]*90%[\s\S]*source:high[\s\S]*低置信结论[\s\S]*30%[\s\S]*source:low/)
    expect(markdown).toContain('0%')
    expect(document.inspector.confidence).toBeNull()
  })

  it('shows a complete report once rather than repeating its summary and structured mirror', () => {
    const report = '# 恢复报告\n\n## 检查\n只进行一次检查。'
    const document = projectArtifactDocument({ entry: { ...entry, semanticTaskKey: 'final_report' }, output: {
      summary: '摘要不能代替完整报告', final_answer: report,
      artifact: { artifactType: 'run_deliverable', content: report },
      artifacts: [{ artifactType: 'run_deliverable', content: report }],
      sections: [{ title: '检查', content: '只进行一次检查。' }]
    } })
    const markdown = renderArtifactDocument(document)
    expect(markdown).toBe(report)
    expect(document.title).toBe('恢复报告')
    expect(markdown.split('只进行一次检查。')).toHaveLength(2)
    expect(markdown).not.toContain('执行摘要')
  })

  it('preserves a plain narrative even when the task has a known schema label', () => {
    const document = projectArtifactDocument({ entry, output: '# 实际输出\n\n这不是任务目标。' })
    expect(renderArtifactDocument(document)).toBe('# 实际输出\n\n这不是任务目标。')
    expect(renderArtifactDocument(document)).not.toContain(entry.objective)
  })

  it('retains distinct reports instead of treating them as duplicates', () => {
    const document = projectArtifactDocument({ entry: { ...entry, semanticTaskKey: 'final_report' }, output: {
      artifacts: [{ artifactType: 'run_deliverable', content: '第一份报告' }, { artifactType: 'run_deliverable', content: '另一份报告' }]
    } })
    expect(renderArtifactDocument(document)).toContain('第一份报告')
    expect(renderArtifactDocument(document)).toContain('另一份报告')
  })

  it('dispatches requirements schema to a semantic document projection', () => {
    expect(resolveArtifactKind(entry, output)).toBe('requirements_specification')
    const document = projectArtifactDocument({ entry, output })
    const markdown = renderArtifactDocument(document)

    expect(markdown).toContain('### REQ-03')
    expect(markdown.split('试生产及爬坡周期')).toHaveLength(2)
    expect(markdown).toContain('**验收目标**')
    expect(markdown).toContain('**验收指标**')
    expect(markdown).toContain('**验收判据**')
    expect(markdown).not.toContain('Requirement Acceptance Matrix')
    expect(markdown.split('≤ 6 周')).toHaveLength(2)
    expect(markdown).not.toContain('- metric:')
    expect(markdown).not.toContain('- requirement_id:')
    expect(markdown).not.toContain('- target:')
    expect(markdown).not.toContain('- criterion:')
    expect(document.inspector.evidenceRefs).toContain('evidence:constraint:03')
    expect(document.inspector.upstreamInputs).toContain('input:constraints')
    expect(document.blocks.every(block => block.blockId)).toBe(true)
    expect(document.blocks.filter(block => block.gutter).map(block => block.blockId)).toEqual([
      'intro',
      'req-03',
      'assumptions'
    ])
    expect(document.blocks.filter(block => block.blockId === 'req-03' && block.gutter)).toHaveLength(1)
  })

  it('uses the generic renderer only for unknown schemas', () => {
    const unknown = projectArtifactDocument({
      entry: { ...entry, semanticTaskKey: 'custom_payload' },
      output: { custom_payload: { value: 'x' } }
    })
    expect(unknown.artifactKind).toBe('unknown')
    expect(renderArtifactDocument(unknown)).toContain('custom payload')
  })

  it('preserves nested records in intermediate results instead of displaying record placeholders', () => {
    const document = projectArtifactDocument({
      entry: { ...entry, semanticTaskKey: 'solution_design' },
      output: { design: { groups: [
        { name: '第一组', count: 8, activities: [{ title: '阅读交流', duration: 30 }] },
        { name: '第二组', count: 7, activities: [{ title: '成果分享', duration: 20 }] }
      ] } }
    })
    const markdown = renderArtifactDocument(document)
    expect(markdown).toContain('第一组')
    expect(markdown).toContain('阅读交流')
    expect(markdown).toContain('30')
    expect(markdown).toContain('第二组')
    expect(markdown).toContain('成果分享')
    expect(markdown).not.toContain('记录')
    const ids = document.blocks.filter(block => block.gutter).map(block => block.blockId)
    expect(new Set(ids).size).toBe(ids.length)
  })
})
