// SPDX-License-Identifier: GPL-2.0-or-later
/**
 * Remote script for the LibreSprite 1.3 async script engine
 * (Promise + setTimeout + storage.fetch).
 *
 * `remote/mcp.js` targets the older QtScript-style API and cannot run on 1.3:
 *   - a script's top-level `this` is undefined there, so `const global = this`
 *     throws and the script aborts while loading;
 *   - `app.yield()` now returns a Promise, so `app.yield("event", delay)` no
 *     longer raises the events the polling loop depends on.
 *
 * This file speaks the same relay protocol as `remote/mcp.js`:
 *   GET  /        -> { "script": "<javascript>" }   (long-poll)
 *   POST /        -> { "output": "<console log>" }
 *   GET  /ping    -> { "status": "pong" }
 *
 * It connects on load (no "Connect" button) and keeps polling in the
 * background.
 *
 * Usage: File > Scripts > mcp-1.3.js
 *    or: libresprite --script <scripts-dir>/mcp-1.3.js
 */

const RELAY_URL = 'http://localhost:64823';

let pending = {};       // storage.fetch key -> resolve callback
let running = false;    // polling loop state
let seq = 0;

function bridgeLog(msg) {
    console.log('[mcp] ' + msg);
}

function newKey(prefix) {
    seq++;
    return prefix + '_' + seq + '_' + Date.now();
}

function delay(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
}

// --- HTTP via storage.fetch (async, event based in LibreSprite 1.3) ---

function waitForFetch(key) {
    return new Promise(function (resolve) {
        pending[key] = function () {
            resolve({
                status: Number(storage.get(key + '_status')),
                body: storage.get(key)
            });
        };
    });
}

function httpGet(url) {
    const key = newKey('mcp_get');
    const done = waitForFetch(key);
    try {
        storage.fetch(url, key);
    } catch (e) {
        delete pending[key];
        return Promise.resolve({ status: 0, body: '', error: e });
    }
    return done;
}

function httpPost(url, body) {
    const key = newKey('mcp_post');
    const done = waitForFetch(key);
    try {
        // 3rd arg = domain, "POST" header key carries the request body.
        storage.fetch(url, key, '', 'POST', body);
    } catch (e) {
        delete pending[key];
        return Promise.resolve({ status: 0, body: '', error: e });
    }
    return done;
}

// --- script execution with captured console output ---

function joinArgs(args) {
    const out = [];
    for (let i = 0; i < args.length; i++) {
        const v = args[i];
        if (typeof v === 'string') out.push(v);
        else if (v === null) out.push('null');
        else if (v === undefined) out.push('undefined');
        else if (typeof v === 'object') {
            try { out.push(JSON.stringify(v)); } catch (e) { out.push(String(v)); }
        } else out.push(String(v));
    }
    return out.join(' ');
}

function runScript(src) {
    return new Promise(function (resolve) {
        let output = '';
        const originalLog = console.log;
        const originalVerbose = console.verbose;
        const originalAssert = console.assert;

        let restored = false;
        function restore() {
            if (restored) return;
            restored = true;
            console.log = originalLog;
            console.verbose = originalVerbose;
            console.assert = originalAssert;
        }

        const capture = function () {
            output += joinArgs(arguments) + '\n';
            try { originalLog.apply(console, arguments); } catch (e) {}
        };

        console.log = capture;
        console.verbose = capture;
        console.assert = function (cond, msg) {
            if (!cond) output += (msg === undefined ? 'assertion failed' : String(msg)) + '\n';
        };

        let result;
        try {
            const fn = new Function(src);
            result = fn();
        } catch (e) {
            output += 'Error: ' + (e && e.message ? e.message : String(e)) + '\n';
            restore();
            resolve(output);
            return;
        }

        if (result && typeof result.then === 'function') {
            result.then(function () {
                restore();
                resolve(output);
            }, function (e) {
                output += 'Error: ' + (e && e.message ? e.message : String(e)) + '\n';
                restore();
                resolve(output);
            });
        } else {
            restore();
            resolve(output);
        }
    });
}

// --- polling loop ---

function step() {
    if (!running) return;

    httpGet(RELAY_URL).then(function (rsp) {
        if (!rsp || rsp.status !== 200) {
            bridgeLog('server unreachable (status ' + (rsp ? rsp.status : 'n/a') + '), retrying...');
            return delay(2000);
        }
        let script = '';
        try {
            const data = JSON.parse(rsp.body);
            script = (data && data.script) || '';
        } catch (e) {
            script = '';
        }
        if (!script) return delay(100);

        return runScript(script).then(function (output) {
            return httpPost(RELAY_URL, JSON.stringify({ output: output }));
        }).then(function () {
            return delay(20);
        });
    }).then(function () {
        if (running) setTimeout(step, 10);
    }, function (err) {
        if (running) setTimeout(step, 1000);
    });
}

function startBridge() {
    if (running) return;
    running = true;
    bridgeLog('connecting to ' + RELAY_URL + ' ...');
    httpGet(RELAY_URL + '/ping').then(function (rsp) {
        if (rsp && rsp.status === 200) bridgeLog('connected, waiting for agent commands');
        else bridgeLog('no MCP server on ' + RELAY_URL + ' yet, will keep retrying');
        step();
    });
}

function stopBridge() {
    running = false;
    bridgeLog('stopped');
}

// --- events ---

function onEvent(event) {
    if (typeof event !== 'string') return;
    if (event.length > 6 && event.substring(event.length - 6) === '_fetch') {
        const key = event.substring(0, event.length - 6);
        const handler = pending[key];
        if (handler) {
            delete pending[key];
            handler();
        }
    }
}

startBridge();
