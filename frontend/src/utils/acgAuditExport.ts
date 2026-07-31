import type { AcgView, TraceEvent } from '@/services/api/agentos'

const contractViolation = (event: TraceEvent) => ({
  eventId: event.eventId,
  eventType: event.eventType,
  stepId: event.stepId,
  agentName: event.agentName,
  createdAt: event.createdAt,
  direction: event.payload?.direction,
  path: event.payload?.path,
  attempt: event.payload?.attempt
})

export const buildAcgAuditExport = (view: AcgView) => ({
  schemaVersion: view.provenance.schemaVersion || 2,
  runId: view.runId,
  status: view.status,
  engine: view.engine,
  graphId: view.acgBlueprint?.graphId || null,
  exportedAt: new Date().toISOString(),
  integrityStatus: view.provenance.integrityStatus || view.lowEntropyMetrics.integrityStatus,
  metrics: { ...view.lowEntropyMetrics },
  productions: view.provenance.productions.map((event) => ({
    eventId: event.eventId,
    runId: event.runId,
    taskId: event.taskId,
    producerStepId: event.producerStepId,
    agentName: event.agentName,
    attempt: event.attempt,
    fieldNames: event.fieldNames || [],
    tokenSize: event.tokenSize || 0,
    evidenceRefs: event.evidenceRefs || [],
    checksum: event.checksum,
    previousHash: event.previousHash,
    eventHash: event.eventHash,
    createdAt: event.createdAt
  })),
  consumptions: view.provenance.consumptions.map((event) => ({
    eventId: event.eventId,
    runId: event.runId,
    taskId: event.taskId,
    consumerStepId: event.consumerStepId,
    consumerAgentName: event.consumerAgentName,
    attempt: event.attempt,
    producerStepIds: event.producerStepIds,
    producerEventIds: event.producerEventIds || [],
    fieldsByProducer: event.fieldsByProducer || {},
    consumedFields: event.consumedFields || [],
    tokensDelivered: event.tokensDelivered || 0,
    tokensAvailable: event.tokensAvailable || 0,
    savingRatio: event.savingRatio || 0,
    contractStatus: event.contractStatus || 'unknown',
    checksum: event.checksum,
    previousHash: event.previousHash,
    eventHash: event.eventHash,
    createdAt: event.createdAt
  })),
  interactions: view.interactions.map((event) => ({
    eventId: event.eventId,
    interactionId: event.interactionId,
    runId: event.runId,
    taskId: event.taskId,
    edgeIds: event.edgeIds,
    producerStepIds: event.producerStepIds,
    consumerStepId: event.consumerStepId,
    producerAgentNames: event.producerAgentNames,
    consumerAgentName: event.consumerAgentName,
    fieldsByProducer: event.fieldsByProducer,
    tokensDelivered: event.tokensDelivered,
    tokensAvailable: event.tokensAvailable,
    savingRatio: event.savingRatio,
    evidenceRefs: event.evidenceRefs,
    contractStatus: event.contractStatus,
    checksum: event.checksum,
    previousHash: event.previousHash,
    eventHash: event.eventHash,
    createdAt: event.createdAt
  })),
  contractViolations: view.contractViolations.map(contractViolation)
})

const csvCell = (value: unknown) => {
  let text = Array.isArray(value)
    ? value.join('|')
    : value && typeof value === 'object'
      ? JSON.stringify(value)
      : String(value ?? '')
  if (/^[=+\-@]/.test(text)) text = `'${text}`
  return `"${text.replace(/"/g, '""')}"`
}

export const buildAcgAuditCsv = (view: AcgView) => {
  const audit = buildAcgAuditExport(view)
  const rows: Record<string, unknown>[] = []

  for (const event of audit.productions) {
    rows.push({
      record_type: 'production', event_id: event.eventId, timestamp: event.createdAt,
      producer_steps: event.producerStepId, producer_agents: event.agentName,
      fields: event.fieldNames, token_size: event.tokenSize, evidence_refs: event.evidenceRefs,
      checksum: event.checksum, previous_hash: event.previousHash, event_hash: event.eventHash,
      attempt: event.attempt
    })
  }
  for (const event of audit.consumptions) {
    rows.push({
      record_type: 'consumption', event_id: event.eventId, timestamp: event.createdAt,
      producer_steps: event.producerStepIds, consumer_step: event.consumerStepId,
      consumer_agent: event.consumerAgentName, fields: event.consumedFields,
      fields_by_producer: event.fieldsByProducer, tokens_delivered: event.tokensDelivered,
      tokens_available: event.tokensAvailable, saving_ratio: event.savingRatio,
      contract_status: event.contractStatus, checksum: event.checksum,
      previous_hash: event.previousHash, event_hash: event.eventHash, attempt: event.attempt
    })
  }
  for (const event of audit.interactions) {
    rows.push({
      record_type: 'interaction', event_id: event.eventId, interaction_id: event.interactionId,
      timestamp: event.createdAt, edge_ids: event.edgeIds, producer_steps: event.producerStepIds,
      consumer_step: event.consumerStepId, producer_agents: event.producerAgentNames,
      consumer_agent: event.consumerAgentName, fields_by_producer: event.fieldsByProducer,
      tokens_delivered: event.tokensDelivered, tokens_available: event.tokensAvailable,
      saving_ratio: event.savingRatio, evidence_refs: event.evidenceRefs,
      contract_status: event.contractStatus, checksum: event.checksum,
      previous_hash: event.previousHash, event_hash: event.eventHash
    })
  }
  for (const event of audit.contractViolations) {
    rows.push({
      record_type: 'contract_violation', event_id: event.eventId, timestamp: event.createdAt,
      consumer_step: event.stepId, consumer_agent: event.agentName,
      contract_status: 'invalid', violation_direction: event.direction,
      violation_path: event.path, attempt: event.attempt
    })
  }

  const columns = [
    'record_type', 'event_id', 'interaction_id', 'timestamp', 'edge_ids',
    'producer_steps', 'consumer_step', 'producer_agents', 'consumer_agent',
    'fields', 'fields_by_producer', 'token_size', 'tokens_delivered',
    'tokens_available', 'saving_ratio', 'evidence_refs', 'contract_status',
    'checksum', 'previous_hash', 'event_hash', 'attempt', 'violation_direction',
    'violation_path'
  ]
  return [
    columns.map(csvCell).join(','),
    ...rows.map((row) => columns.map((column) => csvCell(row[column])).join(','))
  ].join('\r\n')
}
