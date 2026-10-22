"""
MCP server implementation that exposes tools for interacting with the libresprite-proxy server.
"""

import asyncio
import json
import os
from pydantic import StrictInt
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

        @self.mcp.tool()
        async def read_pixel(x: StrictInt, y: StrictInt, ctx: Context) -> dict:
            """Read a pixel in the active layer/frame's cel image without editing it.

            x and y are zero-based integer image-local coordinates, not canvas
            coordinates. RGB/grayscale return RGBA channels (0-255); indexed
            images return the stored palette index, not a composited color.
            Missing images, unsupported formats and out-of-bounds coordinates
            produce an error.
            """
            script = """
(function () {
    var image = app.activeImage;
    if (!image) {
        console.log(JSON.stringify({error: "No active image in the current layer/frame."}));
        return;
    }
    var x = X_COORD, y = Y_COORD;
    if (x < 0 || y < 0 || x >= image.width || y >= image.height) {
        console.log(JSON.stringify({error: "Pixel coordinates are outside the active image."}));
        return;
    }
    var mode = image.format;
    if (mode !== ColorMode.RGB && mode !== ColorMode.GRAYSCALE && mode !== ColorMode.INDEXED) {
        console.log(JSON.stringify({error: "Unsupported active image color mode."}));
        return;
    }
    // Native helpers on older builds accept signed 32-bit packed colors.
    var value = image.getPixel(x, y) | 0;
    var result = {x: x, y: y, value: value >>> 0};
    var pc = app.pixelColor;
    if (mode === ColorMode.RGB) {
        result.color_mode = "rgb";
        result.rgba = [pc.rgbaR(value), pc.rgbaG(value), pc.rgbaB(value), pc.rgbaA(value)];
    } else if (mode === ColorMode.GRAYSCALE) {
        result.color_mode = "grayscale";
        var gray = pc.grayaV(value);
        result.rgba = [gray, gray, gray, pc.grayaA(value)];
    } else {
        result.color_mode = "indexed";
        result.palette_index = value;
    }
    console.log(JSON.stringify(result));
})();
""".replace("X_COORD", str(x)).replace("Y_COORD", str(y))
            output = await asyncio.to_thread(self._libresprite_proxy.run_script, script, ctx)
            try:
                result = json.loads(output)
            except (TypeError, ValueError) as exc:
                raise RuntimeError("LibreSprite did not return a valid pixel result: " + str(output)) from exc
            if not isinstance(result, dict):
                raise RuntimeError("LibreSprite did not return a valid pixel result object.")
            if "error" in result:
                raise RuntimeError(result["error"])
            value = result.get("value")
            mode = result.get("color_mode")
            if (type(result.get("x")) is not int or result["x"] != x
                    or type(result.get("y")) is not int or result["y"] != y
                    or type(value) is not int or not 0 <= value <= 4294967295
                    or mode not in ("rgb", "grayscale", "indexed")):
                raise RuntimeError("LibreSprite did not return a valid pixel result.")
            if mode == "indexed":
                index = result.get("palette_index")
                if type(index) is not int or index < 0 or index != value:
                    raise RuntimeError("LibreSprite did not return a valid indexed pixel result.")
            else:
                rgba = result.get("rgba")
                if (not isinstance(rgba, list) or len(rgba) != 4
                        or any(type(channel) is not int or not 0 <= channel <= 255 for channel in rgba)
                        or (mode == "grayscale" and value > 65535)):
                    raise RuntimeError("LibreSprite did not return a valid RGBA pixel result.")
                if mode == "rgb":
                    expected_value = sum(channel << (8 * position) for position, channel in enumerate(rgba))
                else:
                    if rgba[0] != rgba[1] or rgba[0] != rgba[2]:
                        raise RuntimeError("LibreSprite did not return consistent grayscale channels.")
                    expected_value = rgba[0] | (rgba[3] << 8)
                if value != expected_value:
                    raise RuntimeError("LibreSprite did not return a consistent packed pixel value.")
            return result

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