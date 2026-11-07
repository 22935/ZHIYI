import axios from 'axios'
import { apiUrl, LOCAL_REQUEST_HEADERS } from '@/platform'
export const agentosRequest = axios.create({
  baseURL: apiUrl('/api/agentos/v2'),
  headers: LOCAL_REQUEST_HEADERS,
  timeout: 240000
})
