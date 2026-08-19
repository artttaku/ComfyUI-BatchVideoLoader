import torch


class EnsureEvenDimensions:
    """
    Crops 1 pixel off the bottom/right of a frame batch if width or height
    is odd. Insert this between an upscaler and VHS_VideoCombine (or any
    node writing to yuv420p/h264/nvenc) to prevent 'OSError: [Errno 22]
    Invalid argument' crashes that happen when ffmpeg is handed an
    odd-numbered frame size mid-encode.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)
    FUNCTION = "fix"
    CATEGORY = "video/batch"

    def fix(self, images):
        # images: [N, H, W, C]
        _, h, w, _ = images.shape
        new_h = h - (h % 2)
        new_w = w - (w % 2)
        if new_h == h and new_w == w:
            return (images,)
        return (images[:, :new_h, :new_w, :],)


NODE_CLASS_MAPPINGS = {
    "EnsureEvenDimensions": EnsureEvenDimensions,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "EnsureEvenDimensions": "Ensure Even Dimensions (encode-safe)",
}
