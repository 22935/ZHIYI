import request from '@/utils/request'
import type { AgentTraceStep, FederatedInfo } from './agentLawyer'

const TEACHER_AGENT_TIMEOUT_MS = 240000

export interface StudentDiagnosisResult {
  student_id?: string
  subject?: string
  grade?: string
  weak_points?: string[]
  strengths?: string[]
  mastery_score?: number
  mastery_level?: string
  learning_style?: string
  trend?: string
  diagnosis_summary?: string
  recommended_actions?: string[]
}

export interface LessonPlanResult {
  topic?: string
  subject?: string
  grade?: string
  duration?: string
  lesson_plan?: string
  template_refs?: Array<Record<string, any>>
  knowledge_points?: Array<Record<string, any>>
}

export interface HomeworkGradingResult {
  question?: string
  score?: number
  feedback?: string
  corrections?: string[]
  model_answer?: string
  strengths?: string[]
  mistakes?: string[]
}

export interface ErrorQuestionPushResult {
  knowledge_gap?: string[]
  gap_details?: Array<Record<string, any>>
  analysis_summary?: string
  root_causes?: string[]
  remediation_suggestions?: string[]
  similar_questions?: Array<Record<string, any>>
}

export interface TeacherAgentRequest {
  text: string
  sessionId?: string
}

export interface TeacherAgentResponse {
  success: boolean
  answer: string
  sessionId: string
  skillsUsed: string[]
  trace: AgentTraceStep[]
  riskLevel?: string
  federated?: FederatedInfo
  studentDiagnosis?: StudentDiagnosisResult
  student_diagnosis?: StudentDiagnosisResult
  lessonPlan?: LessonPlanResult
  lesson_plan_generation?: LessonPlanResult
  homeworkGrading?: HomeworkGradingResult
  homework_grading?: HomeworkGradingResult
  errorQuestionPush?: ErrorQuestionPushResult
  error_analysis_question_push?: ErrorQuestionPushResult
  message?: string
  error?: string
}

export interface TeacherOcrResult {
  text: string
  success: boolean
  method?: string
  raw?: any
}

const extractTextFromOcrResponse = (responseData: any): TeacherOcrResult => {
  const data = responseData?.data || {}
  const text = String(
    data?.content ||
      data?.text ||
      responseData?.text ||
      ''
  ).trim()
  return {
    text,
    success: Boolean(responseData?.success) && text.length > 0,
    method: data?.method,
    raw: responseData
  }
}

export const agentTeacherApi = {
  async chat(payload: TeacherAgentRequest): Promise<TeacherAgentResponse> {
    const response = await request.post<TeacherAgentResponse>(
      '/agent/teacher/chat',
      payload,
      { timeout: TEACHER_AGENT_TIMEOUT_MS }
    )
    return response.data
  },

  async extractOcrText(file: File): Promise<TeacherOcrResult> {
    const formData = new FormData()
    formData.append('file', file)

    const response = await request.post<any>('/ai/multimodal/image?task=ocr', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      },
      timeout: TEACHER_AGENT_TIMEOUT_MS
    })
    return extractTextFromOcrResponse(response.data)
  }
}
