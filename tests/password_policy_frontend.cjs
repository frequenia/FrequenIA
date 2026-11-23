const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const field = { value: '' };
const context = vm.createContext({ document: { getElementById: () => field } });
vm.runInContext(fs.readFileSync('static/js/redefinicaoSenha.js', 'utf8'), context);
for (const symbol of '.+-[]*~_#:?@') {
  field.value = `Aa1${symbol}xxxx`;
  assert.equal(context.senhaValida(), true, `Simbolo recusado: ${symbol}`);
}
for (const value of ['Aa1?xxx', 'Aa1?' + 'x'.repeat(61), 'Aa1xxxxx', 'Aa1é?xxx',
  'Aa1? x x', ' Aa1?xxx', 'Aa1?xxx ', 'Aa1?\txxx', 'Aa1!xxxx',
  'Aa1$xxxx', 'aa1?xxxx', 'AA1?XXXX', 'Aaa?xxxx']) {
  field.value = value;
  assert.equal(context.senhaValida(), false);
}
for (const value of ['Aa1?' + 'x'.repeat(60), 'Aa1?xxxx']) {
  field.value = value;
  assert.equal(context.senhaValida(), true);
}
console.log('password_frontend_policy=ok');
