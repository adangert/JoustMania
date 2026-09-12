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
vm.runInNewContext(script.replace('}());', 'globalThis.renderControllers = renderControllers; globalThis.connectionAssessment = connectionAssessment; globalThis.renderPairing = renderPairing;}());'), context);
(async () => {
    const button = {dataset: {address: 'AA:BB:CC:DD:EE:01', role: 'central'}, disabled: false};
    await handlers.click({target: {closest(selector) {return selector === '.role-toggle' ? button : null;}}});
    assert.equal(requests[0].role, 'central');
    for (const kind of ['identify', 'unpair']) {
        requests.length = 0;
        const action = {dataset: {address: 'AA:BB:CC:DD:EE:01', action: kind}, disabled: false};
        context.window.confirm = () => false;
        if (kind === 'unpair') {
            await handlers.click({target: {closest(selector) {return selector === '.controller-action' ? action : null;}}});
            assert.equal(requests.length, 0);
        }
        context.window.confirm = () => true;
        await handlers.click({target: {closest(selector) {return selector === '.controller-action' ? action : null;}}});
        assert.equal(requests[0].url, '/debug/controller-' + kind);
        assert.equal(requests[0].address, action.dataset.address);
    }
    function node() {
        return {children: [], dataset: {}, style: {},
            appendChild(child) {this.children.push(child); this.lastElementChild = child;},
            setAttribute() {},
            set textContent(value) {this.text = value; this.children = [];},
            get textContent() {return this.text || '';}};
    }
    const body = node(); body.dataset.forAdapter = 'hci0';
    const unknown = node(); unknown.dataset.forAdapter = 'unknown';
    context.document.createElement = node;
    context.document.querySelectorAll = () => [body, unknown];
    context.document.querySelector = selector => selector.includes('unknown') ? unknown : body;
    element('unassigned-controller-section').style = {};
    const controller = {address: 'AA', adapter: 'hci0', connected: true, role: 'Central',
        update_count: 10, report_gap: {p95_ms: 36, p99_ms: 40, max_ms: 80,
            last_report_age_ms: 500, sample_count: 600, window_s: 10,
            gaps_over_50ms: 2, gaps_over_100ms: 0}};
    context.renderControllers([controller], 1);
    assert.equal(body.children[0].children[3].textContent, '36.0 ms');
    assert.equal(body.children[0].children[4].textContent, '80.0 ms');
    assert.equal(body.children[0].children[5].textContent, 'Central');
    assert.equal(body.children[0].children[3].className, 'nowrap rate-slow');
    assert.equal(body.children[0].children[4].className, 'nowrap rate-slow');
    for (const [p95, max, color] of [[22, 30, 'rate-good'], [24, 40, 'rate-warning'], [30, 50, 'rate-warning'], [31, 51, 'rate-slow']]) {
        controller.report_gap.p95_ms = p95; controller.report_gap.max_ms = max;
        context.renderControllers([controller], 1);
        assert.equal(body.children[0].children[3].className, 'nowrap ' + color);
        assert.equal(body.children[0].children[4].className, 'nowrap ' + color);
    }
    controller.connected = false;
    context.renderControllers([controller], 1);
    assert.equal(body.children[0].children[3].textContent, '—');
    assert.equal(body.children[0].children[3].className, 'nowrap');
    assert.equal(body.children[0].children[1].children.length, 0);
    assert.equal(body.children[0].children[6].children.length, 0);
    controller.connected = true; controller.role = 'Unavailable';
    context.renderControllers([controller], 1);
    assert.equal(body.children[0].children[6].children.length, 0);
    controller.role = 'Central'; controller.report_gap = null;
    context.renderControllers([controller], 1);
    assert.equal(body.children[0].children[3].textContent, 'Unavailable');
    controller.adapter = 'unknown'; controller.model = 'ZCM2';
    context.renderControllers([controller], 1);
    assert.equal(unknown.children[0].children[6].children.length, 0);
    assert.equal(unknown.children[0].children[10].textContent, 'ZCM2 (PS4)');
    assert.equal(unknown.children[0].children.length, 15);
    const adapter = {name: 'hci0', connections: 2};
    const link = p95 => ({adapter: 'hci0', connected: true, report_gap: {p95_ms: p95}});
    assert.equal(context.connectionAssessment(adapter, [link(20), link(36)]), 'Mixed: 1 good, 1 slow');
    assert.equal(context.connectionAssessment(adapter, [link(36), link(40)]), 'Slow connections (2)');
    assert.equal(context.connectionAssessment(adapter, [link(24)]), 'Borderline connection');
    assert.equal(context.connectionAssessment(adapter, [link(null)]), 'Measuring connections…');
    const pairingInputs = [{value:'AA'}, {value:'BB'}];
    context.document.querySelectorAll = selector => selector === '.pairing-target' ? pairingInputs : [body, unknown];
    context.document.createTextNode = text => ({textContent: text});
    const plan = {available: true, adapters: [{name:'hci0', address:'AA', count:4}, {name:'hci1', address:'BB', count:0}],
        automatic:'AA', selected:'AA', override:'', busy:false, error:''};
    context.renderPairing(plan);
    assert.match(element('pairing-status').textContent, /Next controller: hci0/);
    let chosen;
    context.fetch = async (url, options) => {
        assert.equal(url, '/debug/pairing-target');
        chosen = options.body.get('address');
        return {ok:true, json:async () => ({...plan, override:chosen, selected:chosen || plan.automatic})};
    };
    await handlers.change({target:{name:'pairing-target',value:'BB'}});
    assert.equal(chosen, 'BB');
    assert.match(element('pairing-status').textContent, /hci1.*next pairing only/);
    context.renderPairing({...plan, busy:true});
    assert(pairingInputs.every(input => input.disabled));
    context.renderPairing(plan);
    assert.equal(pairingInputs[0].checked, true);
    assert.equal(pairingInputs[1].checked, false);
    console.log('Controller and pairing target UI tests passed');
})().catch(error => {console.error(error); process.exitCode = 1;});
