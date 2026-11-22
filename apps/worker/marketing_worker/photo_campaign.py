"""Produce channel-specific photo campaigns on the normal, fenced creation queue."""
import hashlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageOps
from app.photo_storyboard import shot_plan as _shot_plan

from .bridge import RenderBridge, local_render_font
from .persistence import StepStore
from .platform_style import poster_slot, scene_owners


class WearPhotoRequired(ValueError):
    code = "WEAR_PHOTO_CUTOUT_REQUIRED"


def _subject(photo, mask=None):
    from app.product_matte import extract_matte
    with Image.open(photo) as im:
        # Scale the image and its mask in the camera's coordinates before applying EXIF.
        original_size = im.size
        orientation = im.getexif().get(274, 1)
        im.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        if mask:
            with Image.open(mask) as source:
                if source.size != original_size:
                    raise ValueError("mask_size_mismatch")
                matte = source.resize(im.size, Image.Resampling.LANCZOS).convert("L")
        else:
            matte = extract_matte(im)
        if matte is None:
            return None
        subject = im.convert("RGBA")
        subject.putalpha(matte)
        subject.getexif()[274] = orientation
        subject = ImageOps.exif_transpose(subject)
        box = subject.getchannel("A").point(lambda value: 255 if value > 16 else 0).getbbox()
        if box is None:
            return None
        return subject.crop(box)


def _copy(request):
    facts = request["profile_snapshot"]["facts"]
    name = facts["name"]
    point = ""
    point_ref = None
    for key in ("核心卖点", "卖点", "selling_point", "specification"):
        value = facts.get(key)
        if isinstance(value, str) and 0 < len(value.strip()) <= 44 and value.strip() != name:
            point, point_ref = value.strip(), key
            break
    worn = bool(request.get("wear_source_id"))
    result = {}
    for platform in request["platforms"]:
        fast = platform == "douyin"
        if worn:
            opening = "戴上，开跑。" if fast else "晨跑的耳边风景"
            close = "下一圈，再听一首。" if fast else "把喜欢的歌，带出门。"
            body = (f"{name}。从跑道边的佩戴近景，看到耳机本身。把喜欢的歌带到下一圈。"
                    if fast else f"晨光落在跑道上。把{name}的佩戴侧面和外形细节放在一起，看清耳边的样子。")
        else:
            opening = "细节，放大看。" if fast else "近看那些小细节"
            close = "把细节看清。" if fast else "留住这一面。"
            body = (f"{name}，从整体轮廓到近处细节，换个距离看。" if fast else
                    f"把{name}的全貌和细节放在一起，选购时可以慢慢看。")
        poster_title = request.get("brief", "").strip() or opening
        if point:
            body = f"{body.rstrip('。')}。{point.rstrip('。')}。"
        refs = list(facts) if request.get("brief") else ["name"] + ([point_ref] if point_ref else [])
        slot = poster_slot(platform, request["platforms"])
        shots = []
        for view, duration in _shot_plan(request, platform):
            caption = opening if view == "scene" else close if view == "end" else ""
            caption_refs = ["name"]
            # Keep a long specification in the post and poster when the shot is too short to read it.
            if view == "packshot" and point_ref and len(point) <= int(duration * 6):
                caption = point
                caption_refs = [point_ref]
            shots.append({"asset_slot":slot if view == "scene" else "white", "duration":duration,
                          "fact_refs":caption_refs, "visual_description":{
                              "scene":"运动佩戴近景" if worn else "商品场景全景",
                              "packshot":"商品外形特写", "end":"商品定格与广告收尾",
                          }.get(view, "从另一张同款照片展示商品"), **({"narration":caption} if caption else {})})
        result[platform] = {
            "title":opening, "body":body, "poster_title":poster_title, "selling_points":[name, point] if point else [name],
            "narration":"".join(shot.get("narration","") for shot in shots), "shots":shots, "fact_refs":refs,
        }
    return result


def _keep_asset(asset, root, scope):
    source = Path(asset["path"])
    digest = asset["sha256"]
    if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
        raise ValueError("asset_hash_mismatch")
    filename = hashlib.sha256((scope + digest).encode()).hexdigest() + source.suffix
    target = root / filename
    try:
        if os.name == "nt":
            os.rename(source, target)  # Windows rename fails if another attempt already placed the file.
        else:
            os.link(source, target)
    except FileExistsError:
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError("asset_hash_mismatch") from None
    kept = {**asset, "path":str(target)}
    if "release" in asset:
        kept["release"] = _keep_asset(asset["release"], root, scope + "/release")
    return kept


class CampaignRun:
    def __init__(self, repository, job, root, folder, paths, subject):
        self.job = job
        self.task = job["id"]
        self.request = job["payload"]["request"]
        self.store = StepStore(repository.sessions, job["workspace"], job["fencing_token"])
        self.renderer = RenderBridge(root, local_render_font(), output_root=folder)
        self.photos = dict(zip([p["source_id"] for p in self.request["photo_sources"]], paths, strict=True))
        self.main = self.request.get("wear_source_id") or next(iter(self.photos))
        self.subject = subject

    def subject_for(self, photo):
        if photo == self.photos[self.main]:
            subject = self.subject
        else:
            subject = _subject(photo)
        if subject is None:
            raise ValueError("campaign_product_cutout_required")
        return subject

    def step(self, key, produce):
        if self.store.canceled(self.task):
            raise ValueError("canceled")
        prior = self.store.read(self.task, key)
        if prior and prior["state"] == "succeeded":
            return prior["result"]
        self.store.write(self.task, key, "rendering", None)
        try:
            value = produce()
            if "path" in value:
                value = _keep_asset(value, self.renderer.root, self.task + ":" + key)
        except Exception as error:
            self.store.write(self.task, key, "failed", {"code":getattr(error, "code", type(error).__name__)})
            raise
        self.store.write(self.task, key, "succeeded", value)
        return value

    def motion(self, media, view, picture, platform, index, duration, output, worn, full_bleed):
        if view in {"packshot", "end"}:
            subject = self.subject
        elif view in self.photos:
            subject = self.subject_for(picture)
        else:
            subject = None
        return media.clip(picture, platform, index, duration, output, worn=worn,
                          full_bleed=full_bleed, subject=subject, closing=view == "end")

    def execute(self):
        from . import campaign_media as media
        request = self.request
        copies = self.step("copy", lambda: _copy(request))
        paths = [self.photos[self.main], *(p for i,p in self.photos.items() if i != self.main)]
        output = self.renderer.path
        images = {"white":self.step("image/white", lambda: media.packshot(
            paths, self.subject, output("white", ".png")))}
        worn = bool(request.get("wear_source_id"))
        platforms = request["platforms"]
        for slot, owner in scene_owners(platforms).items():
            # Single-platform deliveries include a second, product-focused scene.
            show_wear = worn and slot == poster_slot(owner, platforms)
            scene_photos = paths if slot == poster_slot(owner, platforms) else list(reversed(paths))
            images[slot] = self.step("image/"+slot, lambda: media.scene(
                scene_photos, self.subject_for(scene_photos[0]),
                owner, output(slot, ".png"), worn=show_wear))
        branches, settings = {}, {}
        for platform in platforms:
            content = copies[platform]
            slot = poster_slot(platform, platforms)
            name = request["profile_snapshot"]["facts"]["name"]
            display_name = name if len(name) <= 36 else ""
            settings[platform] = {"creative_mode":"photo_campaign", "product_name":display_name,
                                  "poster_scene":slot, "poster_layout":"classic" if platform=="douyin" else "product_top",
                                  "soundtrack":"original_score", "shot_photo_sources":{}, "wearing_campaign":worn}
            branches[platform] = {}
            try:
                poster = self.step(platform+"/poster", lambda: self.renderer.poster({
                    "images":images, "image_slot":slot, "copy":content, "campaign_platform":platform,
                }, platform+"/poster"))
                branches[platform]["poster"] = {"state":"awaiting_review", "result":poster}
            except Exception as error:
                if getattr(error, "code", "") == "paused" or self.store.canceled(self.task):
                    raise
                branches[platform]["poster"] = {"state":"failed", "code":getattr(error, "code", type(error).__name__)}
            clips = []
            try:
                for index, (view, duration) in enumerate(_shot_plan(request, platform)):
                    shot_worn = view == "scene" and worn
                    if view == "scene":
                        picture = self.renderer.input_path(images[slot])
                    elif view in {"packshot", "end"}:
                        picture = self.renderer.input_path(images["white"])
                    else:
                        picture = self.photos[view]
                        settings[platform]["shot_photo_sources"][str(index)] = view
                    key = f"{platform}/dynamic/{index}"
                    full_bleed = view in {"packshot", "end"} or (view == "scene" and images[slot].get("scene_kind") == "studio")
                    clip = self.step(key, lambda: self.motion(media, view, picture, platform, index, duration,
                                                              output(key, ".mp4"), shot_worn, full_bleed))
                    clips.append(clip)
                voice = self.step(platform+"/voice", lambda: media.score(
                    platform, request["duration_seconds"], output(platform+"/score", ".wav")))
                video = self.step(platform+"/video", lambda: self.renderer.video({
                    "clips":clips, "voice":voice, "duration":request["duration_seconds"],
                    "copy":content, "campaign_platform":platform, "product_name":display_name, "wearing_campaign":worn,
                }, platform+"/video"))
                branches[platform]["video"] = {"state":"awaiting_review", "result":video}
            except Exception as error:
                if getattr(error, "code", "") == "paused" or self.store.canceled(self.task):
                    raise
                branches[platform]["video"] = {"state":"failed", "code":getattr(error, "code", type(error).__name__)}
        return {"images":images, "platforms":branches, "copy":copies, "render_settings":settings}


def create_campaign(repository, job):
    from app.photo_campaign import verify_campaign_job
    from app.sources import ROOT
    from .business import persist_result
    request = job["payload"]["request"]
    selected = request.get("wear_source_id") or request["photo_sources"][0]["source_id"]
    with repository.sessions() as session:
        paths = verify_campaign_job(session, job)
        manual_mask = _reviewed_mask(session, job, selected, ROOT)
    main = next(path for ref,path in zip(request["photo_sources"], paths, strict=True)
                if ref["source_id"] == selected)
    subject = _subject(main, manual_mask)
    if request.get("wear_source_id") and subject is None:
        raise WearPhotoRequired()
    if subject is None:
        raise ValueError("campaign_product_cutout_required")
    with TemporaryDirectory(dir=ROOT, prefix="campaign-") as folder:
        run = CampaignRun(repository, job, ROOT, folder, paths, subject)
        result = run.execute()
        # Recheck rights and frozen input hashes before committing a result version.
        with repository.sessions() as session:
            verify_campaign_job(session, job)
            _reviewed_mask(session, job, selected, ROOT)
        return persist_result(repository.sessions, job, result, ROOT)


def _reviewed_mask(session, job, selected, root):
    from app.db import Record
    request = job["payload"]["request"]
    selection = request["profile_snapshot"].get("source_selection", {})
    if selection.get("product", {}).get("source_id") != selected or not selection.get("mask"):
        return None
    binding = selection["mask"]
    record = session.get(Record, binding["source_id"])
    if (not record or record.workspace != job["workspace"] or record.kind != "source"
        or record.data.get("sku_id") != request["sku_id"] or record.data.get("deleting")
        or record.data.get("rights_confirmed") is not True or record.data.get("sha256") != binding["sha256"]):
        raise ValueError("source_scope_invalid")
    path = (root / record.data["object_key"]).resolve()
    if not path.is_relative_to(root) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != binding["sha256"]:
        raise ValueError("source_hash_mismatch")
    if record.data.get("derived_from_source_id"):
        return None  # Recompute automatic masks under the current extraction rules.
    return path
