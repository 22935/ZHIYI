import type { WorkflowRun, WorkflowStep } from '@/services/api/workflow'

type AnyRecord = Record<string, any>

export interface ContractRiskItem {
  id?: string
  title?: string
  level?: string
  clause?: string
  reason?: string
  consequence?: string
  suggestion?: string
  evidenceIds?: string[]
  [key: string]: any
}

export interface ContractEvidenceItem {
  id?: string
  riskId?: string
  stepId?: string
  sourceType?: string
  sourceName?: string
  title?: string
  content?: string
  citationText?: string
  chunkId?: string
  confidence?: number
  retrievalScore?: number
  metadata?: Record<string, any>
  [key: string]: any
}

export interface ContractReviewArtifacts {
  risks: ContractRiskItem[]
  evidences: ContractEvidenceItem[]
  reportMarkdown: string
  riskSummary: AnyRecord | null
  revisionSuggestions: AnyRecord[]
  contractInfo: AnyRecord | null
  paths: {
    risks: string
    evidences: string
    reportMarkdown: string
  }
}

const ARTIFACT_PATHS = {
  risks: 'output.artifacts.risk_detect.risks',
  evidences: 'output.artifacts.legal_evidence_match.evidences',
  reportMarkdown: 'output.artifacts.report_generate.report_markdown'
}

const asRecord = (value: unknown): AnyRecord => {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as AnyRecord : {}
}

const asArray = <T = AnyRecord>(value: unknown): T[] => {
  return Array.isArray(value) ? value as T[] : []
}

const asString = (value: unknown): string => {
  return typeof value === 'string' ? value : ''
}

const stepOutput = (steps: WorkflowStep[] | undefined, stepId: string): AnyRecord => {
  return asRecord(steps?.find(step => step.stepId === stepId)?.output)
}

export const extractContractReviewArtifacts = (run: WorkflowRun | null): ContractReviewArtifacts => {
  const artifacts = asRecord(run?.output?.artifacts)
  const riskDetect = {
    ...stepOutput(run?.steps, 'risk_detect'),
    ...asRecord(artifacts.risk_detect)
  }
  const evidenceMatch = {
    ...stepOutput(run?.steps, 'legal_evidence_match'),
    ...asRecord(artifacts.legal_evidence_match)
  }
  const revisionSuggest = {
    ...stepOutput(run?.steps, 'revision_suggest'),
    ...stepOutput(run?.steps, 'suggestion_generate'),
    ...asRecord(artifacts.revision_suggest),
    ...asRecord(artifacts.suggestion_generate)
  }
  const humanReview = {
    ...stepOutput(run?.steps, 'human_review'),
    ...asRecord(artifacts.human_review)
  }
  const reportGenerate = {
    ...stepOutput(run?.steps, 'report_generate'),
    ...asRecord(artifacts.report_generate)
  }
  const report = asRecord(reportGenerate.report)

  const risks =
    asArray<ContractRiskItem>(riskDetect.risks).length
      ? asArray<ContractRiskItem>(riskDetect.risks)
      : asArray<ContractRiskItem>(humanReview.risks).length
        ? asArray<ContractRiskItem>(humanReview.risks)
        : asArray<ContractRiskItem>(report.riskItems)

  const evidences =
    asArray<ContractEvidenceItem>(evidenceMatch.evidences).length
      ? asArray<ContractEvidenceItem>(evidenceMatch.evidences)
      : asArray<ContractEvidenceItem>(report.evidenceAppendix)

  return {
    risks,
    evidences,
    reportMarkdown: asString(reportGenerate.report_markdown) || asString(reportGenerate.reportMarkdown),
    riskSummary: Object.keys(asRecord(riskDetect.risk_summary)).length ? asRecord(riskDetect.risk_summary) : asRecord(report.riskSummary),
    revisionSuggestions: asArray<AnyRecord>(revisionSuggest.revision_suggestions).length
      ? asArray<AnyRecord>(revisionSuggest.revision_suggestions)
      : asArray<AnyRecord>(report.revisionSuggestions),
    contractInfo: Object.keys(asRecord(report.contractInfo)).length ? asRecord(report.contractInfo) : null,
    paths: ARTIFACT_PATHS
  }
}
