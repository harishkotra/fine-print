import base64, json, socket, threading, time, sys
from pathlib import Path
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tests.stub_gateway import app as stub  # noqa: E402
from app import config, pipeline  # noqa: E402

ROOT = Path(__file__).resolve().parent
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
server = uvicorn.Server(uvicorn.Config(stub, host="127.0.0.1", port=port, log_level="warning"))
threading.Thread(target=server.run, daemon=True).start()
for _ in range(200):
    if server.started: break
    time.sleep(0.05)
config.OTARI_BASE_URL = f"http://127.0.0.1:{port}/v1"
config.OTARI_API_KEY = "stub-key"

for name in ["bill_clean", "bill_doctored", "notice_injection", "letter_insurance"]:
    png = (ROOT / "fixtures" / f"{name}.png").read_bytes()
    url = "data:image/png;base64," + base64.b64encode(png).decode()
    r = pipeline.analyze(image_data_url=url, end_user=f"debug-{name}")
    print("=" * 70)
    print(name, r["status"], r["verdict"], "|", r.get("models"))
    for c in r["checks"]:
        print(f"  {c['id']:11s} {c['verdict']:8s} {c['headline']}")
    print("  total:", r["document"].get("total_stated"), "payable:", r["document"].get("amount_payable"),
          "sender:", r["document"].get("sender_name"), "asks:", r["document"].get("asks_for_money"))
    print("  receipts:", [(x["step"], round(x["cost_usd"], 6)) for x in r["receipts"]])
    print("  notes:", r.get("notes"))
