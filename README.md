# LibreSprite-MCP

[![Install MCP Server](https://cursor.com/deeplink/mcp-install-light.svg)](https://cursor.com/install-mcp?name=libresprite&config=JTdCJTIyY29tbWFuZCUyMiUzQSUyMnV2eCUyMGxpYnJlc3ByaXRlLW1jcCUyMiU3RA%3D%3D)
[![PyPI version](https://img.shields.io/pypi/v/libresprite-mcp)](https://pypi.org/project/libresprite-mcp/)

> Prompt your way into LibreSprite

Model Context Protocol (MCP) server for prompt-assisted editing, designing, and scripting inside LibreSprite.

https://github.com/user-attachments/assets/71440bba-16a5-4ee2-af10-2c346978a290

## Prerequisites

[`uv`](https://docs.astral.sh/uv/) is the recommended way to install and use this server. Here are quick one-liners to install it if you haven't:

- **Windows**: (run as administrator)

    ```powershell
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```

- **Unix**:

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

More on [installing `uv`](https://docs.astral.sh/uv/getting-started/installation/).

The package is published on [PyPI](https://pypi.org/project/librespsrite-mcp/), so feel free to consume it any other way you prefer (`pipx`, etc)

## Usage

### Step 1: Setting up the client

Add the MCP server with the following entrypoint command (or something else if you are not using `uv`) to your MCP client:

```bash
uvx libresprite-mcp
```

#### Examples:

- **Claude Desktop & Cursor**

    Edit _Claude > Settings > Developer > Edit Config > claude_desktop_config.json_ or _.cursor > mcp.json_ to include the server:
    
    ```json
    {
        "mcpServers": {
            // ...existing servers...
            "libresprite": {
                "type": "stdio",
                "command": "uvx",
                "args": [
                    "libresprite-mcp"
                ]
            }
            // ...existing servers...
        }
    }
    ```

    You can also use this fancy badge to make it quick:
  
    [![Install MCP Server](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/install-mcp?name=libresprite&config=JTdCJTIyY29tbWFuZCUyMiUzQSUyMnV2eCUyMGxpYnJlc3ByaXRlLW1jcCUyMiU3RA%3D%3D)

> [!NOTE]
> You will have to restart Claude Desktop to load the MCP Server.

### Step 2: Setting up LibreSprite

> [!IMPORTANT]
> Pick the remote script that matches your LibreSprite version.
>
> | LibreSprite version | Remote script |
> | --- | --- |
> | 1.3 and newer (new async script engine) | `remote/mcp-1.3.js` |
> | older builds (QtScript engine) | `remote/mcp.js` |
>
> LibreSprite 1.3 replaced the script engine: a script's top-level `this` is
> `undefined`, and `app.yield()` returns a `Promise` instead of raising an
> event. `mcp.js` relies on both of the old behaviours, so on 1.3 it aborts at
> load time (`TypeError: cannot read property 'console' of undefined`) and its
> polling loop never runs. `mcp-1.3.js` implements the same relay protocol on
> top of `Promise` / `setTimeout` / `storage.fetch` and connects
> automatically, without the "Connect" button.

Download the remote script and add it to LibreSprite's scripts folder:

![scripts-folder](https://raw.githubusercontent.com/Snehil-Shah/libresprite-mcp/main/assets/scripts-folder.png)

### Step 3: Connect and use

Run the script from `File > Scripts` (or start LibreSprite with
`--script <path-to-script>`) and make sure your MCP server is running
(Claude Desktop/Cursor is loaded and running).

- `remote/mcp.js`: you should see the following screen. Click the "Connect"
  button and you can now start talking to Claude about your next big pixel-art
  project.
- `remote/mcp-1.3.js`: it connects by itself and logs
  `[mcp] connected, waiting for agent commands` to the console.

![connect-button](https://raw.githubusercontent.com/Snehil-Shah/libresprite-mcp/main/assets/connect.png)

## Some pointers

- You can only run one instance of the MCP server at a time.
- The server expects port `64823` to be free.
- `ModuleNotFoundError: No module named 'mcp.server.fastmcp'` means the client
  resolved `mcp 2.x` (FastMCP was renamed there). Upgrade to a release that
  pins `mcp<2`, or run `uvx --with "mcp<2" libresprite-mcp`.
- The server has a hacky and brittle implementation (see [ARCHITECTURE](https://github.com/Snehil-Shah/libresprite-mcp/blob/main/ARCHITECTURE.md)), and is not extensively tested.
- The MCP resources are kinda low quality with unclear API reference and limited examples, leaving the LLM confused at times. If you're a LibreSprite expert, we need your help.

***
