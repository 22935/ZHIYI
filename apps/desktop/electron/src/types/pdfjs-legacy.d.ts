/**
 * pdfjs-dist legacy 子路径未随包提供类型声明（包类型只挂在主入口），
 * 这里按文本提取用到的最小面声明；渲染相关 API 一律不暴露。
 */
declare module 'pdfjs-dist/legacy/build/pdf.mjs' {
  export interface PdfTextContentItem { str?: string; hasEOL?: boolean }
  export interface PdfPageProxy { getTextContent(): Promise<{ items: PdfTextContentItem[] }> }
  export interface PdfDocumentProxy { numPages: number; getPage(n: number): Promise<PdfPageProxy>; destroy(): Promise<void> }
  export interface PdfLoadingTaskProxy { promise: Promise<PdfDocumentProxy> }
  export function getDocument(src: {
    data: Uint8Array
    useWorkerFetch?: boolean
    isEvalSupported?: boolean
    disableFontFace?: boolean
  }): PdfLoadingTaskProxy
}
