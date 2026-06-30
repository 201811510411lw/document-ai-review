import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import path from 'node:path'

const repoRoot = path.resolve(fileURLToPath(new URL('../..', import.meta.url)))
const apiSource = readFileSync(path.join(repoRoot, 'web-console/src/api/index.js'), 'utf8')
const loginPageSource = readFileSync(
  path.join(repoRoot, 'web-console/src/views/LoginPage.vue'),
  'utf8',
)
const userStoreSource = readFileSync(path.join(repoRoot, 'web-console/src/store/user.js'), 'utf8')

assert.match(
  apiSource,
  /startSso\(mode = 'qr'\)/,
  'authApi.startSso should default to desktop QR login mode',
)
assert.match(
  loginPageSource,
  /authApi\.startSso\(\)/,
  'Login page should use the default desktop QR login mode',
)
assert.doesNotMatch(
  loginPageSource,
  /authApi\.startSso\('work'\)/,
  'Login page should not force in-WeCom OAuth mode for desktop login',
)
assert.match(
  apiSource,
  /login\(username, password\)/,
  'authApi should expose local username/password login',
)
assert.match(
  userStoreSource,
  /localStorage\.setItem\('auth_token', res\.access_token\)/,
  'User store should persist the bearer token returned by local login',
)
assert.match(
  loginPageSource,
  /userStore\.login\(username\.value, password\.value\)/,
  'Login page should submit local credentials through the user store',
)
