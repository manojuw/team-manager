import io
import logging
import os
import requests
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY", "")
SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"
CHUNK_MS = 25_000

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

    def to_stt_wav(self, audio_bytes: bytes, filename: str = "audio.m4a") -> bytes:
        from pydub import AudioSegment
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "mp4"
        audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format=ext)
        audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
        wav_io = io.BytesIO()
        audio.export(wav_io, format="wav")
        wav_io.seek(0)
        result = wav_io.getvalue()
        logger.info(f"[Audio] Converted {filename} to 16kHz mono WAV ({len(audio_bytes)} -> {len(result)} bytes)")
        return result

    def _post_chunk(self, wav_bytes: bytes, filename: str) -> str:
        response = None
        try:
            response = requests.post(
                SARVAM_STT_URL,
                headers={"api-subscription-key": SARVAM_API_KEY},
                files={"file": (filename, io.BytesIO(wav_bytes), "audio/wav")},
                data={
                    "model": "saarika:v2.5",
                    "language_code": "unknown",
                    "with_timestamps": "false",
                },
                timeout=60,
            )
            response.raise_for_status()
            transcript = response.json().get("transcript", "")
            logger.info(f"[Audio] Chunk {filename}: {len(transcript)} chars")
            return transcript
        except requests.exceptions.HTTPError:
            body = response.text if response is not None else "(no response)"
            logger.error(f"[Audio] SarvamAI {response.status_code if response is not None else '?'}: {body}")
            return ""
        except Exception as e:
            logger.error(f"[Audio] Chunk request failed for {filename}: {e}")
            return ""

    def _transcribe_wav_bytes(self, wav_bytes: bytes, base: str) -> str:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(io.BytesIO(wav_bytes), format="wav")
        duration_s = len(audio) / 1000.0

        if duration_s <= 25:
            return self._post_chunk(wav_bytes, f"{base}.wav")

        logger.info(f"[Audio] Audio is {duration_s:.1f}s — splitting into 25s chunks")
        chunks = [audio[i:i + CHUNK_MS] for i in range(0, len(audio), CHUNK_MS)]
        total = len(chunks)

        def _export_and_send(args):
            idx, chunk = args
            chunk_io = io.BytesIO()
            chunk.export(chunk_io, format="wav")
            chunk_bytes = chunk_io.getvalue()
            chunk_s = len(chunk) / 1000.0
            logger.info(f"[Audio] Transcribing chunk {idx}/{total} ({chunk_s:.1f}s, {len(chunk_bytes)} bytes)")
            return self._post_chunk(chunk_bytes, f"{base}_chunk{idx}.wav")

        with ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(_export_and_send, enumerate(chunks, 1)))

        parts = [r for r in results if r]
        transcript = " ".join(parts)
        logger.info(f"[Audio] Merged {total} chunks → {len(transcript)} chars total")
        return transcript

    def transcribe_audio(self, audio_bytes: bytes, filename: str = "audio.wav") -> str:
        if not SARVAM_API_KEY:
            logger.warning("[Audio] SARVAM_API_KEY not set, skipping transcription")
            return ""

        detected_ext, _ = self.detect_audio_format(audio_bytes)
        base = filename.rsplit(".", 1)[0] if "." in filename else filename

        try:
            logger.info(f"[Audio] Converting {base}.{detected_ext} to 16kHz mono WAV")
            wav_bytes = self.to_stt_wav(audio_bytes, f"{base}.{detected_ext}")
        except Exception as e:
            logger.warning(f"[Audio] WAV conversion failed for {base}.{detected_ext}: {e}")
            return ""

        return self._transcribe_wav_bytes(wav_bytes, base)
