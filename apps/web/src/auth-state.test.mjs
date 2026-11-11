import test from 'node:test';
import assert from 'node:assert/strict';
import {validateAuth,authErrorMessage} from './auth-state.mjs';
test('registration validates length, confirmation and username before submission',()=>{
 assert.match(validateAuth('register','user','short','short'),/12/);
 assert.match(validateAuth('register','user','long-password','different'),/不一致/);
 assert.match(validateAuth('register',' user','long-password','long-password'),/账号/);
 assert.equal(validateAuth('register','user','long-password','long-password'),'');
});
test('login accepts existing credentials without registration-only constraints',()=>{
 assert.equal(validateAuth('login','user','old-pass',''),'');
 assert.match(validateAuth('login','user','',''),/密码/);
});
test('errors reveal no raw internal response',()=>{
 assert.match(authErrorMessage({status:409,detail:{code:'USERNAME_TAKEN'}}),/已被使用/);
 assert.match(authErrorMessage({status:401}),/不正确/);
 assert.match(authErrorMessage({status:429}),/稍后/);
 assert.doesNotMatch(authErrorMessage({status:500,detail:'secret diagnostic'}),/secret/);
});
