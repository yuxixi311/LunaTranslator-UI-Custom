// Execute the actual WebView bridge callbacks in a small DOM/native harness.
// Run with: node src/tests/test_lookup_popup_bridge.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '../LunaTranslator/htmlcode/uiwebview/mainui.html'), 'utf8');
const calls = [];
const callbacks = {};
let uid = 0;
const bridge = new Proxy({}, {
    get: (_, name) => (...args) => calls.push([name, ...args]),
});
const sandbox = {
    window: {
        LUNAJSObject: bridge,
        getSelection: () => ({ removeAllRanges() {}, toString: () => '' }),
        location: { search: '', origin: 'http://example.invalid' },
    },
    LUNAJSObject: bridge,
    URL, URLSearchParams,
    _simpleuid: () => `gesture-${++uid}`,
    luna_current_cursor: 'default',
    isPointOverText: () => true,
};
vm.createContext(sandbox);
const bridgeStart = html.indexOf('    const urlParams = new URLSearchParams');
const bridgeEnd = html.indexOf('</script>', bridgeStart);
assert(bridgeStart >= 0 && bridgeEnd > bridgeStart, 'lookup bridge script is present');
vm.runInContext(html.slice(bridgeStart, bridgeEnd), sandbox);
for (const eventName of ['mousedown', 'mouseup', 'mouseleave']) {
    const expression = new RegExp(`document\\.addEventListener\\('${eventName}', function \\(e\\) \\{([\\s\\S]*?)\\n    \\}\\);`);
    const match = html.match(expression);
    assert(match, `${eventName} listener is present`);
    callbacks[eventName] = vm.runInContext(`(function (e) {${match[1]}\n})`, sandbox);
}
const event = button => ({ button, clientX: 10, clientY: 12, preventDefault() {} });

for (const button of [0, 2]) {
    calls.length = 0;
    callbacks.mousedown(event(button));
    callbacks.mouseup(event(button));
    sandbox.safe_calllunaclickedword(event(button), { word: '猫' }, button === 2);
    const pressed = calls.find(call => call[0] === 'calllunaSourcePressed');
    const released = calls.find(call => call[0] === 'calllunaSourceReleased');
    const lookup = calls.find(call => call[0] === 'calllunaclickedword');
    assert(pressed, 'word mousedown reports press even when over selectable text');
    assert(released, 'word mouseup reports release');
    assert.equal(pressed[1], released[1]);
    assert.equal(lookup[3], pressed[1]);
    assert.equal(lookup[2], button === 2);
    assert.equal(calls.filter(call => call[0] === 'calllunaMousePress').length, 0);
}

calls.length = 0;
sandbox.isPointOverText = () => false;
callbacks.mousedown(event(0));
callbacks.mouseup(event(0));
const blankToken = calls.find(call => call[0] === 'calllunaSourcePressed')[1];
assert(calls.some(call => call[0] === 'calllunaMousePress'), 'blank press preserves drag bridge');
sandbox.isPointOverText = () => true;
callbacks.mousedown(event(0));
const nextToken = calls.filter(call => call[0] === 'calllunaSourcePressed').at(-1)[1];
assert.notEqual(blankToken, nextToken, 'blank/canceled gesture cannot reuse later word token');

calls.length = 0;
callbacks.mouseleave(event(0));
assert(calls.some(call => call[0] === 'calllunaSourceReleased' && call[1] === nextToken),
    'leaving WebView must release the source gesture even if mouseup occurs outside');
assert(calls.some(call => call[0] === 'calllunaLeave'), 'leave still notifies source hover cleanup');

calls.length = 0;
callbacks.mousedown(event(1));
callbacks.mouseup(event(1));
assert(!calls.some(call => /^calllunaSource/.test(call[0])), 'middle click does not start a lookup gesture');

calls.length = 0;
sandbox.luna_current_cursor = 'nw-resize';
callbacks.mousedown(event(0));
assert.equal(calls[0][0], 'calllunaSourcePressed', 'border press lifecycle precedes early return');
assert(calls.some(call => call[0] === 'calllunaMousePress'), 'resize bridge is preserved');
console.log('WebView lookup bridge: 6 dispatch/cancellation scenarios passed');
