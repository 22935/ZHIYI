import type { Role } from '@/services/api/role'

const BUILTIN_ROLE_NAME_MAP: Array<{ matcher: RegExp; roleId: string }> = [
  { matcher: /(律师|lawyer|法律)/i, roleId: 'lawyer' },
  { matcher: /(教师|teacher|教学)/i, roleId: 'teacher' },
  { matcher: /(程序员|programmer|developer|开发)/i, roleId: 'programmer' },
  { matcher: /(作家|writer|写作)/i, roleId: 'writer' }
]

export function resolveKnowledgeRoleId(role?: Role | null): string | undefined {
  if (!role) {
    return undefined
  }

  if (role.roleType === 'BUILTIN') {
    const name = role.name || ''
    const matched = BUILTIN_ROLE_NAME_MAP.find(item => item.matcher.test(name))
    return matched?.roleId
  }

  return role.id
}
