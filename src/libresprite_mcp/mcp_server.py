"""
MCP server implementation that exposes tools for interacting with the libresprite-proxy server.
"""

import os
from mcp.server.fastmcp import FastMCP, Context
from .libresprite_proxy import LibrespriteProxy


class MCPServer:
    """The LibreSprite MCP Server."""

    def __init__(self, libresprite_proxy: LibrespriteProxy, server_name: str = "libresprite"):
        # Cache the libresprite proxy instance
        self._libresprite_proxy = libresprite_proxy

        # Initialize FastMCP
        self.mcp = FastMCP(server_name)

        # Setup MCP tools, prompts, and resources
        self._setup_tools()
        self._setup_resources()
        self._setup_prompts()

    def _setup_tools(self):
        """Setup MCP tools."""

        @self.mcp.tool()
        async def run_script(script: str, ctx: Context) -> str:
            """
            Run a JavaScript script inside Libresprite.

            IMPORTANT: Make sure you are well versed with the documentation and examples provided in the resources `docs:reference` and `docs:examples`.

            Args:
                script: The script to execute

            Returns:
                Console output
            """
            return await self._libresprite_proxy.run_script(script, ctx)

    def _setup_resources(self):
        """Setup MCP resources."""

        base_dir = os.path.dirname(os.path.abspath(__file__))

        @self.mcp.resource("docs://reference")
        def read_reference() -> str:
            """Read the libresprite command reference documentation."""
            doc_path = os.path.join(base_dir, "resources", "reference.txt")
            try:
                with open(doc_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                return f"Error reading reference.txt: {e}"

        @self.mcp.resource("docs://examples")
        def read_examples() -> str:
            """Read example scripts using libresprite commands."""
            example_path = os.path.join(base_dir, "resources", "examples.txt")
            try:
                with open(example_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                return f"Error reading examples.txt: {e}"

    def _setup_prompts(self):
        """Setup MCP prompts."""

        @self.mcp.prompt(title="libresprite")
        def libresprite(prompt: str) -> str:
            """
            Prompt template to use the libresprite tool with proper context conditioning.

            Args:
                prompt: User prompt

            Returns:
                Prompt to process
            """
            return f"""
            Libresprite is a program for creating and editing pixel art and animations using JavaScript.

            Before proceeding, please ensure you are well versed with the documentation and examples provided in the resources `docs:reference` and `docs:examples`.

            You can use the `run_script` tool to execute JavaScript scripts in the context of libresprite.

            Here's what you need to do using the above tools and resources:

            {prompt}
            """

    def run(self, transport: str = 'stdio'):
        """Run the MCP server."""
        self.mcp.run(transport=transport)