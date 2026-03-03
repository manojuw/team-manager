import io
import logging
import os
import requests

logger = logging.getLogger(__name__)

SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY", "")
SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"

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

    def transcribe_audio(self, audio_bytes: bytes, filename: str = "audio.wav") -> str:
        if not SARVAM_API_KEY:
            logger.warning("[Audio] SARVAM_API_KEY not set, skipping transcription")
            return ""

        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "wav"
        mime_map = {
            "wav": "audio/wav", "mp3": "audio/mpeg", "amr": "audio/amr",
            "ogg": "audio/ogg", "m4a": "audio/mp4", "aac": "audio/aac",
            "webm": "audio/webm", "3gp": "audio/3gpp",
        }
        mime_type = mime_map.get(ext, "audio/wav")

        try:
            logger.info(f"[Audio] Transcribing {filename} ({len(audio_bytes)} bytes) via SarvamAI")
            response = requests.post(
                SARVAM_STT_URL,
                headers={"api-subscription-key": SARVAM_API_KEY},
                files={"file": (filename, io.BytesIO(audio_bytes), mime_type)},
                data={
                    "model": "saarika:v2",
                    "language_code": "unknown",
                    "with_timestamps": "false",
                },
                timeout=60,
            )
            response.raise_for_status()
            result = response.json()
            transcript = result.get("transcript", "")
            logger.info(f"[Audio] Transcription complete: {len(transcript)} chars")
            return transcript
        except Exception as e:
            logger.error(f"[Audio] Transcription failed for {filename}: {e}")
            return ""
