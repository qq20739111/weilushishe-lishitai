import sys
import uasyncio as asyncio
import io

class Request:
    def __init__(self, reader):
        self.reader = reader
        self.method = 'GET'
        self.path = '/'
        self.headers = {}
        self.args = {}
        self.body = b''
        self.json = None

    async def read_request(self):
        line = await self.reader.readline()
        if not line:
            return False
        line = line.decode().strip()
        parts = line.split()
        if len(parts) >= 2:
            self.method = parts[0]
            self.path = parts[1]
            if '?' in self.path:
                self.path, query = self.path.split('?', 1)
                for arg in query.split('&'):
                    if '=' in arg:
                        k, v = arg.split('=', 1)
                        self.args[k] = v

        while True:
            line = await self.reader.readline()
            if not line or line == b'\r\n':
                break
            line = line.decode().strip()
            if ':' in line:
                k, v = line.split(':', 1)
                self.headers[k.strip().lower()] = v.strip()

        if 'content-length' in self.headers:
            length = int(self.headers['content-length'])
            self.body = await self.reader.read(length)
            if self.headers.get('content-type') == 'application/json':
                import json
                try:
                    self.json = json.loads(self.body)
                except:
                    pass
        return True

class Response:
    def __init__(self, body='', status_code=200, headers=None):
        self.body = body
        self.status_code = status_code
        self.headers = headers or {}
        if 'Content-Type' not in self.headers:
            self.headers['Content-Type'] = 'text/plain'

    async def write(self, writer):
        writer.write(f'HTTP/1.1 {self.status_code} OK\r\n'.encode())
        for k, v in self.headers.items():
            writer.write(f'{k}: {v}\r\n'.encode())
        
        # Check for file-like object (has read method)
        if hasattr(self.body, 'read'):
            writer.write(b'\r\n')
            await writer.drain()
            
            buf = bytearray(1024)
            while True:
                try:
                    l = self.body.readinto(buf)
                    if not l: break
                    writer.write(buf[:l])
                    await writer.drain()
                except Exception:
                    break
            try:
                self.body.close()
            except:
                pass
        else:
            body_data = self.body
            if isinstance(body_data, str):
                body_data = body_data.encode()
            
            if 'Content-Length' not in self.headers:
                writer.write(f'Content-Length: {len(body_data)}\r\n'.encode())
            
            writer.write(b'\r\n')
            writer.write(body_data)
            await writer.drain()

class Microdot:
    def __init__(self):
        self.routes = []

    def route(self, url, methods=['GET']):
        def decorator(f):
            self.routes.append((url, methods, f))
            return f
        return decorator

    async def handle_request(self, reader, writer):
        req = Request(reader)
        if not await req.read_request():
            writer.close()
            await writer.wait_closed()
            return

        handler = None
        # Simple exact match for now, or prefix for static
        for url, methods, f in self.routes:
            if req.method in methods:
                if url == req.path:
                    handler = f
                    break
                # rudimentary wildcard for static files logic if implemented in handler
        
        if handler:
            try:
                res = handler(req)
                # Check if it is a generator or an awaitable
                # MicroPython's uasyncio check (simplified)
                if hasattr(res, 'send') or hasattr(res, '__await__'): # Check if coroutine/generator
                    try:
                        import uasyncio as asyncio
                        # In latest MicroPython, simply awaiting works, but to check type safely:
                        # We just await it since we are in async context
                        res = await res
                    except AttributeError:
                        pass # Wasn't awaitable after all
            except Exception as e:
                import sys
                sys.print_exception(e)
                res = Response('Internal Server Error', 500)
        else:
            res = Response('Not Found', 404)

        if isinstance(res, str):
            res = Response(res)
        if isinstance(res, dict) or isinstance(res, list):
            import json
            res = Response(json.dumps(res), headers={'Content-Type': 'application/json'})
            
        try:
            await res.write(writer)
            writer.close()
            await writer.wait_closed()
        except OSError:
            pass # Connection reset by peer or closed prematurely


    def run(self, host='0.0.0.0', port=80):
        async def main():
            print(f'Starting web server on {host}:{port}...')
            server = await asyncio.start_server(self.handle_request, host, port)
            while True:
                await asyncio.sleep(3600)
        
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            pass

def send_file(filename, content_type=None):
    if not content_type:
        if filename.endswith('.html'): content_type = 'text/html'
        elif filename.endswith('.css'): content_type = 'text/css'
        elif filename.endswith('.js'): content_type = 'application/javascript'
        elif filename.endswith('.png'): content_type = 'image/png'
        elif filename.endswith('.jpg'): content_type = 'image/jpeg'
        else: content_type = 'text/plain'
        
    try:
        import os
        stat = os.stat(filename)
        size = stat[6]
        f = open(filename, 'rb')
        return Response(f, headers={'Content-Type': content_type, 'Content-Length': str(size)})
    except OSError:
        return Response('File not found', 404)
