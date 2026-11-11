import test from 'node:test';
import assert from 'node:assert/strict';
import {creationQuoteError} from './work-contract.mjs';
test('quote failure shows actionable material errors without exposing raw response',()=>{
 assert.match(creationQuoteError({status:422,detail:{code:'PROFILE_INCOMPLETE'}}),/商品资料未完整/);
 assert.match(creationQuoteError({status:401}),/重新登录/);
 assert.doesNotMatch(creationQuoteError({status:500,message:'secret',detail:{message:'secret'}}),/secret/);
});
import {workStatusLabel} from './work-contract.mjs';
test('failed and unknown work labels do not imply continued generation',()=>{
 assert.equal(workStatusLabel('failed'),'生成失败');
 assert.match(workStatusLabel('external_unknown'),/已停止推进/);
});
