"""
modules/aplus_studio.py
=======================
✨ A+ Content Studio.

One simple flow: upload the product package/spec file + the product's own
reference image(s) → the studio (1) asks Claude to architect a compact Premium A+
plan (4-5 modules, 1-2 images each) AND a set of 4-5 listing "feature" images,
then (2) renders every image with gpt-image-2 using your uploaded photos as the
identity source, so the generated images look like the ACTUAL product.

Outputs are split into two download sections — **A+ images** and **Feature
images** — and the full written brief/strategy lives in its own tab.

Keys: Anthropic (planning) + OpenAI (images), both from Settings.
"""

from __future__ import annotations
import io
import json
import zipfile
import streamlit as st

from core import db, assistant, imagegen
from core.components import page_header
from core.styles import section_label, badge, alert


# ---------------------------------------------------------------------------
# Planner system prompt — returns STRICT JSON we can drive generation from.
# ---------------------------------------------------------------------------
APLUS_JSON_SYSTEM = r"""You are a senior Amazon A+ Content Architect and Creative Director for an Amazon.ae Porodo seller. Analyze the product brief/spec and produce a Premium A+ package that follows the EXACT 5-module blueprint below. The STRUCTURE is fixed for every product — only the CONTENT adapts to the product you are given. Return STRICT JSON ONLY (no markdown, no commentary, no code fences).

THE FIXED 5-MODULE BLUEPRINT (always these five, in this order):
- Module 1 — "Simple Banner" (Hero Hook): a wide 3/4 lifestyle hero showing the product in its real, attractive use-environment; visually emphasise its single most marketable quality (e.g. compact, sleek, premium). Copy fields: "Title Text (max 300)".
- Module 2 — "Premium Single Image" (Core Feature): showcase the product's #1 most compelling unique selling feature. Copy fields: "Headline 1 (max 40)", "Headline 2 (max 80)", "Body Text (max 500)".
- Module 3 — "Premium Dual Images" (Secondary Features): TWO closely-related secondary features, one per block, side by side. images: exactly 2. Copy fields: "Block 1 Headline (max 50)", "Block 1 Body (max 300)", "Block 2 Headline (max 50)", "Block 2 Body (max 300)".
- Module 4 — "Premium Single Image" (Accessories & Specs): an overhead flat-lay / unboxing arrangement of the product WITH every included accessory, communicating value, plus the key hard specs (power/motor, exact dimensions, capacity). Copy fields: "Headline 1 (max 40)", "Headline 2 (max 80)", "Body Text (max 500)".
- Module 5 — "Simple Banner" (Lifestyle Wrap-up): a warm, emotional lifestyle close with a happy person/family enjoying the benefit while the product sits naturally in the scene. Copy fields: "Title Text (max 300)".
Total A+ module images for the 5-module default = 6 (M1:1, M2:1, M3:2, M4:1, M5:1).

MODULE COUNT = exactly {NMOD} modules:
- If {NMOD} = 5, use the blueprint above exactly.
- If {NMOD} < 5, drop the least essential MIDDLE module(s) (keep M1 hero, the core-feature single, and the emotional close).
- If {NMOD} > 5, add extra "Premium Single Image" modules for the next strongest features (one feature each).
- ALWAYS: Module 1 = Simple Banner hero (wide 3/4 lifestyle); the LAST module = Simple Banner emotional lifestyle close; use AT MOST ONE "Premium Dual Images" (2-image) module total; every other middle module = single-image. Keep total module images ≤ 7.

CONTENT INTELLIGENCE (be smart, not generic):
- First silently rank the product's features by buyer appeal. Module 2 must use the SINGLE strongest, most differentiating feature. Module 3's two blocks must use the next two strongest, genuinely distinct secondary features. Never fill modules with weak/obvious points.
- IMAGE↔COPY SYNC IS MANDATORY: every image must VISUALLY PROVE the exact claim its copy makes. If copy says "compact" the scene must clearly read as compact (small counter, beside a common-size object for scale, or held in a hand); "dual-mode / two ways" → show both modes in one frame; "touch display / controls" → a finger on the glowing panel, macro; "food-grade / safe interior" → the open interior with the relevant accessory; "950W / 425x514x570mm" → the flat-lay with all accessories and a sense of scale. The depicted action must match the words — never a decorative shot that ignores the claim.

unique_feature_images: produce ONLY 1 to {NFEAT} listing-gallery image(s) that are NOT already covered by an A+ module — chiefly ONE clean studio HERO of the product on a pure white seamless background, straight-on, filling the frame, NO text overlay (this becomes the gallery main image). Do NOT duplicate any A+ module scene; the other gallery images are produced by reusing the A+ feature images.

JSON shape:
{
 "analysis": {"product_name":"","category":"","usps":["..."],"features":["..."],"specs":["..."],"contents":["..."],"target":"","tone":"","narrative":""},
 "modules": [
   {"n":1,"type":"Simple Banner","purpose":"one sentence",
    "designer_note":"crop guidance + where text overlay sits",
    "copy":{"Title Text (max 300)":"English","Arabic (العربية)":"العربية"},
    "images":[{"label":"hero","filename":"module1_hero.png","prompt":"FULL prompt"}]}
 ],
 "unique_feature_images":[{"n":1,"label":"Hero on white","filename":"feature_hero.png","prompt":"FULL prompt"}]
}

COPY RULES: write all copy yourself; never blank/placeholder; lead with the customer benefit; active voice; respect each field's character limit. Bilingual — for EACH module give the English copy fields then an "Arabic (العربية)" value (natural professional Arabic, not literal MT) — unless the dialect note says English only.

IMAGE PROMPT RULES (every "prompt" string: min 180 words, flowing paragraphs, in this exact order):
1) Exact camera angle first (each image a DIFFERENT angle — M1 wide 3/4 lifestyle; M2 matched to the core feature; M3 block1 macro/close-up, block2 interior/open view; M4 top-down overhead flat-lay; M5 eye-level lifestyle with people; hero feature = straight-on white studio). 2) Full scene/environment (surface, background, props, palette, atmosphere). 3) Lighting (source, direction, hard/soft, Kelvin). 4) Include VERBATIM: "Use the uploaded product reference image as the sole identity source. Faithfully reproduce the product's overall silhouette, color scheme, surface finish, material texture, branding marks, labels, logos, and all distinguishing design details. You are not cloning the reference photograph — you are placing the same product into the new scene and camera angle described above. You have full freedom to rotate, reposition, and reframe the product to match the specified angle. You must NOT add, remove, restyle, recolor, or alter any physical detail — every control, dial, button, port, vent, hopper, seam, proportion, logo and marking stays EXACTLY as in the reference; only the camera angle and the surrounding scene change. All text, logos, and labels that are naturally visible from this new angle must be rendered sharp, accurate, and fully legible." 5) Feature storytelling — explicitly stage the feature named in this module's copy so the image PROVES it. 6) One short in-image overlay phrase that names the feature (English, plus the exact Arabic string beneath unless English-only), with position + treatment, never overlapping the product. 7) End VERBATIM with: "Photorealistic commercial product photography quality, ultra-sharp focus on the product, no illustration style, no graphic design style, no cartoon rendering. Square format, 2000x2000 pixels, 1:1 ratio."
(The white-background hero feature image has NO overlay — skip element 6 for it only.)

Output the JSON now."""


# ---------------------------------------------------------------------------
# File text extraction (PDF / TXT / CSV / XLSX)
# ---------------------------------------------------------------------------
def _extract_text(upload) -> str:
    name = upload.name.lower()
    try:
        if name.endswith(".txt"):
            return upload.getvalue().decode("utf-8", errors="ignore")
        if name.endswith(".csv"):
            import pandas as pd
            return pd.read_csv(upload).to_csv(index=False)
        if name.endswith(".xlsx"):
            import pandas as pd
            sheets = pd.read_excel(upload, sheet_name=None)
            return "\n\n".join(f"# Sheet: {s}\n{df.to_csv(index=False)}"
                               for s, df in sheets.items())
        if name.endswith(".pdf"):
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(upload.getvalue()))
            return "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception as e:
        return f"[Could not read {upload.name}: {e}]"
    return ""


def _parse_json(txt: str):
    """Pull the JSON object out of the model response."""
    if not txt:
        return None
    s, e = txt.find("{"), txt.rfind("}")
    if s < 0 or e <= s:
        return None
    try:
        return json.loads(txt[s:e + 1])
    except Exception:
        return None


def _plan(brief: str, dialect: str, n_modules: int, n_features: int):
    dial = {
        "Modern Standard Arabic (default)": "Use professional Modern Standard Arabic for all Arabic text.",
        "Gulf / Khaleeji dialect": "Use natural Gulf/Khaleeji Arabic for all Arabic text.",
        "English only": "ENGLISH ONLY — omit all Arabic translations and Arabic overlays.",
    }[dialect]
    system = (APLUS_JSON_SYSTEM.replace("{NFEAT}", str(max(1, min(2, n_features))))
              .replace("{NMOD}", str(n_modules)))
    user = (f"{dial}\nProduce exactly {n_modules} A+ modules following the blueprint priority, "
            f"and up to {max(1, min(2, n_features))} unique gallery feature image(s).\n\n"
            f"PRODUCT BRIEF / SPEC:\n{brief}")
    txt, status = assistant.complete(system, user, max_tokens=14000)
    if status != "ok":
        return None, status
    data = _parse_json(txt)
    if not data:
        return None, "error: could not parse plan JSON"
    return data, "ok"


# Amazon A+ upload dimensions per module type (the crop target for the designer).
_UPLOAD_SIZE = {
    "Simple Banner": "1464×600 desktop · 600×450 mobile",
    "Premium Single Image": "800×600",
    "Premium Dual Images": "650×350 each",
    "feature": "1:1 square (≥1000px)",
}


def _all_image_specs(plan: dict) -> tuple[list, list]:
    """Return (aplus_specs, unique_feature_specs). Feature gallery is built later by
    reusing the A+ feature images + these unique ones."""
    aplus = []
    for m in plan.get("modules", []):
        mtype = m.get("type", "")
        for j, im in enumerate(m.get("images", []) or []):
            if not im.get("prompt"):
                continue
            aplus.append({
                "label": f"Module {m.get('n','?')} — {im.get('label','image')}",
                "filename": im.get("filename") or f"module{m.get('n','x')}_{j+1}.png",
                "prompt": im["prompt"], "module_type": mtype,
                "upload_size": _UPLOAD_SIZE.get(mtype, "")})
    feats = []
    for f in plan.get("unique_feature_images", []) or plan.get("feature_images", []):
        if not f.get("prompt"):
            continue
        feats.append({
            "label": f"Feature — {f.get('label','image')}",
            "filename": f.get("filename") or f"feature_{f.get('n','x')}.png",
            "prompt": f["prompt"], "module_type": "feature",
            "upload_size": _UPLOAD_SIZE["feature"]})
    return aplus, feats


def _is_banner(module_type: str) -> bool:
    return "banner" in (module_type or "").lower()


def _sizes_for(module_type: str) -> list:
    """Exact Amazon upload sizes for a module — matched by keyword so any planner
    wording ('Simple Banner', 'Premium Single Image with Text', etc.) still works."""
    t = (module_type or "").lower()
    if "banner" in t:
        return [("desktop", 1464, 600), ("mobile", 600, 450)]
    if "dual" in t:
        return [("desktop", 650, 350)]
    return [("desktop", 800, 600)]          # default = Premium Single Image


def _gen_size(module_type: str) -> str:
    """gpt-image-2 generation size best suited to the module's final crop."""
    return "1536x1024" if _is_banner(module_type) else "1024x1024"


def _cover(png_bytes: bytes, w: int, h: int) -> bytes:
    """Cover-crop the generated image to the target aspect, then resize to exactly
    w×h (the Amazon module size). Product stays centered; no distortion."""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        sw, sh = im.size
        tar, src = w / h, sw / sh
        if src > tar:                      # source too wide → crop sides
            nw = int(round(sh * tar))
            x = (sw - nw) // 2
            im = im.crop((x, 0, x + nw, sh))
        else:                              # source too tall → crop top/bottom
            nh = int(round(sw / tar))
            y = (sh - nh) // 2
            im = im.crop((0, y, sw, y + nh))
        im = im.resize((w, h), Image.LANCZOS)
        out = io.BytesIO()
        im.save(out, format="PNG")
        return out.getvalue()
    except Exception:
        return png_bytes


def _add_crops(specs: list) -> None:
    """Attach desktop/mobile Amazon-sized crops to each A+ module image."""
    for sp in specs:
        sp["crops"] = []
        if not sp.get("bytes"):
            continue
        stem = sp["filename"].rsplit(".", 1)[0]
        for name, w, h in _sizes_for(sp.get("module_type")):
            sp["crops"].append({"name": name, "w": w, "h": h,
                                "filename": f"{stem}_{name}_{w}x{h}.png",
                                "bytes": _cover(sp["bytes"], w, h)})


def _resize_square(png_bytes: bytes, target: int = 1600) -> bytes:
    """Resize a (square) A+ image to a clean square for the listing gallery."""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        w, h = im.size
        s = min(w, h)
        im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))
        im = im.resize((target, target), Image.LANCZOS)
        out = io.BytesIO()
        im.save(out, format="PNG")
        return out.getvalue()
    except Exception:
        return png_bytes


def _feature_gallery(run: dict) -> list:
    """Listing feature gallery = the freshly-generated unique image(s) (white-bg
    hero) + the A+ FEATURE images reused/resized (skip the lifestyle banners)."""
    gallery = [dict(s) for s in run.get("unique", []) if s.get("bytes")]
    for s in run.get("aplus", []):
        if _is_banner(s.get("module_type")) or not s.get("bytes"):
            continue
        g = dict(s)
        g["bytes"] = _resize_square(s["bytes"])
        g["label"] = "Feature (from " + s["label"].split(" — ")[0] + ")"
        g["filename"] = "feature_" + s["filename"]
        gallery.append(g)
    return gallery


def _zip(items: list) -> bytes:
    """items: [{filename, bytes}] → zip bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for it in items:
            if it.get("bytes"):
                z.writestr(it["filename"], it["bytes"])
    return buf.getvalue()


def _generate_set(specs: list, ref_images: list, prog, base: float, span: float,
                  workers: int = 4):
    """Generate all specs CONCURRENTLY (image calls are network-bound) → attach
    'bytes'. Each module is generated at the size best for its final crop."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    n = max(len(specs), 1)
    results = [None] * len(specs)

    def _work(idx, sp):
        gsize = _gen_size(sp.get("module_type", ""))
        data, status = imagegen.generate_image(sp["prompt"], ref_images, size=gsize)
        rec = dict(sp)
        rec["bytes"] = data if status == "ok" else None
        rec["status"] = status
        return idx, rec

    done = 0
    if specs:
        with ThreadPoolExecutor(max_workers=min(workers, len(specs))) as ex:
            futs = [ex.submit(_work, i, sp) for i, sp in enumerate(specs)]
            for fut in as_completed(futs):
                idx, rec = fut.result()
                results[idx] = rec
                done += 1
                if prog:
                    prog.progress(min(1.0, base + span * done / n))
    return results


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------
def render(nav=None) -> None:
    page_header("A+ Content Studio",
                "Upload the product file + its photos → get A+ images and Feature images",
                icon="✨")

    has_text = bool(db.get_setting("anthropic_api_key", ""))
    has_img = imagegen.has_image_key()
    b = []
    b.append(badge(f"Claude {assistant.model()}" if has_text else "Add Anthropic key in Settings",
                   "green" if has_text else "amber"))
    b.append(badge(f"Images {imagegen.image_model()}" if has_img else "Add OpenAI key in Settings",
                   "green" if has_img else "amber"))
    st.markdown(" ".join(b), unsafe_allow_html=True)

    tab_gen, tab_brief = st.tabs(["🎨 Generate", "📋 Brief / Strategy"])

    with tab_gen:
        st.markdown(section_label("1 · Upload product package + product photos"),
                    unsafe_allow_html=True)
        c = st.columns(2)
        with c[0]:
            files = st.file_uploader(
                "Product package / spec file (PDF, TXT, CSV, XLSX)",
                type=["pdf", "txt", "csv", "xlsx"], accept_multiple_files=True,
                key="aplus_files")
            brief_txt = st.text_area("…or paste a short brief (optional)", height=90,
                                     key="aplus_brief")
        with c[1]:
            ref_up = st.file_uploader(
                "Product reference image(s) — the studio matches the real item to these",
                type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True,
                key="aplus_ref_uploader")

        cc = st.columns(3)
        dialect = cc[0].selectbox("Language", ["Modern Standard Arabic (default)",
                                  "Gulf / Khaleeji dialect", "English only"])
        n_modules = cc[1].slider("A+ modules", 4, 7, 5,
                                 help="How many A+ content modules to build (5 = the standard "
                                      "Premium blueprint).")
        n_features = cc[2].slider("Feature images", 3, 6, 5,
                                  help="How many listing gallery images (white-bg hero + your "
                                       "A+ feature images resized).")
        st.caption("Blueprint priority is kept at any count: hero banner first, emotional banner "
                   "last, at most one 2-image module, the rest single-image.")

        # Accumulate reference images across uploads.
        store = st.session_state.setdefault("aplus_ref_store", {})
        for f in (ref_up or []):
            store[f"{f.name}:{f.size}"] = {"name": f.name, "bytes": f.getvalue()}
        if store:
            tcols = st.columns(min(max(len(store), 1), 6))
            for i, item in enumerate(store.values()):
                with tcols[i % len(tcols)]:
                    st.image(item["bytes"], caption=item["name"], width=95)
            if st.button("🗑 Clear photos"):
                store.clear()
                st.rerun()
        ref_images = [v["bytes"] for v in store.values()]
        ref_names = [v["name"] for v in store.values()]

        # Assemble brief text.
        parts = []
        if brief_txt.strip():
            parts.append("BRIEF:\n" + brief_txt.strip())
        for f in files or []:
            t = _extract_text(f)
            if t.strip():
                parts.append(f"FILE {f.name}:\n{t.strip()}")
        combined = "\n\n".join(parts)[:24000]

        ready = bool(combined.strip()) and bool(ref_images) and has_text and has_img
        sig = hash((combined, tuple(sorted(store.keys())), dialect, n_modules, n_features))

        if not has_text or not has_img:
            st.markdown(alert("Add both the Anthropic and OpenAI API keys in Settings → "
                              "AI & Amazon to use the studio.", kind="amber", icon="🔑"),
                        unsafe_allow_html=True)
        elif not combined.strip():
            st.markdown(alert("Upload a product package/spec file (or paste a brief) to begin.",
                              kind="amber", icon="⬆️"), unsafe_allow_html=True)
        elif not ref_images:
            st.markdown(alert("Upload the product's own photo(s) so the generated images match "
                              "the real item.", kind="amber", icon="🖼️"), unsafe_allow_html=True)

        run = st.session_state.get("aplus_run")

        cgo = st.columns([1, 2])
        regen = cgo[0].button("🔄 Regenerate", use_container_width=True, disabled=not ready)
        cgo[1].caption(f"Full run ≈ {6 + n_features} images · ~{((6 + n_features + 5)//6)*55}s · "
                       f"6 generated in parallel · each module cropped to desktop + mobile · "
                       f"uses OpenAI credits per run.")
        # Auto-run once per unique input set (no manual click needed), or on Regenerate.
        should_run = ready and (regen or not run or run.get("sig") != sig)

        if should_run:
            with st.spinner("① Architecting the A+ plan (Claude)…"):
                plan, status = _plan(combined, dialect, n_modules, n_features)
            if status != "ok" or not plan:
                st.markdown(alert(f"Planning failed — {status}", kind="coral", icon="⛔"),
                            unsafe_allow_html=True)
                return
            aplus_specs, feat_specs = _all_image_specs(plan)
            all_specs = aplus_specs + feat_specs
            total = len(all_specs)
            est = ((total + 5) // 6) * 55  # 6 in parallel, ~55s/wave (edit endpoint)
            st.caption(f"② Generating {len(aplus_specs)} A+ image(s) + {len(feat_specs)} unique "
                       f"gallery image(s) — ALL at once (6 in parallel), ~{est}s — with "
                       f"{imagegen.image_model()} using your {len(ref_images)} photo(s). The "
                       f"feature gallery then reuses the A+ images.")
            prog = st.progress(0.0)
            # One parallel batch for every image (A+ + unique) → fastest.
            all_done = _generate_set(all_specs, ref_images, prog, 0.0, 1.0, workers=6)
            aplus_done = all_done[:len(aplus_specs)]
            feat_done = all_done[len(aplus_specs):]
            _add_crops(aplus_done)         # desktop + mobile Amazon-sized crops
            prog.progress(1.0)
            st.session_state["aplus_run"] = {"sig": sig, "plan": plan, "n_features": n_features,
                                             "aplus": aplus_done, "unique": feat_done}
            run = st.session_state["aplus_run"]
            db.add_task(f"A+ content: {plan.get('analysis',{}).get('product_name','product')[:50]}",
                        "A+ + feature images generated in A+ Content Studio.",
                        module="A+ Content Studio", priority="medium")

        if not run:
            return

        # Retry only the images that failed (e.g. a dropped connection) — no full redo.
        failed = [s for s in run["aplus"] if not s.get("bytes")] + \
                 [s for s in run.get("unique", []) if not s.get("bytes")]
        if failed and ready:
            cwa = st.columns([2, 1])
            cwa[0].markdown(alert(f"{len(failed)} image(s) didn't generate (connection issue). "
                                  f"Retry just those — no need to redo the rest.",
                                  kind="amber", icon="🔁"), unsafe_allow_html=True)
            if cwa[1].button(f"🔁 Retry {len(failed)} failed", use_container_width=True):
                redo = _generate_set(failed, ref_images, st.progress(0.0), 0.0, 1.0)
                _add_crops(redo)
                byname = {r["filename"]: r for r in redo if r and r.get("bytes")}
                for lst in (run["aplus"], run.get("unique", [])):
                    for i, s in enumerate(lst):
                        if not s.get("bytes") and s.get("filename") in byname:
                            lst[i] = byname[s["filename"]]
                st.rerun()

        # ---- Results: two sections ----
        ok_a = [x for x in run["aplus"] if x.get("bytes")]
        feat_gallery = _feature_gallery(run)[:run.get("n_features", 5)]
        ok_f = [x for x in feat_gallery if x.get("bytes")]

        st.markdown("---")
        st.markdown(section_label(f"📦 A+ Module Images ({len(ok_a)} modules)"),
                    unsafe_allow_html=True)
        st.caption("Each module is delivered at its exact Amazon upload size — banners include "
                   "both desktop (1464×600) and mobile (600×450).")
        if ok_a:
            st.download_button("⬇ Download ALL A+ images (ZIP, desktop + mobile)",
                               _aplus_zip(run["aplus"]),
                               file_name="aplus_images.zip", mime="application/zip",
                               use_container_width=True, key="zip_aplus")
            _aplus_gallery(run["aplus"])
        else:
            st.info("No A+ images generated.")

        st.markdown(section_label(f"🖼️ Feature Images ({len(ok_f)})"), unsafe_allow_html=True)
        st.caption("Listing gallery: white-background hero (new) + your A+ feature images resized.")
        if ok_f:
            st.download_button("⬇ Download ALL Feature images (ZIP)", _zip(ok_f),
                               file_name="feature_images.zip", mime="application/zip",
                               use_container_width=True, key="zip_feat")
            _gallery(feat_gallery, "f")
        else:
            st.info("No feature images generated.")

    with tab_brief:
        run = st.session_state.get("aplus_run")
        if not run:
            st.caption("The written A+ brief (analysis, modules, copy, image prompts) will "
                       "appear here after you generate. It's kept out of the main view so you "
                       "only deal with the finished images.")
        else:
            _render_brief(run["plan"])


def _aplus_zip(specs: list) -> bytes:
    """ZIP of every module's Amazon-sized crops (desktop + mobile)."""
    items = []
    for sp in specs:
        crops = sp.get("crops") or []
        if crops:
            items += [{"filename": "aplus/" + c["filename"], "bytes": c["bytes"]} for c in crops]
        elif sp.get("bytes"):
            items.append({"filename": "aplus/" + sp["filename"], "bytes": sp["bytes"]})
    return _zip(items)


def _aplus_gallery(specs: list) -> None:
    cols = st.columns(3)
    for i, sp in enumerate(specs):
        with cols[i % 3]:
            crops = sp.get("crops") or []
            preview = crops[0]["bytes"] if crops else sp.get("bytes")
            if not preview:
                st.warning(f"{sp['label']}: {sp.get('status', 'failed')}")
                continue
            st.image(preview, caption=sp["label"], use_container_width=True)
            if crops:
                st.caption("📐 " + " · ".join(f"{c['name']} {c['w']}×{c['h']}" for c in crops))
                for c in crops:
                    st.download_button(f"⬇ {c['name']} {c['w']}×{c['h']}", c["bytes"],
                                       file_name=c["filename"], mime="image/png",
                                       key=f"dla_{i}_{c['name']}")
            else:
                st.download_button("⬇ download", sp["bytes"], file_name=sp["filename"],
                                   mime="image/png", key=f"dla_{i}")


def _gallery(specs: list, prefix: str) -> None:
    cols = st.columns(3)
    for i, sp in enumerate(specs):
        with cols[i % 3]:
            if sp.get("bytes"):
                st.image(sp["bytes"], caption=sp["label"], use_container_width=True)
                if sp.get("upload_size"):
                    st.caption(f"📐 Amazon crop: **{sp['upload_size']}**")
                st.download_button("⬇", sp["bytes"], file_name=sp["filename"],
                                   mime="image/png", key=f"dl_{prefix}_{i}")
            else:
                st.warning(f"{sp['label']}: {sp.get('status','failed')}")


def _render_brief(plan: dict) -> None:
    a = plan.get("analysis", {})
    st.markdown(section_label("Product analysis"), unsafe_allow_html=True)
    st.markdown(f"**{a.get('product_name','')}** — {a.get('category','')}  \n"
                f"*Tone:* {a.get('tone','')} · *Target:* {a.get('target','')}")
    if a.get("narrative"):
        st.caption(a["narrative"])
    for label, key in [("USPs", "usps"), ("Features", "features"), ("Specs", "specs"),
                       ("Contents", "contents")]:
        vals = a.get(key) or []
        if vals:
            st.markdown(f"**{label}:** " + ", ".join(str(v) for v in vals))

    st.markdown(section_label("Modules"), unsafe_allow_html=True)
    for m in plan.get("modules", []):
        with st.expander(f"Module {m.get('n','?')} — {m.get('type','')}  ·  "
                         f"{m.get('purpose','')}"):
            if m.get("designer_note"):
                st.caption("🎨 " + m["designer_note"])
            for fld, val in (m.get("copy") or {}).items():
                st.markdown(f"**{fld}:** {val}")
            for im in m.get("images", []) or []:
                with st.expander(f"gpt-image-2 prompt — {im.get('label','')}"):
                    st.code(im.get("prompt", ""), language="text")

    st.markdown(section_label("Unique feature image prompts"), unsafe_allow_html=True)
    for f in plan.get("unique_feature_images", []) or plan.get("feature_images", []):
        with st.expander(f"Feature — {f.get('label','')}"):
            st.code(f.get("prompt", ""), language="text")
