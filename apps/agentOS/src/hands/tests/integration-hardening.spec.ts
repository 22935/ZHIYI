import { mkdtempSync,writeFileSync,appendFileSync,readFileSync,rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe,it,expect } from 'vitest'
import { HandsService } from '../hands/service.ts'
import { HandsCredentialStore } from '../hands/keys.ts'
import { TrustedGrantStore,issueTestGrant } from '../hands/grant-store.ts'
import { ExecutionLedger } from '../hands/ledger.ts'
import { receiptChecksum } from '../hands/engine.ts'
import { callHandle,signRequest,pollTerminal } from './service-client.ts'

describe('EX-M1 real boundary hardening',()=>{
  it('enforces owner on status/events/cancel and seals identity on every terminal',async()=>{
    const root=mkdtempSync(join(tmpdir(),'hands-m1-'))
    const service=new HandsService({workspaceRoot:root,dataDir:join(root,'ledger'),
      credentials:new HandsCredentialStore([{credentialId:'a',secret:'alpha'},{credentialId:'b',secret:'beta'}]),
      grants:new TrustedGrantStore([issueTestGrant({grantId:'g',workspaceId:'w',canonicalRoot:root,
        capabilities:['fs.write','fs.read','fs.list'],allowedCallers:['a','b']})])})
    try {
      await service.start()
      const identity={runId:'r',stepId:'s',attemptId:'a',commitId:'c'}
      const request={protocolVersion:'1',requestId:'req',invocationId:'inv',idempotencyKey:'one',identity,
        capabilityId:'fs.write',authorization:{grantId:'g',workspaceId:'w'},input:{path:'x.txt',content:'real'},limits:{}}
      const posted=callHandle(service,signRequest({credentialId:'a',secret:'alpha',method:'POST',path:'/v1/executions',body:JSON.stringify(request),idempotencyKey:'one'}))
      const id=posted.body.executionId
      for(const suffix of ['', '/events','/cancel']) {
        const response=callHandle(service,signRequest({credentialId:'b',secret:'beta',method:suffix==='/cancel'?'POST':'GET',
          path:'/v1/executions/'+id+suffix,body:suffix==='/cancel'?JSON.stringify({executionId:id}):'',idempotencyKey:'query'}))
        expect(response.status).toBe(403)
      }
      const terminal=await pollTerminal(service,id,{credentialId:'a',secret:'alpha'})
      expect(terminal.body.receipt.identity).toEqual(identity)
      expect(terminal.body.receipt.checksum).toBe(receiptChecksum(terminal.body.receipt))
      expect(readFileSync(join(root,'x.txt'),'utf8')).toBe('real')
      writeFileSync(join(root,'outside-placeholder'),'unused')
      request.capabilityId='fs.read';request.requestId='read';request.invocationId='read';request.idempotencyKey='read'
      request.input={path:join(root,'..','outside-sentinel'),content:''}
      // A real outside existing target is rejected before DSH's read seam.
      const outsideDir=mkdtempSync(join(tmpdir(),'hands-m1-outside-'));const outside=join(outsideDir,'sentinel');writeFileSync(outside,'sentinel');request.input={path:outside,content:''}
      try {
        const denied=callHandle(service,signRequest({credentialId:'a',secret:'alpha',method:'POST',path:'/v1/executions',body:JSON.stringify(request),idempotencyKey:'read'}))
        expect((await pollTerminal(service,denied.body.executionId,{credentialId:'a',secret:'alpha'})).body.state).toBe('FAILED')
        expect(readFileSync(outside,'utf8')).toBe('sentinel')
      } finally {rmSync(outsideDir,{recursive:true,force:true})}
    } finally {await service.stop();rmSync(root,{recursive:true,force:true})}
  })
  it('holds a single OS writer and appends safely after quarantining a torn tail',()=>{
    const root=mkdtempSync(join(tmpdir(),'hands-lock-'))
    let ledger=new ExecutionLedger(root)
    try {
      expect(()=>new ExecutionLedger(root)).toThrow('HANDS_LEDGER_ALREADY_OWNED')
      ledger.close()
      appendFileSync(join(root,'ledger.jsonl'),'{"t":"claim",')
      ledger=new ExecutionLedger(root)
      ledger.claim({callerId:'a',idempotencyKey:'new',requestDigest:'x',summary:{callerId:'a',capabilityId:'fs.read',requestId:'r',invocationId:'i',workspaceId:'w',grantId:'g',identity:{runId:'run'}}})
      ledger.close();ledger=new ExecutionLedger(root);ledger.reconcile()
      const record=ledger.findIdempotent('a','new')!
      expect(record.state).toBe('FAILED')
      expect(record.receipt?.identity).toEqual({runId:'run'})
      expect(record.receipt?.checksum).toBe(receiptChecksum(record.receipt!))
    } finally {ledger.close();rmSync(root,{recursive:true,force:true})}
  })
})
