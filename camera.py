"""
camera.py
─────────
JARVIS's eyes. Captures a single frame from the webcam on demand and
has Claude vision describe it.

Per the build brief:
  - single file at the project root
  - OpenCV (cv2) grabs one frame from the default webcam
  - exposes get_camera_description() for the brain
  - no PyAudio / audio packages involved
  - install with:  C:\\jarvis\\.venv\\Scripts\\pip.exe install opencv-python

One deliberate substitution from the brief: the description comes from
Claude vision (the same Anthropic account the brain already uses), not
a second OpenAI account. Same eyes, one API key.
"""

import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

try:
    import cv2
    CV2_OK = True
except Exception as _e:
    CV2_OK = False
    _CV2_ERR = str(_e)

CAMERA_INDEX = getattr(config, "CAMERA_INDEX", 0)


LAST_FRAME_FILE = config.MEMORY_DIR / "last_camera.jpg"


def _recent_shared_frame():
    """If the live camera panel is open it owns the webcam — but it also
    saves a frame every second. Use that if it's fresh (< 4s old)."""
    try:
        import time
        if LAST_FRAME_FILE.exists() and \
                time.time() - LAST_FRAME_FILE.stat().st_mtime < 4:
            return LAST_FRAME_FILE.read_bytes()
    except Exception:
        pass
    return None


def capture_frame_jpeg():
    """Grab one frame from the webcam, return JPEG bytes (or raise)."""
    if not CV2_OK:
        raise RuntimeError(
            f"OpenCV not installed ({_CV2_ERR}). Run: "
            r"C:\jarvis\.venv\Scripts\pip.exe install opencv-python")
    shared = _recent_shared_frame()
    if shared:
        return shared
    cap = cv2.VideoCapture(CAMERA_INDEX)
    try:
        if not cap.isOpened():
            shared = _recent_shared_frame()
            if shared:
                return shared
            raise RuntimeError(
                f"Could not open webcam (index {CAMERA_INDEX}). "
                "Check camera privacy settings or CAMERA_INDEX in config.py.")
        # a few warm-up reads so auto-exposure settles
        for _ in range(3):
            cap.read()
        ok, frame = cap.read()
        if not ok or frame is None:
            raise RuntimeError("Webcam returned no frame.")
        # keep the upload modest
        h, w = frame.shape[:2]
        if w > 1280:
            scale = 1280 / w
            frame = cv2.resize(frame, (1280, int(h * scale)))
        ok, buf = cv2.imencode(".jpg", frame,
                               [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ok:
            raise RuntimeError("Could not encode frame.")
        data = bytes(buf)
        try:
            LAST_FRAME_FILE.parent.mkdir(exist_ok=True)
            LAST_FRAME_FILE.write_bytes(data)
        except Exception:
            pass
        return data
    finally:
        cap.release()


def get_camera_description(client=None, question=None) -> str:
    """Look through the webcam once and describe what's there.

    client   : an anthropic.Anthropic() instance (the brain passes its own)
    question : optional specific question, e.g. "what am I holding?"
    """
    try:
        jpeg = capture_frame_jpeg()
    except Exception as e:
        return f"My eyes are unavailable, sir: {e}"

    if client is None:
        try:
            from anthropic import Anthropic
            client = Anthropic()
        except Exception as e:
            return f"Camera worked but the vision brain is unreachable: {e}"

    prompt = question or ("Describe what you see through this webcam in "
                          "2-4 sentences, as JARVIS reporting to Shaun. "
                          "Mention people, objects and anything notable.")
    try:
        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=400,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": "image/jpeg",
                    "data": base64.b64encode(jpeg).decode()}},
                {"type": "text", "text": prompt},
            ]}],
        )
        return "".join(getattr(b, "text", "") for b in response.content).strip() \
            or "I saw the frame but words failed me, sir."
    except Exception as e:
        return f"I captured the image but could not analyse it: {e}"


if __name__ == "__main__":
    # standalone test:  python camera.py
    print(get_camera_description())
