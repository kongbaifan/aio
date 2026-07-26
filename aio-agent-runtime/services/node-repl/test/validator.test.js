import assert from 'node:assert/strict';
import test from 'node:test';

import { MAX_TIMEOUT, MIN_TIMEOUT, validateExecuteParams } from '../validator.js';


test('接受合法的执行参数', () => {
  const errors = validateExecuteParams({
    timeout: 30000,
    cwd: process.cwd(),
    session_id: 'demo-session',
  });
  assert.deepEqual(errors, []);
});


test('拒绝越界或非数字超时', () => {
  assert.match(validateExecuteParams({ timeout: MIN_TIMEOUT - 1 })[0], /at least/);
  assert.match(validateExecuteParams({ timeout: MAX_TIMEOUT + 1 })[0], /not exceed/);
  assert.match(validateExecuteParams({ timeout: Number.NaN })[0], /finite number/);
});


test('拒绝危险目录与非法会话标识', () => {
  assert.match(validateExecuteParams({ cwd: 'relative/path' })[0], /absolute path/);
  assert.match(validateExecuteParams({ cwd: '/tmp/../outside' })[0], /path traversal/);
  assert.match(validateExecuteParams({ session_id: '' })[0], /must not be empty/);
});
