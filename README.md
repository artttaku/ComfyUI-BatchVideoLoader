# ComfyUI Batch Video Loader

A ComfyUI custom node that batch-processes every video in a folder through
your existing single-video workflow — no loop nodes, no external scripts.

Loads videos one at a time from a folder. In `incremental_video` mode it
moves to the next file in the folder every time you queue the prompt, so
you can batch-process an entire folder by queuing N times (or using
ComfyUI's "Auto Queue" / queuing N prompts up front).

This avoids trying to load every video into one giant tensor at once,
which is how `VHS_LoadVideo` works for a single file but isn't practical
for a whole folder of videos.

## Install

**Via git clone (recommended):**

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/artttaku/ComfyUI-BatchVideoLoader
```

**Or manually:** download this repo as a ZIP and extract it into
`ComfyUI/custom_nodes/` so the path looks like
`ComfyUI/custom_nodes/ComfyUI-BatchVideoLoader/`.

Then:

1. Make sure `opencv-python`, `numpy`, and `torch` are available in your
   ComfyUI environment (opencv is already a dependency of VHS, so if VHS
   works, you're set).
2. Restart ComfyUI. You'll find the node under
   **video/batch → Batch Video Loader (Folder)**.


## Recommended: guard against odd-dimension encoder crashes

This package also includes **Ensure Even Dimensions (encode-safe)**
(`video/batch` category). Insert it between your upscaler's output and
`VHS_VideoCombine`'s `images` input. `yuv420p`/H.264 encoding requires
both width and height to be even numbers — if a scale factor (e.g. 1.5×)
lands on an odd dimension for a particular source resolution, the encoder
can die mid-write with a cryptic `OSError: [Errno 22] Invalid argument`.
This node crops 1px off the edge only when needed, so it's a no-op for
videos that were already fine.

##Wiring it into your RTX-Upscaler-1080 workflow

1. Delete the existing `VHS_LoadVideo` node (and `VHS_VideoInfo`, since
   this node reports frame_rate directly and VideoInfo isn't needed to
   drive the pipeline).
2. Add **Batch Video Loader (Folder)**.
3. Set the `folder` widget to the folder containing your videos.
4. Connect its outputs:
   - `IMAGE` → **Ensure Even Dimensions** → `RTXVideoSuperResolution.images`
   - `frame_rate` → `VHS_VideoCombine.frame_rate` (right-click the
     `frame_rate` widget on VHS_VideoCombine → "Convert to input" if it
     isn't already an input socket, then connect)
   - `filename` → `VHS_VideoCombine.filename_prefix` (same — convert to
     input first) so each output file is named after its source video
     instead of all sharing the same `AnimateDiff_00001` prefix.
   - `video_info` → `VHS_VideoInfo.video_info`, exactly like
     `VHS_LoadVideo`'s own `video_info` output, if you want the
     source/loaded fps/duration/width/height readout node.
5. Leave `mode` as `incremental_video`.

## Batch-running it

- Queue the prompt once per video (ComfyUI's queue button, N times), or
  turn on **Auto Queue** in the ComfyUI menu and let it rip — it'll stop
  being useful once the folder wraps around (the counter loops via
  modulo), so keep an eye on `video_index` / `total_videos` in the node
  output if you want to know when you've done a full pass.
- If you want a single, exact rerun of one file, switch `mode` to
  `single_video` and set `index` manually.

## Widgets

| Widget | What it does |
|---|---|
| `folder` | Folder to pull videos from |
| `mode` | `incremental_video` (advance each queue) or `single_video` (pinned to `index`) |
| `index` | Used only in `single_video` mode |
| `extensions` | Comma-separated list of video extensions to include |
| `frame_load_cap` | Max frames to load (0 = no cap) |
| `skip_first_frames` | Skip N frames at the start |
| `select_every_nth` | Only keep every Nth frame |
| `force_rate` | Override output frame rate (0 = use source fps) |

## Troubleshooting

**`OSError: [Errno 22] Invalid argument` in `VHS_VideoCombine`, on some
videos in a batch but not others:**

This means the `ffmpeg` subprocess died mid-encode and Python's next
`stdin.write()` hit the closed pipe — the traceback always points at
`VHS_VideoCombine`, not this loader, since decoding already succeeded by
that point. Two known causes:

1. **Odd width/height.** `yuv420p`/H.264 needs both dimensions divisible
   by 2. Fix: use the included **Ensure Even Dimensions** node (see
   above) between your upscaler and `VHS_VideoCombine`.
2. **NVENC hardware encoder session conflict.** GeForce cards cap the
   number of concurrent NVENC sessions. Another app doing hardware video
   encoding at the same time (OBS, Discord, a browser tab, or a stray
   leftover `ffmpeg.exe` process from an earlier crashed run — check Task
   Manager) can cause a new session request to silently fail. This
   affects specific videos inconsistently and isn't something this node
   can detect or fix automatically.

To tell them apart: temporarily switch `VHS_VideoCombine`'s `format`
widget from `video/nvenc_h264-mp4` to `video/h264-mp4` (software
encode) and rerun just the failing video. If it succeeds, it was NVENC —
close conflicting apps/processes and switch back. If it still fails,
it's almost certainly cause #1, or the source file itself has an
unusual/corrupt stream worth checking with `ffprobe` outside ComfyUI.
