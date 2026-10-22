/**
 * Source: https://github.com/Snehil-Shah/libresprite-mcp
 */

// Cache the global context.
// NOTE: LibreSprite 1.3+ runs scripts as ES modules, where top-level `this` is undefined.
const global = typeof globalThis !== 'undefined' ? globalThis : this;

/**
 * Model Context Protocol (MCP) remote script that interacts with the libresprite-mcp server.
 *
 * NOTE: Defined as an IIFE to avoid global namespace pollution.
 */
(function MCP() {
    // CONSTANTS //

    /**
     * URL to the relay server exposing the next command.
     */
    const RELAY_SERVER_URL = 'http://localhost:64823';

    /**
     * Delay between polling requests. (in number of rendering cycles)
     */
    const POLL_DELAY = 120;

    /**
     * Flag indicating whether the script is running on the LibreSprite 1.3+ scripting engine.
     */
    const NEW_ENGINE = typeof setTimeout === 'function';


    // VARIABLES //

    /**
     * Flag indicating extension state.
     *
     * @type {boolean}
     */
    let active = false;

    /**
     * Flag indicating whether polling is active.
     *
     * @type {boolean}
     */
    let polling = false;

    /**
     * Flag indicating whether the client is connected to the server.
     *
     * @type {boolean}
     */
    let connected = false;

    /**
     * Stores stdout.
     *
     * @type {string}
     */
    let output = '';

    /**
     * Function to get response from storage in the next cycle.
     *
     * @type {Function|null}
     */
    let _get_response = null;

    /**
     * Function to post response to storage in the next cycle.
     *
     * @type {Function|null}
     */
    let _post_response = null;

    /**
     * Dialog instance for UI.
     */
    let dialog = null;

    /**
     * Status label in the UI dialog.
     */
    let statusLabel = null;

    /**
     * Connect/Disconnect button in the UI dialog.
     */
    let toggleButton = null;


    // FUNCTIONS //

    /**
     * Global `console.log`.
     */
    const _clientLogger = global.console.log;

    // Override global console object to capture stdout.
    const console = Object.assign({}, global.console);

    /**
     * Modified `console.log` that captures output before logging.
     */
    console.log = function() {
        var args = Array.prototype.slice.call(arguments);
        output += args.join(' ') + '\n';
        _clientLogger.apply(null, args);
    }

    /**
     * Raises an event after the given number of rendering cycles.
     *
     * NOTE: In LibreSprite 1.3+, `app.yield()` returns a Promise instead of raising an event, so we use timers instead.
     *
     * @param {string} event - event to raise
     * @param {number} [cycles] - delay (in number of rendering cycles)
     */
    function yieldEvent(event, cycles) {
        if (NEW_ENGINE) {
            // A rendering cycle is a ~10ms tick...
            setTimeout(function() { onEvent(event); }, (cycles || 0) * 10);
            return;
        }
        app.yield(event, cycles);
    }

    /**
     * Makes a GET request.
     *
     * @private
     * @param {string} url - url to fetch
     * @param {Function} cb - callback function to handle the response
     */
    function _get(url, cb) {
        storage.fetch(url, '_get_response');
        _get_response = function() {
            const status = storage.get('_get_response' + '_status');
            const string = storage.get('_get_response');
            cb({
                string,
                status
            });
        };
    }

    /**
     * Makes a POST request.
     *
     * @private
     * @param {string} url - url to fetch
     * @param {string} body - request body
     * @param {Function} cb - callback function to handle the response
     */
    function _post(url, body, cb) {
        storage.fetch(url, '_post_response', "", "POST", body, "Content-Type", "application/json");
        _post_response = function() {
            const status = storage.get('_post_response' + '_status');
            const string = storage.get('_post_response');
            cb({
                string,
                status
            });
        }
    }

    /**
     * Makes a GET request.
     *
     * @param {string} url - url to fetch
     * @param {Function} cb - callback function to handle the response
     */
    function get(url, cb) {
        _get(url, function(rsp) {
            var data, error = rsp.status != 200 ? 'status:' + rsp.status : 0;
            try {
                if (!error)
                    data = JSON.parse(rsp.string);
            } catch (ex) {
                error = ex;
            }
            cb(data, error);
        });
    }

    /**
     * Makes a POST request.
     *
     * @param {string} url - url to fetch
     * @param {Object} body - request body
     * @param {Function} cb - callback function to handle the response
     */
    function post(url, body, cb) {
        _post(url, body, function(rsp) {
            var data, error = rsp.status != 200 ? 'status:' + rsp.status : 0;
            try {
                if (!error)
                    data = JSON.parse(rsp.string);
                else error += rsp.string;
            } catch (ex) {
                error = ex;
            }
            cb(data, error);
        });
    }

    /**
     * Pings for server health.
     *
     * This yields a "bad_health" event if the server is unreachable,
     * or an "init" event if the server is reachable.
     */
    function checkServerHealth() {
        get(RELAY_SERVER_URL + '/ping', function(data, error) {
            if (error) {
                connected = false;
                yieldEvent("bad_health", POLL_DELAY);
                return;
            }
            if (data && data.status === 'pong') {
                connected = true;
                yieldEvent("good_health");
            } else {
                connected = false;
                yieldEvent("bad_health", POLL_DELAY);
            }

        });
    }

    /**
     * Fetches the next script from the server.
     *
     * @param {Function} cb - script handler
     */
    function getScript(cb) {
        get(RELAY_SERVER_URL, function(data, error) {
            if (error) {
                // The post request will log the error.
                cb('');
                return;
            }
            cb((data && data.script) ? data.script : '');
        });
    }

    /**
     * Posts the output to the server.
     */
    function postOutput() {
        const body = JSON.stringify({output: output});
        post(RELAY_SERVER_URL, body, function(data, error) {
            // NOTE: This is the last interaction with the MCP server for a tool call and hence we ensure updates to the UI and connection status.
            if (error) {
                _clientLogger('The MCP server was shut down.');
                connected = false;
                stopPolling();
                paintUI();
                yieldEvent("bad_health", POLL_DELAY);
                return;
            }
            if ( !data ) {
                _clientLogger('Something went wrong. Please report it on https://github.com/Snehil-Shah/libresprite-mcp/issues.');
                return;
            }
            if ( data.status === 'invalid' )
                _clientLogger('Something is wrong. Please report it on https://github.com/Snehil-Shah/libresprite-mcp/issues.');
            // Other status types can be ignored...
            // Continue polling...
            if (!polling) {
                return;
            }
            yieldEvent("poll", POLL_DELAY);
        });
    }

    /**
     * Runs a script in the current context.
     *
     * @param {string} script - script to run
     */
    function runScript(script) {
        if (!script) {
            return;
        }
        try {
            // Execute in global scope with our custom logger...
            new Function('console', script)(console);
        } catch (e) {
            console.log('Error in script:', e.message);
        }
    }

    /**
     * Fetches, executes, and posts the output for the next script.
     *
     * NOTE: This is the entry point for the polling loop.
     */
    function exec() {
        if (!polling) return;
        getScript(script => {
            output = ''; // sanity reset
            runScript(script);
            postOutput();
        });
    }

    /**
     * Starts the polling loop.
     */
    function startPolling() {
        if (polling) return;
        polling = true;
        exec();
    }

    /**
     * Stops the polling loop.
     */
    function stopPolling() {
        polling = false;
    }

    /**
     * Paints the UI dialog based on the current state.
     */
    function paintUI() {
        let label, button;
        if (!connected) {
            label = 'Discovering MCP servers... Make sure the libresprite-mcp server is running.';
            button = 'Waiting...';
        } else if (polling) {
            label = 'Connected to the libresprite-mcp server!';
            button = 'Disconnect';
        } else {
            label = 'Found an active libresprite-mcp server, "Connect" when you are ready!';
            button = 'Connect';
        }
        // NOTE: LibreSprite 1.3+ only shows dialogs created while the script is loading, so we create the dialog once and update it in place.
        if (dialog) {
            statusLabel.text = label;
            toggleButton.text = button;
            return;
        }
        dialog = app.createDialog();
        dialog.title = 'libresprite-mcp';
        statusLabel = dialog.addLabel(label, 'status');
        dialog.addBreak();
        toggleButton = dialog.addButton(button, 'toggle');
    }


    // MAIN //

    /**
     * Event handler.
     *
     * @global
     * @param {string} event
     */
    function onEvent(event) {
        switch (event) {
            /**
             * Initialize script.
             */
            case 'init':
                active = true;
                checkServerHealth();
                paintUI();
                return;
            /**
             * Cleanup script.
             */
            case '_close':
                active = false;
                connected = false;
                polling = false;
                return;
            /**
             * Events triggered by initial health checks.
             */
            case 'bad_health':
                if (!active) {
                    // The extension was closed, stop recursion...
                    return;
                }
                checkServerHealth();
                return;
            case 'good_health':
                paintUI();
                return;
            /**
             * UI operation.
             */
            case 'toggle_click':
                if (!connected) {
                    // The button is visible before a server is found, ignore clicks until then...
                    return;
                }
                if (polling) {
                    stopPolling();
                } else {
                    startPolling();
                }
                paintUI();
                return;
            /**
             * Successful 'GET' event response triggered by `storage.fetch`.
             */
            case '_get_response_fetch':
                _get_response && _get_response();
                _get_response = null;
                return;
            /**
             * Successful 'POST' event response triggered by `storage.fetch`.
             */
            case '_post_response_fetch':
                _post_response && _post_response();
                _post_response = null;
                return;
            /**
             * Event triggered to continue polling the endpoint.
             */
            case 'poll':
                if (!active) {
                    // The extension was closed, stop recursion...
                    // NOTE: This is a sanity check and should never be executed given the close button is not visible during polling
                    stopPolling();
                    return;
                }
                exec();
                return;
            default:
                // No action for unknown events
                break;
        }
    }
    global.onEvent = onEvent;
})();