const USER_NOTIFIED_FLAG = '__kinlinUserNotified'
type UserNotifiedError = Error & { [USER_NOTIFIED_FLAG]?: boolean }

export const markErrorAsUserNotified = <T extends Error>(error: T): T => {
  (error as UserNotifiedError)[USER_NOTIFIED_FLAG] = true
  return error
}

export const wasErrorUserNotified = (error: unknown): boolean =>
  error instanceof Error && Boolean((error as UserNotifiedError)[USER_NOTIFIED_FLAG])
