from flask import Flask, request, render_template, jsonify, send_file, url_for
import yt_dlp
import os
import uuid
import threading
import glob
import time
from urllib.parse import urlparse

app = Flask(__name__)

DOWNLOAD_DIR = "downloads"
MESSAGE_DIR = "messages"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(MESSAGE_DIR, exist_ok=True)

jobs = {}
ALLOWED_HOSTS = [
    "instagram.com", "www.instagram.com",
    "tiktok.com", "www.tiktok.com", "vm.tiktok.com",
    "youtube.com", "www.youtube.com", "youtu.be",
    "facebook.com", "www.facebook.com", "fb.watch"
]

def is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme not in ("http", "https"):
            return False
        host = parsed.netloc.lower()
        return any(host == allowed or host.endswith("." + allowed) for allowed in ALLOWED_HOSTS)
    except Exception:
        return False

def detect_platform(url: str) -> str:
    lower = url.lower()
    if "instagram.com" in lower:
        return "Instagram"
    if "tiktok.com" in lower:
        return "TikTok"
    if "facebook.com" in lower or "fb.watch" in lower:
        return "Facebook"
    if "youtube.com" in lower or "youtu.be" in lower:
        return "YouTube"
    return "Destekleniyor"

def cleanup_old_files(max_age_seconds: int = 60 * 60 * 3):
    now = time.time()

    for path in glob.glob(os.path.join(DOWNLOAD_DIR, "*")):
        try:
            if os.path.isfile(path) and now - os.path.getmtime(path) > max_age_seconds:
                os.remove(path)
        except Exception:
            pass

    expired_job_ids = []
    for job_id, job in jobs.items():
        created_at = job.get("created_at", now)
        if now - created_at > max_age_seconds:
            expired_job_ids.append(job_id)

    for job_id in expired_job_ids:
        jobs.pop(job_id, None)

@app.route("/")
def home():
    cleanup_old_files()
    return render_template("index.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip()
        message = (request.form.get("message") or "").strip()

        if not name or not email or not message:
            return render_template(
                "contact.html",
                success=False,
                error="Lütfen tüm alanları doldurun."
            )

        message_id = str(uuid.uuid4())
        payload = {
            "id": message_id,
            "name": name,
            "email": email,
            "message": message,
            "created_at": int(time.time())
        }
        with open(os.path.join(MESSAGE_DIR, f"{message_id}.json"), "w", encoding="utf-8") as f:
            import json
            json.dump(payload, f, ensure_ascii=False, indent=2)

        return render_template(
            "contact.html",
            success=True,
            error=None
        )

    return render_template("contact.html", success=False, error=None)

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()

    if not url:
        return jsonify({"success": False, "error": "Link boş olamaz."}), 400

    if not is_valid_url(url):
        return jsonify({
            "success": False,
            "error": "Desteklenen bir Instagram, TikTok, YouTube veya Facebook linki gir."
        }), 400

    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        return jsonify({
            "success": True,
            "title": info.get("title") or "Video hazır",
            "thumbnail": info.get("thumbnail") or "",
            "duration": info.get("duration"),
            "platform": detect_platform(url),
            "uploader": info.get("uploader") or "",
            "webpage_url": info.get("webpage_url") or url
        })
    except Exception:
        return jsonify({
            "success": False,
            "error": "Önizleme alınamadı. Linki kontrol edip tekrar dene."
        }), 500

def download_worker(job_id: str, url: str):
    output_template = os.path.join(DOWNLOAD_DIR, f"{job_id}.%(ext)s")

    jobs[job_id] = {
        "status": "starting",
        "percent": 1,
        "file_path": None,
        "error": None,
        "created_at": time.time()
    }

    def progress_hook(d):
        job = jobs.get(job_id)
        if not job:
            return

        status = d.get("status")

        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)

            if total and total > 0:
                percent = int(downloaded * 100 / total)
                job["percent"] = min(max(percent, 1), 95)
            else:
                job["percent"] = min(job.get("percent", 1) + 2, 90)

            job["status"] = "downloading"

        elif status == "finished":
            job["status"] = "processing"
            job["percent"] = 97

    try:
        ydl_opts = {
            "format": "bv*+ba/b",
            "outtmpl": output_template,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "merge_output_format": "mp4",
            "progress_hooks": [progress_hook],
            "retries": 3
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(url, download=True)

        matches = glob.glob(os.path.join(DOWNLOAD_DIR, f"{job_id}.*"))
        matches = [m for m in matches if os.path.isfile(m)]

        if not matches:
            raise FileNotFoundError("Dosya bulunamadı.")

        # Prefer mp4 if merged output exists
        matches.sort(key=lambda p: (0 if p.lower().endswith(".mp4") else 1, p))
        file_path = matches[0]

        jobs[job_id]["status"] = "done"
        jobs[job_id]["percent"] = 100
        jobs[job_id]["file_path"] = file_path

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = "Kaydetme sırasında hata oluştu. Farklı bir link ile tekrar dene."

@app.route("/download", methods=["POST"])
def download():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()

    if not url:
        return jsonify({"success": False, "error": "Link boş olamaz."}), 400

    if not is_valid_url(url):
        return jsonify({
            "success": False,
            "error": "Desteklenen bir Instagram, TikTok, YouTube veya Facebook linki gir."
        }), 400

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "queued",
        "percent": 0,
        "file_path": None,
        "error": None,
        "created_at": time.time()
    }

    thread = threading.Thread(target=download_worker, args=(job_id, url), daemon=True)
    thread.start()

    return jsonify({
        "success": True,
        "job_id": job_id,
        "status_url": url_for("status", job_id=job_id),
        "file_url": url_for("get_file", job_id=job_id)
    })

@app.route("/status/<job_id>")
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({
            "success": False,
            "error": "İş bulunamadı."
        }), 404

    return jsonify({
        "success": True,
        "status": job.get("status"),
        "percent": job.get("percent", 0),
        "error": job.get("error")
    })

@app.route("/file/<job_id>")
def get_file(job_id):
    job = jobs.get(job_id)
    if not job or job.get("status") != "done":
        return "Dosya hazır değil.", 404

    file_path = job.get("file_path")
    if not file_path or not os.path.exists(file_path):
        return "Dosya bulunamadı.", 404

    ext = os.path.splitext(file_path)[1] or ".mp4"
    download_name = f"ishmp4-save{ext}"

    return send_file(
        file_path,
        as_attachment=True,
        download_name=download_name
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
