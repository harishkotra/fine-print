import socket, threading, time, traceback
import uvicorn
from tests.stub_gateway import app as stub
from app import config, pipeline
from app.otari import Otari

with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
srv = uvicorn.Server(uvicorn.Config(stub, host="127.0.0.1", port=port, log_level="warning"))
threading.Thread(target=srv.run, daemon=True).start()
for _ in range(200):
    if srv.started: break
    time.sleep(0.05)
config.OTARI_BASE_URL = f"http://127.0.0.1:{port}/v1"
config.OTARI_API_KEY = "k"
c = Otari()
try:
    comp = c.complete(model=config.CHECKER_MODEL or "auto",
                      messages=[{"role": "system", "content": pipeline.CHECKER_SYSTEM},
                                {"role": "user", "content": "x"}], max_tokens=1500, step="check")
    print("OK", repr(comp.text[:120]), comp.served_by)
except Exception as e:
    print("ERR", type(e).__name__, e)
    traceback.print_exc()
