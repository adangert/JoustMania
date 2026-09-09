// Run with: node test_controller_role_ui.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const script = fs.readFileSync('templates/controller_debug.html', 'utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
const elements = {};
const handlers = {};
function element(id) {
    return elements[id] ||= {disabled: false, textContent: '', addEventListener(type, fn) {this[type] = fn;}};
}
const targets = [
    {dataset: {address: 'AA:BB:CC:DD:EE:01', role: 'peripheral'}, disabled: false},
    {dataset: {address: 'AA:BB:CC:DD:EE:02', role: 'peripheral'}, disabled: false},
    {dataset: {address: 'AA:BB:CC:DD:EE:03', role: 'peripheral'}, disabled: true}
];
const requests = [];
let active = 0, maximumActive = 0;
const context = {
    document: {
        getElementById: element,
        addEventListener(type, fn) {handlers[type] = fn;},
        querySelectorAll() {return targets;}
    },
    window: {setInterval() {}},
    URLSearchParams,
    async fetch(url, options) {
        active++;
        maximumActive = Math.max(maximumActive, active);
        const address = options.body.get('address');
        requests.push({url, address, role: options.body.get('role')});
        await new Promise(resolve => setImmediate(resolve));
        active--;
        const ok = !address.endsWith('02');
        return {ok, async json() {return ok ? {role: 'Peripheral'} : {error: 'Switch rejected'};}};
    }
};
vm.runInNewContext(script, context);
(async () => {
    await element('all-peripheral').click();
    assert.equal(requests.length, 2);
    assert.equal(maximumActive, 1);
    assert(requests.every(r => r.url === '/debug/controller-role' && r.role === 'peripheral'));
    assert.match(element('all-peripheral-status').textContent, /Switched 1 of 2/);
    assert.match(element('all-peripheral-status').textContent, /1 failed/);
    assert.equal(element('all-peripheral').disabled, false);
    requests.length = 0;
    const button = {dataset: {address: 'AA:BB:CC:DD:EE:01', role: 'central'}, disabled: false};
    await handlers.click({target: {closest() {return button;}}});
    assert.equal(requests[0].role, 'central');
    console.log('Controller role UI tests passed');
})().catch(error => {console.error(error); process.exitCode = 1;});
