import io
import json
import logging
import os
import re
import tempfile
from datetime import datetime as _datetime
from sarvamai import SarvamAI
import local_store

logger = logging.getLogger(__name__)

SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY", "")

AUDIO_DEBUG_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', 'attached_assets', 'audio_debug'
)

AUDIO_MIME_TYPES = {
    "audio/amr", "audio/mpeg", "audio/mp3", "audio/ogg",
    "audio/wav", "audio/mp4", "audio/aac", "audio/webm",
    "audio/x-m4a", "audio/x-wav", "audio/3gpp",
    "application/vnd.microsoft.card.audio",
}
VIDEO_MIME_TYPES = {
    "video/mp4", "video/mpeg", "video/webm", "video/quicktime",
    "video/x-msvideo", "video/3gpp", "video/x-matroska",
    "application/vnd.microsoft.card.video",
}

AUDIO_EXTENSIONS = {".amr", ".mp3", ".ogg", ".wav", ".m4a", ".aac", ".weba", ".3gp"}
VIDEO_EXTENSIONS = {".mp4", ".mpeg", ".webm", ".mov", ".avi", ".mkv", ".3gp"}


class AudioProcessor:
    def _save_debug_bytes(self, filename: str, data: bytes):
        try:
            os.makedirs(AUDIO_DEBUG_DIR, exist_ok=True)
            path = os.path.join(AUDIO_DEBUG_DIR, filename)
            with open(path, "wb") as f:
                f.write(data)
            logger.info(f"[AudioDebug] Saved {len(data)} bytes → {path}")
        except Exception as e:
            logger.warning(f"[AudioDebug] Could not save {filename}: {e}")

    def _save_debug_text(self, filename: str, text: str):
        try:
            os.makedirs(AUDIO_DEBUG_DIR, exist_ok=True)
            path = os.path.join(AUDIO_DEBUG_DIR, filename)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            logger.info(f"[AudioDebug] Saved text ({len(text)} chars) → {path}")
        except Exception as e:
            logger.warning(f"[AudioDebug] Could not save {filename}: {e}")

    def is_audio_attachment(self, att: dict) -> bool:
        content_type = (att.get("content_type") or att.get("contentType") or "").lower().split(";")[0].strip()
        name = (att.get("name") or "").lower()
        if content_type in AUDIO_MIME_TYPES:
            return True
        if any(name.endswith(ext) for ext in AUDIO_EXTENSIONS):
            return True
        if "voicenote" in name.replace(" ", "").replace("-", "").replace("_", ""):
            return True
        return False

    def is_video_attachment(self, att: dict) -> bool:
        content_type = (att.get("content_type") or att.get("contentType") or "").lower().split(";")[0].strip()
        name = (att.get("name") or "").lower()
        if content_type in VIDEO_MIME_TYPES:
            return True
        if any(name.endswith(ext) for ext in VIDEO_EXTENSIONS):
            return True
        return False

    def detect_audio_format(self, data: bytes) -> tuple:
        if not data:
            return ("wav", "audio/wav")
        if data[:5] == b'#!AMR':
            logger.info("[Audio] Detected format from magic bytes: amr (audio/amr)")
            return ("amr", "audio/amr")
        if data[:4] == b'OggS':
            logger.info("[Audio] Detected format from magic bytes: ogg (audio/ogg)")
            return ("ogg", "audio/ogg")
        if data[:4] == b'RIFF':
            logger.info("[Audio] Detected format from magic bytes: wav (audio/wav)")
            return ("wav", "audio/wav")
        if len(data) > 8 and data[4:8] == b'ftyp':
            logger.info("[Audio] Detected format from magic bytes: m4a (audio/mp4)")
            return ("m4a", "audio/mp4")
        if data[:4] == b'\x1a\x45\xdf\xa3':
            logger.info("[Audio] Detected format from magic bytes: webm (audio/webm)")
            return ("webm", "audio/webm")
        if data[:3] == b'ID3':
            logger.info("[Audio] Detected format from magic bytes: mp3 (audio/mpeg)")
            return ("mp3", "audio/mpeg")
        if len(data) > 1 and data[0] == 0xff and (data[1] & 0xe0) == 0xe0:
            logger.info("[Audio] Detected format from magic bytes: mp3 (audio/mpeg)")
            return ("mp3", "audio/mpeg")
        logger.info("[Audio] Format not detected from magic bytes, defaulting to ogg")
        return ("ogg", "audio/ogg")

    def video_to_mp3(self, video_bytes: bytes, filename: str = "video.mp4") -> bytes:
        try:
            from pydub import AudioSegment
            video_io = io.BytesIO(video_bytes)
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "mp4"
            audio = AudioSegment.from_file(video_io, format=ext)
            mp3_io = io.BytesIO()
            audio.export(mp3_io, format="mp3")
            mp3_io.seek(0)
            logger.info(f"[Audio] Converted video {filename} to MP3 ({len(video_bytes)} -> {len(mp3_io.getvalue())} bytes)")
            return mp3_io.getvalue()
        except Exception as e:
            logger.error(f"[Audio] video_to_mp3 failed for {filename}: {e}")
            raise

    def _run_batch_job(self, audio_bytes: bytes, ext: str, debug_key: str) -> str:
        tmp_dir = tempfile.mkdtemp(prefix="sarvam_")
        try:
            safe_name = "audio"
            tmp_audio_path = os.path.join(tmp_dir, f"{safe_name}.{ext}")
            tmp_output_dir = os.path.join(tmp_dir, "output")
            os.makedirs(tmp_output_dir, exist_ok=True)

            with open(tmp_audio_path, "wb") as f:
                f.write(audio_bytes)

            logger.info(f"[Audio] Starting Sarvam batch job for {safe_name}.{ext} ({len(audio_bytes)} bytes)")

            client = SarvamAI(api_subscription_key=SARVAM_API_KEY)

            job = client.speech_to_text_job.create_job(
                model="saaras:v3",
                mode="transcribe",
                language_code="unknown",
                with_diarization=True,
                num_speakers=2,
            )
            logger.info(f"[Audio] Batch job created: {job.job_id}")

            job.upload_files(file_paths=[tmp_audio_path])
            logger.info(f"[Audio] File uploaded to job {job.job_id}")

            job.start()
            logger.info(f"[Audio] Batch job {job.job_id} started, waiting for completion...")

            start_ts = _datetime.now()
            job.wait_until_complete(poll_interval=5, timeout=1800)
            elapsed = (_datetime.now() - start_ts).total_seconds()
            logger.info(f"[Audio] Batch job {job.job_id} completed in {elapsed:.1f}s")

            file_results = job.get_file_results()
            successful = file_results.get("successful", [])
            failed = file_results.get("failed", [])
            logger.info(f"[Audio] Results — successful: {len(successful)}, failed: {len(failed)}")
            for f in failed:
                logger.error(f"[Audio] Failed file: {f.get('file_name')} — {f.get('error_message')}")

            if not successful:
                logger.error(f"[Audio] Batch job {job.job_id} had no successful files")
                return ""

            job.download_outputs(output_dir=tmp_output_dir)

            output_json_path = os.path.join(tmp_output_dir, f"{safe_name}.json")
            if not os.path.exists(output_json_path):
                all_files = os.listdir(tmp_output_dir)
                json_files = [fn for fn in all_files if fn.endswith(".json")]
                if json_files:
                    output_json_path = os.path.join(tmp_output_dir, json_files[0])
                    logger.info(f"[Audio] Using output file: {json_files[0]}")
                else:
                    logger.error(f"[Audio] No JSON output found in {tmp_output_dir}. Files: {all_files}")
                    return ""

            with open(output_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            raw_json_str = json.dumps(data, ensure_ascii=False, indent=2)

            diarized = data.get("diarized_transcript") or {}
            segments = diarized.get("segments") or []

            if segments:
                lines = []
                for seg in segments:
                    speaker = seg.get("speaker", "SPEAKER")
                    start = seg.get("start", 0)
                    end = seg.get("end", 0)
                    text = seg.get("text", "").strip()
                    lines.append(f"[{speaker} {start:.1f}s-{end:.1f}s]: {text}")
                formatted = "\n".join(lines)
                logger.info(f"[Audio] Diarized transcript: {len(segments)} segments, {len(formatted)} chars")
            else:
                formatted = data.get("transcript", "")
                logger.info(f"[Audio] Plain transcript: {len(formatted)} chars (no diarization data)")

            if debug_key:
                debug_content = f"=== RAW JSON RESPONSE ===\n{raw_json_str}\n\n=== FORMATTED TRANSCRIPT ===\n{formatted}"
                self._save_debug_text(f"{debug_key}_full_transcript.txt", debug_content)

            return formatted

        except Exception as e:
            logger.error(f"[Audio] Batch job failed: {e}", exc_info=True)
            return ""
        finally:
            import shutil
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

    def transcribe_audio(self, audio_bytes: bytes, filename: str = "audio.wav", cache_key: str = "") -> str:
        if not SARVAM_API_KEY:
            logger.warning("[Audio] SARVAM_API_KEY not set, skipping transcription")
            return ""

        detected_ext, _ = self.detect_audio_format(audio_bytes)
        base = filename.rsplit(".", 1)[0] if "." in filename else filename

        safe_base = re.sub(r'[^\w-]', '_', base)[:40]
        debug_key = cache_key[:8] if cache_key else _datetime.now().strftime("%Y%m%d_%H%M%S")
        full_debug_key = f"{safe_base}_{debug_key}"

        self._save_debug_bytes(f"{full_debug_key}_full.{detected_ext}", audio_bytes)

        if cache_key:
            cached = local_store.cache_get_chunk(cache_key, 0)
            if cached is not None:
                logger.info(f"[Audio] Full transcript loaded from cache for key {cache_key[:8]}")
                return cached

        result = self._run_batch_job(audio_bytes, detected_ext, full_debug_key)

        if result and cache_key:
            local_store.cache_set_chunk(cache_key, 0, result)

        return result
