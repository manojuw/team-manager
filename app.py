import threading
import time

def install_tornado_proxy():
    try:
        import tornado.web
        import tornado.httpclient
        from streamlit.web.server.server import Server

        for _ in range(60):
            if Server._singleton is not None:
                break
            time.sleep(0.5)

        if Server._singleton is None:
            with open("/tmp/proxy_install.log", "a") as f:
                f.write("Server._singleton still None after 30s\n")
            return

        server_instance = Server._singleton

        class ProxyHandler(tornado.web.RequestHandler):
            SUPPORTED_METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD")

            async def get(self, *args, **kwargs):
                await self._proxy()
            async def post(self, *args, **kwargs):
                await self._proxy()
            async def put(self, *args, **kwargs):
                await self._proxy()
            async def delete(self, *args, **kwargs):
                await self._proxy()
            async def patch(self, *args, **kwargs):
                await self._proxy()
            async def options(self, *args, **kwargs):
                await self._proxy()
            async def head(self, *args, **kwargs):
                await self._proxy()

            def _get_target(self):
                path = self.request.uri
                if path.startswith("/api/management/"):
                    rewrite = "/api/" + path[len("/api/management/"):]
                    return 3001, rewrite
                elif path.startswith("/api/ai/"):
                    rewrite = "/api/" + path[len("/api/ai/"):]
                    return 8001, rewrite
                else:
                    return 5001, path

            async def _proxy(self):
                port, path = self._get_target()
                client = tornado.httpclient.AsyncHTTPClient()
                url = f"http://127.0.0.1:{port}{path}"

                body = self.request.body if self.request.body else None
                if self.request.method in ("GET", "HEAD", "OPTIONS"):
                    body = None

                headers = {}
                for k, v in self.request.headers.get_all():
                    if k.lower() not in ("host", "transfer-encoding"):
                        headers[k] = v

                try:
                    resp = await client.fetch(
                        url,
                        method=self.request.method,
                        headers=headers,
                        body=body,
                        allow_nonstandard_methods=True,
                        request_timeout=120,
                        follow_redirects=False,
                        raise_error=False,
                    )
                    self.set_status(resp.code)
                    for k, v in resp.headers.get_all():
                        if k.lower() not in ("transfer-encoding", "content-encoding", "connection", "content-length"):
                            try:
                                self.add_header(k, v)
                            except:
                                pass
                    if resp.body:
                        self.write(resp.body)
                except Exception as e:
                    self.set_status(502)
                    self.write(f"Proxy error: {e}")

                self.finish()

        tornado_app = getattr(server_instance, '_app', None)

        if tornado_app and hasattr(tornado_app, 'wildcard_router'):
            rules = tornado_app.wildcard_router.rules
            proxy_patterns = [
                r"/login.*",
                r"/signup.*",
                r"/dashboard.*",
                r"/api/management/.*",
                r"/api/ai/.*",
                r"/_next/.*",
                r"/__nextjs.*",
                r"/favicon\.ico",
            ]
            for pattern in reversed(proxy_patterns):
                rule = tornado.web.url(pattern, ProxyHandler)
                rules.insert(0, rule)

            with open("/tmp/proxy_install.log", "a") as f:
                f.write(f"Proxy installed with {len(proxy_patterns)} route rules\n")
        else:
            with open("/tmp/proxy_install.log", "a") as f:
                f.write(f"No tornado_app or wildcard_router found\n")
                if tornado_app:
                    f.write(f"App attrs: {[a for a in dir(tornado_app) if not a.startswith('_')]}\n")
                else:
                    f.write(f"Server attrs: {[a for a in dir(server_instance) if not a.startswith('_')]}\n")

    except Exception as e:
        import traceback
        with open("/tmp/proxy_install.log", "a") as f:
            f.write(f"Proxy install error: {e}\n{traceback.format_exc()}\n")

proxy_thread = threading.Thread(target=install_tornado_proxy, daemon=True)
proxy_thread.start()

import streamlit as st
st.set_page_config(page_title="Teams Knowledge Base", layout="wide")

redirect_html = """
<script>
(function() {
    setTimeout(function() {
        if (window.top !== window.self) {
            window.top.location.href = '/login';
        } else {
            window.location.href = '/login';
        }
    }, 1000);
})();
</script>
<div style="display:flex;align-items:center;justify-content:center;height:200px;">
<p style="font-size:18px;color:#666;">Loading Teams Knowledge Base...</p>
</div>
"""
st.components.v1.html(redirect_html, height=200)
