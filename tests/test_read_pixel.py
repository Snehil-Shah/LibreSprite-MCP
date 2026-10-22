"""Read-pixel regressions. Requires Node.js on PATH to execute the generated JS.

Run: .venv/Scripts/python -m unittest discover -s tests -p test_read_pixel.py -v
Native proof is separate and does not require Node.js.
"""
import asyncio
import threading
import json
import subprocess
import unittest
from libresprite_mcp.mcp_server import MCPServer

class ScriptProxy:
    def __init__(self, app):
        self.app = app
        self.calls = 0
    def run_script(self, script, ctx):
        self.calls += 1
        setup = '''
const spec = APP;
let reads = 0;
// This native build converts helper arguments to signed int; passing the
// normalized unsigned packed result back into helpers loses RGB channels.
const nativeColor = v => v > 2147483647 ? -2147483648 : v;
const app = {activeImage: spec.image, pixelColor: {
 rgbaR: v => nativeColor(v) & 255, rgbaG: v => (nativeColor(v) >>> 8) & 255,
 rgbaB: v => (nativeColor(v) >>> 16) & 255, rgbaA: v => (nativeColor(v) >>> 24) & 255,
 grayaV: v => v & 255, grayaA: v => (v >>> 8) & 255}};
const ColorMode = {RGB: 0, GRAYSCALE: 1, INDEXED: 2, BITMAP: 3};
if (app.activeImage) app.activeImage.getPixel = (x,y) => {
 if (x < 0 || y < 0 || x >= app.activeImage.width || y >= app.activeImage.height) throw Error('Unsafe native read');
 reads++; return spec.value;
};
'''.replace('APP', json.dumps(self.app))
        result = subprocess.run(['node', '-e', setup + script + '\nconsole.error(reads);'], text=True, capture_output=True, check=True)
        self.reads = int(result.stderr.strip())
        return result.stdout.strip()

class ReadPixelTests(unittest.IsolatedAsyncioTestCase):
    def proxy(self, mode=0, value=0x80332211, image=True):
        return ScriptProxy({'image': {'width': 2, 'height': 3, 'format': mode} if image else None, 'value': value})
    async def call(self, proxy, x=1, y=2):
        result = await MCPServer(proxy).mcp.call_tool('read_pixel', {'x': x, 'y': y})
        if isinstance(result, tuple): result = result[0]
        return json.loads(result[0].text)
    async def test_relay_wait_keeps_event_loop_responsive(self):
        release = threading.Event()
        class BlockingProxy:
            released_during_wait = False
            def run_script(self, script, ctx):
                self.released_during_wait = release.wait(timeout=0.3)
                return '{"x": 1, "y": 2, "color_mode": "rgb", "value": 2150834705, "rgba": [17, 34, 51, 128]}'
        proxy = BlockingProxy()
        async def release_from_event_loop():
            await asyncio.sleep(0.02)
            release.set()
        ticker = asyncio.create_task(release_from_event_loop())
        try:
            await self.call(proxy)
            await ticker
            self.assertTrue(proxy.released_during_wait,
                            "The relay blocked the MCP event loop until the fake wait timed out")
        finally:
            release.set()
            await ticker

    async def test_rgb_and_repeated_reads_preserve_value(self):
        proxy = self.proxy(value=-2144132591)
        for _ in range(2):
            result = await self.call(proxy)
            self.assertEqual(result, {'x':1, 'y':2, 'color_mode':'rgb', 'value':0x80332211, 'rgba':[17,34,51,128]})
            self.assertEqual(proxy.reads, 1)
        self.assertEqual(proxy.calls, 2)
    async def test_unsigned_native_rgb_is_decoded_through_signed_helpers(self):
        result = await self.call(self.proxy(value=0x80332211))
        self.assertEqual(result['rgba'], [17,34,51,128])
        self.assertEqual(result['value'], 0x80332211)
    async def test_grayscale(self):
        result = await self.call(self.proxy(1, 0x8040))
        self.assertEqual(result['rgba'], [64,64,64,128])
        self.assertEqual(result['color_mode'], 'grayscale')
    async def test_index_is_not_misrepresented_as_rgba(self):
        result = await self.call(self.proxy(2, 7))
        self.assertEqual(result['palette_index'], 7)
        self.assertEqual(result['color_mode'], 'indexed')
        self.assertNotIn('rgba', result)
    async def test_missing_image(self):
        proxy = self.proxy(image=False)
        with self.assertRaisesRegex(Exception, 'No active image'): await self.call(proxy)
        self.assertEqual(proxy.reads, 0)
    async def test_bounds_before_native_read(self):
        for x,y in [(-1,0),(0,-1),(2,0),(0,3)]:
            proxy = self.proxy()
            with self.assertRaisesRegex(Exception, 'outside'): await self.call(proxy,x,y)
            self.assertEqual(proxy.reads, 0)
    async def test_unsupported_mode_before_native_read(self):
        proxy = self.proxy(3)
        with self.assertRaisesRegex(Exception, 'Unsupported'): await self.call(proxy)
        self.assertEqual(proxy.reads, 0)
    async def test_non_integer_rejected_before_relay(self):
        for x in [0.5, True, '1', '0; throw Error()']:
            proxy = self.proxy()
            with self.assertRaises(Exception): await self.call(proxy,x,0)
            self.assertEqual(proxy.calls, 0)

class ReadPixelResponseTests(unittest.IsolatedAsyncioTestCase):
    async def response(self, output):
        class Proxy:
            def run_script(self, script, ctx):
                return output
        content = await MCPServer(Proxy()).mcp.call_tool('read_pixel', {'x': 1, 'y': 2})
        if isinstance(content, tuple):
            content = content[0]
        return json.loads(content[0].text)

    async def test_malformed_responses_are_tool_errors(self):
        valid = {'x': 1, 'y': 2, 'color_mode': 'rgb', 'value': 0x80332211,
                 'rgba': [17, 34, 51, 128]}
        invalid = [None, '', 'not json', 'null', '[]', '{}', '123', '"text"',
                   json.dumps({'garbage': True})]
        for key in valid:
            missing = dict(valid)
            missing.pop(key)
            invalid.append(json.dumps(missing))
        for key, value in [('x', True), ('x', 2), ('y', 3), ('value', True),
                           ('value', -1), ('value', 4294967296), ('color_mode', 'bitmap'),
                           ('rgba', [17, 34, 51]), ('rgba', [17, True, 51, 128]),
                           ('rgba', [17, 34, 51, 256]), ('rgba', [17, 34, 51, -1]),
                           ('rgba', [17, 34, 51, 128.0]), ('rgba', [18, 34, 51, 128]),
                           ('value', 0x80332212)]:
            invalid.append(json.dumps({**valid, key: value}))
        indexed = {'x': 1, 'y': 2, 'color_mode': 'indexed', 'value': 7, 'palette_index': 7}
        for index in [None, True, -1, 7.5, '7', 8]:
            invalid.append(json.dumps({**indexed, 'palette_index': index}))
        invalid.append(json.dumps({**indexed, 'value': -1}))
        gray = {'x': 1, 'y': 2, 'color_mode': 'grayscale', 'value': 65536,
                'rgba': [64, 64, 64, 128]}
        invalid.append(json.dumps(gray))
        invalid.append(json.dumps({**gray, 'value': 0x8040, 'rgba': [64, 65, 64, 128]}))
        invalid.append(json.dumps({**gray, 'value': 0x8041}))
        for output in invalid:
            with self.subTest(output=output):
                with self.assertRaises(Exception):
                    await self.response(output)

    async def test_valid_modes_and_compatible_extra_fields_are_preserved(self):
        cases = [
            {'x': 1, 'y': 2, 'color_mode': 'rgb', 'value': 0x80332211,
             'rgba': [17, 34, 51, 128], 'native_version': 'test'},
            {'x': 1, 'y': 2, 'color_mode': 'grayscale', 'value': 0x8040,
             'rgba': [64, 64, 64, 128]},
            {'x': 1, 'y': 2, 'color_mode': 'indexed', 'value': 7, 'palette_index': 7},
        ]
        for result in cases:
            with self.subTest(result=result):
                self.assertEqual(await self.response(json.dumps(result)), result)

    async def test_explicit_native_error_is_preserved(self):
        with self.assertRaisesRegex(Exception, 'No active image'):
            await self.response('{"error":"No active image"}')


if __name__ == '__main__': unittest.main()
