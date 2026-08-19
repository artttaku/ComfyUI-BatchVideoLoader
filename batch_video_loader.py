import os
import numpy as np
import torch
import cv2


class BatchVideoLoader:
    """
    Loads videos one-at-a-time from a folder, advancing to the next file
    each time the prompt is queued (mode = incremental_video). Queue this
    workflow N times (or use ComfyUI's Auto Queue) to batch-process every
    video in the folder, one full pipeline run per video.

    Use mode = single_video + the `index` widget if you want to pin it to
    one specific file in the folder instead (e.g. for testing settings).
    """

    _counters = {}  # per-folder incremental counters, kept in memory

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "folder": ("STRING", {"default": "", "multiline": False}),
                "mode": (["incremental_video", "single_video"], {"default": "incremental_video"}),
                "index": ("INT", {"default": 0, "min": 0, "max": 999999, "step": 1}),
                "extensions": ("STRING", {"default": "mp4,mov,avi,mkv,webm"}),
                "frame_load_cap": ("INT", {"default": 0, "min": 0, "max": 100000, "step": 1}),
                "skip_first_frames": ("INT", {"default": 0, "min": 0, "max": 100000, "step": 1}),
                "select_every_nth": ("INT", {"default": 1, "min": 1, "max": 100, "step": 1}),
                "force_rate": ("FLOAT", {"default": 0, "min": 0, "max": 120, "step": 0.01}),
            }
        }

    RETURN_TYPES = ("IMAGE", "INT", "FLOAT", "STRING", "INT", "INT", "VHS_VIDEOINFO")
    RETURN_NAMES = ("IMAGE", "frame_count", "frame_rate", "filename", "video_index", "total_videos", "video_info")
    FUNCTION = "load_batch"
    CATEGORY = "video/batch"

    # ---------- helpers ----------

    def _get_video_list(self, folder, extensions):
        exts = tuple("." + e.strip().lower().lstrip(".") for e in extensions.split(",") if e.strip())
        files = [f for f in sorted(os.listdir(folder)) if f.lower().endswith(exts)]
        return files

    def _load_video_frames(self, filepath, frame_load_cap, skip_first_frames, select_every_nth, force_rate):
        cap = cv2.VideoCapture(filepath)
        if not cap.isOpened():
            raise ValueError(f"BatchVideoLoader: could not open video {filepath}")

        src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        src_frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        src_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        src_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        src_duration = (src_frame_count / src_fps) if src_fps else 0.0

        out_fps = force_rate if force_rate and force_rate > 0 else src_fps

        frames = []
        idx = 0
        loaded = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if idx < skip_first_frames:
                idx += 1
                continue
            if (idx - skip_first_frames) % select_every_nth != 0:
                idx += 1
                continue
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(frame)
            loaded += 1
            idx += 1
            if frame_load_cap and loaded >= frame_load_cap:
                break
        cap.release()

        if not frames:
            raise ValueError(f"BatchVideoLoader: no frames decoded from {filepath}")

        arr = np.stack(frames).astype(np.float32) / 255.0
        tensor = torch.from_numpy(arr)

        loaded_frame_count = tensor.shape[0]
        loaded_height, loaded_width = frames[0].shape[0], frames[0].shape[1]
        loaded_duration = (loaded_frame_count / out_fps) if out_fps else 0.0

        # Mirrors the VHS_VIDEOINFO dict shape so this plugs straight into
        # VHS_VideoInfo (or anything else expecting that type) the same
        # way VHS_LoadVideo's video_info output does.
        video_info = {
            "source_fps": src_fps,
            "source_frame_count": src_frame_count,
            "source_duration": src_duration,
            "source_width": src_width,
            "source_height": src_height,
            "loaded_fps": out_fps,
            "loaded_frame_count": loaded_frame_count,
            "loaded_duration": loaded_duration,
            "loaded_width": loaded_width,
            "loaded_height": loaded_height,
        }

        return tensor, loaded_frame_count, out_fps, video_info

    # ---------- main ----------

    def load_batch(self, folder, mode, index, extensions, frame_load_cap,
                    skip_first_frames, select_every_nth, force_rate):
        if not folder or not os.path.isdir(folder):
            raise ValueError(f"BatchVideoLoader: folder not found: {folder}")

        files = self._get_video_list(folder, extensions)
        if not files:
            raise ValueError(f"BatchVideoLoader: no video files found in '{folder}' "
                              f"matching extensions: {extensions}")

        total = len(files)

        if mode == "incremental_video":
            key = os.path.abspath(folder)
            cur = self._counters.get(key, index)
            use_index = cur % total
            self._counters[key] = cur + 1
        else:
            use_index = index % total

        filepath = os.path.join(folder, files[use_index])
        images, frame_count, fps, video_info = self._load_video_frames(
            filepath, frame_load_cap, skip_first_frames, select_every_nth, force_rate
        )

        # strip extension so it's clean to feed into filename_prefix downstream
        clean_name = os.path.splitext(files[use_index])[0]

        return (images, frame_count, fps, clean_name, use_index, total, video_info)

    @classmethod
    def IS_CHANGED(cls, folder, mode, index, extensions, frame_load_cap,
                    skip_first_frames, select_every_nth, force_rate):
        # Force re-execution every queue when incrementing, so the counter
        # actually advances instead of being cached/skipped.
        if mode == "incremental_video":
            return float("nan")
        return f"{folder}-{index}-{extensions}-{frame_load_cap}-{skip_first_frames}-{select_every_nth}-{force_rate}"


NODE_CLASS_MAPPINGS = {
    "BatchVideoLoader": BatchVideoLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "BatchVideoLoader": "Batch Video Loader (Folder)",
}
