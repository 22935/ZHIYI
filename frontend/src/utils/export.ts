/**
 * 导出工具
 */
export interface ConversationExport {
  messages: Array<{
    role: string
    content: string
    time: string
  }>
  role?: string
  createdAt: string
}

/**
 * 导出对话为JSON
 */
export function exportConversationToJson(data: ConversationExport): string {
  return JSON.stringify(data, null, 2)
}

/**
 * 导出对话为TXT
 */
export function exportConversationToTxt(data: ConversationExport): string {
  let content = `对话导出\n`
  content += `角色: ${data.role || '默认'}\n`
  content += `创建时间: ${data.createdAt}\n`
  content += `\n${'='.repeat(50)}\n\n`

  data.messages.forEach((msg, index) => {
    content += `[${msg.role.toUpperCase()}] ${msg.time}\n`
    content += `${msg.content}\n\n`
  })

  return content
}

/**
 * 导出对话为CSV
 */
export function exportConversationToCsv(data: ConversationExport): string {
  // CSV头部（使用BOM支持中文）
  let content = '\uFEFF时间,角色,内容\n'
  
  data.messages.forEach((msg) => {
    // 转义CSV特殊字符
    const time = `"${msg.time.replace(/"/g, '""')}"`
    const role = `"${msg.role.replace(/"/g, '""')}"`
    const msgContent = `"${msg.content.replace(/"/g, '""').replace(/\n/g, ' ')}"`
    content += `${time},${role},${msgContent}\n`
  })

  return content
}

/**
 * 导出对话为Markdown
 */
export function exportConversationToMarkdown(data: ConversationExport): string {
  let content = `# 对话导出\n\n`
  content += `**角色**: ${data.role || '默认'}\n\n`
  content += `**创建时间**: ${data.createdAt}\n\n`
  content += `---\n\n`

  data.messages.forEach((msg) => {
    const roleLabel = msg.role === 'user' ? '👤 用户' : '🤖 AI助手'
    content += `## ${roleLabel} - ${msg.time}\n\n`
    // 转义Markdown特殊字符，但保留换行
    const escapedContent = msg.content
      .replace(/\n/g, '\n\n')
      .replace(/\*\*/g, '\\*\\*')
      .replace(/#/g, '\\#')
    content += `${escapedContent}\n\n`
    content += `---\n\n`
  })

  return content
}

/**
 * 下载文件
 */
export function downloadFile(content: string, filename: string, mimeType: string = 'text/plain') {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

