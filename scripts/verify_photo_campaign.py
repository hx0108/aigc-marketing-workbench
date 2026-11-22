"""Run an isolated, provider-free workbench creation and download the resulting sample ZIP."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import sys
import time
from urllib.parse import quote
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photos", nargs="+", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--selling-point", help="A confirmed, verifiable detail of the supplied concept product.")
    parser.add_argument("--wear-first", action="store_true", help="The first photo is a single in-ear bud from the outside.")
    parser.add_argument("--seconds", type=int, default=15)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    scratch = ROOT / "runtime" / ("campaign-acceptance-" + uuid.uuid4().hex)
    media = scratch / "media"
    media.mkdir(parents=True)
    os.environ.update(DATABASE_URL="sqlite:///" + (scratch / "qa.db").as_posix(), AIGC_STORAGE_ROOT=str(media),
                      TEMP=str(scratch), TMP=str(scratch))
    for name in ("AIGC_PIPELINE_CONFIG","AIGC_RULESET_FILE","AIGC_RELEASE_CONTENT_PRODUCER","AIGC_RELEASE_CONTENT_PROPAGATOR"):
        os.environ.pop(name, None)
    sys.path[:0] = [str(ROOT / "apps/api"), str(ROOT / "apps/worker")]
    from fastapi.testclient import TestClient
    from app import db
    from app.execution import ExternalCall
    from app.ledger import CallReservation
    from app.job_repository import JobRepository
    from app.main import app
    from marketing_worker.runner import run_once
    from marketing_worker.media import probe
    db.initialize()

    with TestClient(app) as http:
        def post(path, payload, headers=None):
            response = http.post("/api/v1/" + path, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()

        signup = post("accounts", {"username":"campaign-qa", "password":secrets.token_urlsafe(24)})
        http.headers["X-CSRF-Token"] = signup["csrf_token"]
        sku = post("skus", {"name":args.name, "merchant_sku":"CONCEPT-AUDIO", "single_spec_confirmed":True})
        photos = []
        for image in args.photos:
            upload = http.post(f"/api/v1/skus/{sku['id']}/sources", content=image.read_bytes(),
                               headers={"X-Rights-Confirmed":"true", "X-Filename":quote(image.name)})
            upload.raise_for_status()
            photos.append(upload.json()["id"])
        facts = {"name":args.name}
        if args.selling_point:
            facts["核心卖点"] = args.selling_point
        profile = post(f"skus/{sku['id']}/profiles", {"source_ids":photos, "facts":facts})
        post(f"profiles/{profile['id']}/confirm", {})
        creation = post("creation-requests", {"profile_id":profile["id"], "creative_mode":"photo_campaign",
                        "platforms":["douyin","xiaohongshu"], "duration_seconds":args.seconds,
                        "wear_source_id": photos[0] if args.wear_first else None})
        assert creation["status"] == "ready" and creation["quote"]["cost_upper_bound"] == 0, creation["blockers"]
        key = {"Idempotency-Key":uuid.uuid4().hex}
        run_path = f"creation-requests/{creation['id']}/runs"
        work = post(run_path, {"authorized":True}, key)
        assert post(run_path, {"authorized":True}, key)["task_id"] == work["task_id"]
        print("render started", work["task_id"], flush=True)
        started = time.monotonic()
        assert run_once(JobRepository(), "photo-campaign-qa")
        elapsed = time.monotonic() - started
        task = http.get("/api/v1/tasks/" + work["task_id"]).json()
        details = http.get("/api/v1/works/" + work["work_id"]).json()
        if task["execution_state"] != "succeeded":
            with db.Session() as session:
                from app.execution import Task
                outcome = session.get(Task, work["task_id"]).payload.get("_outcome")
                print("task outcome", outcome, flush=True)
                if "result" in details:
                    print("branches", {p:{k:(b["state"],b.get("code")) for k,b in branches.items()}
                                       for p,branches in details["result"]["branches"].items()})
            raise RuntimeError(f"campaign task {task['execution_state']}: {task.get('error')}")
        assert details["status"] == "awaiting_review" and len(details["assets"]) == 11
        assert all(a["review"] == "pending" for a in details["assets"])
        with db.Session() as session:
            assert session.query(ExternalCall).count() == session.query(CallReservation).count() == 0
        payload = {"work_id":work["work_id"], "selection":"full_suite", "mode":"sample"}
        package = post("export-packages", payload)
        download = http.get(f"/api/v1/exports/{package['id']}/download")
        download.raise_for_status()
        response = http.post("/api/v1/export-packages", json={**payload, "mode":"release"})
        assert response.status_code == 409, response.status_code
        report = {"work_id":work["work_id"], "task_id":work["task_id"], "duration_seconds":args.seconds,
                  "render_seconds":round(elapsed, 2), "asset_count":11, "external_calls":0, "reservations":0,
                  "review":"pending", "release_gate":response.json()["detail"]["code"], "files":[]}
        with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["mode"] == "sample" and not manifest["missing_items"]
            assert len(manifest["assets"]) == 11
            for asset in manifest["assets"]:
                item = next(row for row in details["assets"] if row["id"] == asset["id"])
                data = archive.read(asset["id"] + item["extension"])
                assert hashlib.sha256(data).hexdigest() == asset["sha256"]
                if asset["kind"] not in {"marketing_poster","video","copy"}:
                    continue
                platform = {"douyin":"抖音","xiaohongshu":"小红书"}[asset["slot"]]
                dest = output / (platform + {"marketing_poster":"-运动海报.png","video":"-广告片.mp4","copy":"-发布文案.txt"}[asset["kind"]])
                if asset["kind"] == "copy":
                    copy = json.loads(data)
                    dest.write_text(copy["title"] + "\n\n" + copy["body"] + "\n", encoding="utf-8")
                else:
                    dest.write_bytes(data)
                if asset["kind"] == "video":
                    meta = probe(dest)
                    video = next(s for s in meta["streams"] if s["codec_type"] == "video")
                    sound = next(s for s in meta["streams"] if s["codec_type"] == "audio")
                    assert (video["width"],video["height"],video["codec_name"],video["pix_fmt"]) == (1080,1920,"h264","yuv420p")
                    assert int(video["nb_frames"]) == args.seconds * 25 and sound["codec_name"] == "aac"
                report["files"].append({"name":dest.name, "sha256":hashlib.sha256(dest.read_bytes()).hexdigest()})
        (scratch / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({**report, "evidence":str(scratch)}, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
