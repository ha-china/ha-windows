"""Standalone mini player preview: fake track + generated artwork + screenshot."""
import io, sys, time, threading
sys.path.insert(0, '.')
from PIL import Image, ImageDraw

# generate a vivid "album cover"
img = Image.new("RGB", (600, 600))
d = ImageDraw.Draw(img)
for y in range(600):
    t = y / 599
    d.line([(0, y), (600, y)], fill=(int(120+100*t), int(60+40*t), int(200-80*t)))
for i in range(12):
    x = 30 + i*45
    d.ellipse((x, 500 - (i*35 % 300), x+38, 538 - (i*35 % 300)), outline=(255,220,120), width=6)
buf = io.BytesIO(); img.save(buf, "JPEG")

from src.ui import mini_player

commands = []
mini_player.set_command_handler(lambda cmd: commands.append(cmd))
mini_player.set_volume_handler(lambda v: print("VOL:", v, flush=True))

mini_player.set_enabled(True)
mini_player._mgr._position = (120, 120)
mini_player.update_track("Neon Tides", "Halcyon", 238000)
mini_player.set_artwork(buf.getvalue())
mini_player.set_volume(65)
mini_player.set_playing(True)
mini_player.set_sync(12, True)
mini_player.show()
time.sleep(1.2)

# simulate progress at 72s
mini_player.update_progress(72000, 1.0)
mgr = mini_player._mgr
if mgr._canvas is not None:
    # push lyric lines directly for preview
    mgr._queue.put(("lyrics", mgr._lyric_fetch_id,
                    [(0, ""), (30000, "\u591c\u8272\u4e2d\u7684\u5149\u4e00\u884c\u884c\u9000\u540e"), (90000, "We ride the neon tide tonight")]))
    mgr.update_progress(95000, 1.0)
time.sleep(0.8)

win = mgr._win
x, y = win.winfo_x(), win.winfo_y()
w, h = win.winfo_width(), win.winfo_height()
with open("C:/tmp/mp/rect.txt", "w") as f:
    f.write(f"{x},{y},{w},{h}")
print("RECT", x, y, w, h, flush=True)
time.sleep(6)

# --- debug total label ---
def dbg():
    mgr = mini_player._mgr
    print("duration_ms:", mgr._duration_ms, flush=True)
    print("total text:", mgr._canvas.itemcget(mgr._total_id, "text"), flush=True)
mgr._root.after(1500, dbg)
time.sleep(4)
