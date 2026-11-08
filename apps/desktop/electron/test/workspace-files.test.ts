import assert from 'node:assert/strict'
import { test } from 'node:test'
import { mkdtemp, mkdir, writeFile, readFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import * as path from 'node:path'
import { WorkspaceFiles } from '../src/lib/workspace-files.ts'

test('native editor: selected folders, hidden entries, conditional save, restore and rejected conflict', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'zhiyi-editor-'))
  assert.ok(path.resolve(root).startsWith(path.join(tmpdir(), 'zhiyi-editor-')))
  try {
    const folder = path.join(root, '用户项目')
    await mkdir(folder); await mkdir(path.join(folder, '.git'))
    await writeFile(path.join(folder, 'note.md'), '原始\r\ntext')
    await writeFile(path.join(folder, 'binary.bin'), Buffer.from([0, 1]))
    await writeFile(path.join(root, 'outside.txt'), 'sentinel')
    const settings = path.join(root, 'folders.json')
    const files = new WorkspaceFiles(settings)
    const selected = await files.select(folder)
    const listing = await files.list(selected.id, '.')
    assert.ok(listing.entries.some(entry => entry.name === '.git'))
    const original = await files.read(selected.id, 'note.md')
    assert.equal(original.content, '原始\r\ntext')
    await files.save(selected.id, 'note.md', '真实保存\r\n完成', original.version)
    assert.equal(await readFile(path.join(folder, 'note.md'), 'utf8'), '真实保存\r\n完成')
    await assert.rejects(files.save(selected.id, 'note.md', 'stale overwrite', original.version), /FILE_CONFLICT/)
    await assert.rejects(files.read(selected.id, '../outside.txt'))
    await assert.rejects(files.read('unselected', 'note.md'))
    const rejected = await files.read(selected.id, 'binary.bin')
    assert.equal(rejected.kind, 'unsupported')
    assert.match(rejected.reason!, /二进制文件/)
    await assert.rejects(files.save(selected.id, 'binary.bin', 'text over binary', rejected.version ?? ''), /UTF-8 文本文件/)
    const observed = await files.read(selected.id, 'note.md')
    const competing = await Promise.allSettled([
      files.save(selected.id, 'note.md', 'first writer', observed.version),
      files.save(selected.id, 'note.md', 'second writer', observed.version)
    ])
    assert.equal(competing.filter(result => result.status === 'fulfilled').length, 1)
    assert.equal(competing.filter(result => result.status === 'rejected').length, 1)
    assert.deepEqual(await new WorkspaceFiles(settings).current(), selected)
    assert.equal(await readFile(path.join(root, 'outside.txt'), 'utf8'), 'sentinel')
  } finally { await rm(root, {recursive: true, force: true}) }
})

test('native editor: read-only preview payloads for encodings, images and office/pdf documents', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'zhiyi-preview-'))
  try {
    const folder = path.join(root, '资料')
    await mkdir(folder)
    await writeFile(path.join(folder, 'note.md'), '# editable text')
    // "中 GBK" 的 GB18030 字节（0xD6 0xD0 = 中）；Buffer 无 gb18030 编码器，只能手写。
    await writeFile(path.join(folder, 'gbk.txt'), Buffer.from([0xD6, 0xD0, 0x20, 0x47, 0x42, 0x4B]))
    await writeFile(path.join(folder, 'utf16.txt'), Buffer.from('\uFEFF' + 'UTF-16 文本', 'utf16le'))
    await writeFile(path.join(folder, 'picture.png'), Buffer.from([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 1]))
    await writeFile(path.join(folder, 'app.exe'), Buffer.from([0x4D, 0x5A, 0, 1, 2]))
    const JSZip = (await import('jszip')).default
    const docx = new JSZip()
    docx.file('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    docx.file('_rels/.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    docx.file('word/document.xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>你好 mammoth 提取</w:t></w:r></w:p><w:p><w:r><w:t>第二段</w:t></w:r></w:p></w:body></w:document>')
    await writeFile(path.join(folder, '报告.docx'), await docx.generateAsync({ type: 'nodebuffer' }))

    const XLSX = await import('xlsx')
    const book = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(book, XLSX.utils.aoa_to_sheet([['名称', '数量'], ['扳手', 3]]), '清单')
    await writeFile(path.join(folder, '表.xlsx'), XLSX.write(book, { type: 'buffer', bookType: 'xlsx' }))

    const objects = [
      '%PDF-1.4\n',
      '1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n',
      '2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n',
      '3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n'
    ]
    const stream = 'BT /F1 12 Tf 20 100 Td (hello pdf) Tj ET'
    objects.push(`4 0 obj\n<< /Length ${stream.length} >>\nstream\n${stream}\nendstream\nendobj\n`)
    objects.push('5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n')
    objects.push('trailer\n<< /Root 1 0 R /Size 6 >>\n%%EOF\n')
    await writeFile(path.join(folder, '文档.pdf'), Buffer.from(objects.join(''), 'latin1'))

    const files = new WorkspaceFiles(path.join(root, 'folders.json'))
    const selected = await files.select(folder)

    const gbk = await files.read(selected.id, 'gbk.txt')
    assert.equal(gbk.kind, 'text')
    assert.equal(gbk.content, '中 GBK')
    assert.equal(gbk.encoding, 'gb18030')
    assert.equal(gbk.version, null)

    const utf16 = await files.read(selected.id, 'utf16.txt')
    assert.equal(utf16.kind, 'text')
    assert.equal(utf16.content, 'UTF-16 文本')
    assert.equal(utf16.encoding, 'utf-16le')
    assert.equal(utf16.version, null)

    const utf8 = await files.read(selected.id, 'note.md')
    assert.equal(utf8.kind, 'text')
    assert.equal(utf8.encoding, 'utf-8')
    assert.match(utf8.version!, /^[0-9a-f]{64}$/)

    const picture = await files.read(selected.id, 'picture.png')
    assert.equal(picture.kind, 'image')
    assert.equal(picture.mime, 'image/png')
    assert.match(picture.content, /^data:image\/png;base64,/)

    const docxRead = await files.read(selected.id, '报告.docx')
    assert.equal(docxRead.kind, 'extracted')
    assert.equal(docxRead.format, 'docx')
    assert.match(docxRead.content, /你好 mammoth 提取/)
    assert.match(docxRead.content, /第二段/)

    const xlsxRead = await files.read(selected.id, '表.xlsx')
    assert.equal(xlsxRead.kind, 'extracted')
    assert.match(xlsxRead.content, /## Sheet: 清单/)
    assert.match(xlsxRead.content, /扳手,3/)

    const pdfRead = await files.read(selected.id, '文档.pdf')
    assert.equal(pdfRead.kind, 'extracted')
    assert.match(pdfRead.content, /hello pdf/)

    const exe = await files.read(selected.id, 'app.exe')
    assert.equal(exe.kind, 'unsupported')
    assert.match(exe.reason!, /Windows 可执行程序/)
    assert.equal(exe.version, null)
  } finally { await rm(root, {recursive: true, force: true}) }
})
