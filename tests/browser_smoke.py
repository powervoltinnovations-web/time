"""Real browser regression checks on disposable data from the supplied CSV."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"


def run():
    ARTIFACTS.mkdir(exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory(prefix="strict-rooms-") as folder:
        environment = {**os.environ, "UNISCHED_DB": str(Path(folder) / "test.db")}
        with (ARTIFACTS / "browser-server.log").open("w") as log:
            server = subprocess.Popen(
                [sys.executable, "run.py", "--port", str(port)], cwd=ROOT,
                env=environment, stdout=log, stderr=log,
            )
            try:
                for _ in range(100):
                    try:
                        with urlopen(base + "/api/health", timeout=1) as response:
                            assert json.load(response)["status"] == "ok"
                        break
                    except OSError:
                        if server.poll() is not None:
                            raise RuntimeError("Server exited; see artifacts/browser-server.log")
                        time.sleep(0.1)
                else:
                    raise RuntimeError("Server did not become ready")
                with sync_playwright() as p:
                    browser = p.chromium.launch(
                        headless=True,
                        executable_path=os.environ.get("CHROMIUM_PATH") or shutil.which("chromium"),
                    )
                    page = browser.new_page(viewport={"width": 1440, "height": 1050})
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(base + "/#generate")
                    expect(page.get_by_role("heading", name="A timetable for your division.", exact=True)).to_be_visible()
                    page.locator("#scope-semester").select_option("3")
                    page.get_by_role("button", name="Generate Division A", exact=False).click()
                    expect(page.locator('[name="flexible_practicals"]')).to_have_count(0)
                    expect(page.locator("#modal")).to_contain_text("Every lab batch uses an eligible laboratory")
                    expect(page.get_by_label("Minimum lectures before a room change")).to_have_value("2")
                    page.get_by_label("Minimum lectures before a room change").select_option("3")
                    page.locator("#modal").get_by_role("button", name="Generate timetable", exact=True).click()
                    expect(page.locator(".timetable")).to_be_visible(timeout=35000)
                    history = page.request.get(base + "/api/generations").json()
                    assert len(history) == 1 and history[0]["status"] == "feasible"
                    saved_id = history[0]["id"]
                    saved = page.request.get(base + f"/api/generations/{saved_id}").json()
                    audit = page.request.get(base + f"/api/generations/{saved_id}/analytics").json()
                    assert audit["hard_conflicts"] == 0
                    assert audit["classroom_optimization"]["early_changes"] == 0
                    # Browser editor must follow the same strict room rules even for legacy flags.
                    choices = page.evaluate("""record => {
                        record.config.settings.practical_classroom_codes = record.config.subjects.map(s=>s.code);
                        return record.result.entries.filter(e=>['lab','lecture'].includes(e.kind)).map(e=>({
                            kind:e.kind, rooms:manualRoomChoices(e,record.config).map(([id])=>
                                record.config.rooms.find(r=>r.id===id).kind)
                        }));
                    }""", saved)
                    assert all(c["rooms"] and set(c["rooms"]) == ({"lab"} if c["kind"] == "lab" else {"classroom"})
                               for c in choices)
                    page.screenshot(path=str(ARTIFACTS / "strict-room-timetable.png"), full_page=True)

                    page.goto(base + "/#subjects")
                    page.get_by_role("tab", name="Teachers").click()
                    expect(page.get_by_role("tab", name="Teachers")).to_have_attribute("aria-selected", "true")
                    expect(page.get_by_role("button", name="Edit teacher", exact=True).first).to_be_visible()
                    page.get_by_role("tab", name="Subjects").click()
                    original = page.request.get(base + "/api/config").json()
                    subject = original["configuration"]["subjects"][0]
                    row = page.locator("#setup-table tr").filter(has_text=subject["code"]).first
                    row.get_by_role("button", name="Edit subject", exact=True).click()
                    page.get_by_label("Subject name", exact=True).fill("Edited mathematics")
                    page.get_by_role("button", name="Save subject", exact=True).click()
                    expect(page.locator("#modal")).not_to_be_visible()
                    page.reload()
                    expect(page.locator("#setup-table")).to_contain_text("Edited mathematics")
                    row = page.locator("#setup-table tr").filter(has_text=subject["code"]).first
                    row.get_by_role("button", name="Edit subject", exact=True).click()
                    page.get_by_label("Academic year", exact=True).select_option("3")
                    page.get_by_role("button", name="Save subject", exact=True).click()
                    expect(page.locator("#form-error")).to_contain_text("linked teaching assignments")
                    page.get_by_role("button", name="Edit linked assignments", exact=True).click()
                    expect(page.get_by_role("tab", name="Assignments")).to_have_attribute("aria-selected", "true")
                    expect(page.locator("#table-search")).to_have_value(subject["code"])
                    page.get_by_role("button", name="Edit assignment", exact=True).first.click()
                    page.get_by_label("Lectures per week", exact=True).fill("2")
                    page.get_by_role("button", name="Save assignment", exact=True).click()
                    expect(page.locator("#modal")).not_to_be_visible()
                    updated = page.request.get(base + "/api/config").json()
                    assert next(o for o in updated["configuration"]["offerings"]
                                if o["subject_id"] == subject["id"])["lectures"] == 2
                    page.get_by_role("tab", name="Subjects").click()
                    page.locator("#setup-table tr").filter(has_text=subject["code"]).first.get_by_role(
                        "button", name="Delete subject", exact=True).click()
                    confirm = page.get_by_label("Also remove", exact=False)
                    expect(confirm).not_to_be_checked()
                    page.locator("#modal").get_by_role("button", name="Delete subject", exact=True).click()
                    expect(page.locator("#modal")).to_be_visible()
                    assert page.request.get(base + "/api/config").json() == updated
                    confirm.check()
                    page.screenshot(path=str(ARTIFACTS / "subject-delete-confirmation.png"), full_page=True)
                    page.locator("#modal").get_by_role("button", name="Delete subject", exact=True).click()
                    expect(page.locator("#modal")).not_to_be_visible()
                    page.reload()
                    after = page.request.get(base + "/api/config").json()["configuration"]
                    assert all(s["id"] != subject["id"] for s in after["subjects"])
                    assert after["offerings"] == [o for o in updated["configuration"]["offerings"]
                                                  if o["subject_id"] != subject["id"]]
                    assert page.request.get(base + f"/api/generations/{saved_id}").json() == saved
                    page.set_viewport_size({"width": 390, "height": 844})
                    page.goto(base + "/#subjects")
                    expect(page.get_by_role("heading", name="Academic setup", exact=True)).to_be_visible()
                    assert errors == [], errors
                    browser.close()
                    print("Browser smoke passed: strict-room generation, three-lecture continuity, "
                          "manual room choices, academic tabs, subject and assignment edits, "
                          "guarded linked-subject deletion, reload persistence, snapshot preservation, "
                          "mobile rendering; no JavaScript errors.")
            finally:
                server.terminate()
                server.wait(timeout=10)


if __name__ == "__main__":
    run()
