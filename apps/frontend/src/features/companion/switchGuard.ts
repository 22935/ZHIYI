/**
 * 切换操作的「最后者胜」门闩。
 *
 * 形象切换必须跨越异步边界（动效皮肤要动态 import 引擎），期间用户完全
 * 可能又切了一次。每次切换领一张票据，落地前用票据核对自己是否仍是最新
 * 一次请求；过期结果必须自行作废，不能覆盖更新的选择。
 *
 * 刻意做成独立小对象而不是组件里的一个数字：这段语义与皮肤、渲染器无关，
 * 后续接入 Profile 级切换（形象 + 声线 + 台词一起换）可以直接复用。
 */
export interface SwitchGuard {
  /** 领一张新票据，返回「我是否仍是最新一次请求」的判定函数。 */
  begin(): () => boolean
}

export function createSwitchGuard(): SwitchGuard {
  let latest = 0
  return {
    begin() {
      const ticket = ++latest
      return () => ticket === latest
    }
  }
}
