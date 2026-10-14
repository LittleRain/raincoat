import fcntl
import json
import math
import os
import subprocess
import threading
import sys
import time
from fractions import Fraction
from pathlib import Path
from .core import now


class Cancelled(Exception):
    pass


class Worker:
    def __init__(self, store):
        self.store = store
        self.stop_event = threading.Event()
        self.thread = None
        self.lock = None

    def start(self):
        self.lock = open(self.store.data / 'worker.lock', 'a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock.close()
            raise RuntimeError('此数据目录已有 worker，请勿启动多个实例')
        # A crashed parent is detected by its subprocess lifeline within 0.1s.
        # Allow old supervisors to terminate before resuming persisted work.
        time.sleep(2.3)
        for partial in (self.store.data / 'uploads').glob('*.partial'):
            partial.unlink(missing_ok=True)
        with self.store.connect() as conn:
            conn.execute("UPDATE jobs SET status=CASE WHEN cancel_requested=1 THEN 'cancelled' ELSE 'queued' END, stage='重启恢复', progress=0, updated_at=? WHERE status='running'", (now(),))
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=15)
            if self.thread.is_alive():
                raise RuntimeError('worker 未能停止')
        if self.lock:
            self.lock.close()

    def update(self, jid, **fields):
        fields['updated_at'] = now()
        with self.store.connect() as conn:
            conn.execute('UPDATE jobs SET ' + ','.join(f'{k}=?' for k in fields) + ' WHERE id=?', (*fields.values(), jid))

    def check(self, jid):
        row = self.store.rows('SELECT cancel_requested FROM jobs WHERE id=?', (jid,))
        if self.stop_event.is_set() or not row or row[0]['cancel_requested']:
            raise Cancelled()

    def run(self, command, jid, output, progress=None, duration=1):
        # Output is written to disk; large ffmpeg logs never accumulate in memory.
        with open(output, 'wb') as out, open(str(output) + '.err', 'wb') as err:
            read_fd, write_fd = os.pipe()
            try:
                process = subprocess.Popen([sys.executable, '-m', 'backend.supervisor', str(read_fd), *command],
                                           stdout=out, stderr=err, stdin=subprocess.DEVNULL, pass_fds=(read_fd,))
            except BaseException:
                os.close(write_fd)
                raise
            finally:
                os.close(read_fd)
            try:
                while process.poll() is None:
                    self.check(jid)
                    if progress and progress.exists():
                        lines = progress.read_text(errors='replace').splitlines()
                        values = [x.split('=', 1)[1] for x in lines if x.startswith('out_time_us=')]
                        if values:
                            try:
                                self.update(jid, progress=min(94, 10 + float(values[-1]) / 1e6 / duration * 84))
                            except ValueError:
                                pass
                    self.stop_event.wait(0.25)
                self.check(jid)
                if process.returncode:
                    log = Path(str(output) + '.err').read_text(errors='replace')
                    raise RuntimeError(log[-3000:] or f'进程退出码 {process.returncode}')
            finally:
                os.close(write_fd)
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()

    def preprocess(self, job):
        jid, mid = job['id'], job['media_id']
        media = self.store.rows('SELECT * FROM media WHERE id=?', (mid,))[0]
        path = Path(media['path']).resolve()
        allowed = self.store.data / 'uploads' if media['managed'] else self.store.root
        if not path.is_relative_to(allowed) or not path.is_file():
            raise RuntimeError('原文件缺失或路径已越界')
        folder = self.store.data / 'derived' / mid
        folder.mkdir(exist_ok=True)
        self.update(jid, stage='探测元数据', progress=1)
        probe = folder / 'probe.json'
        self.run([os.getenv('FFPROBE_BIN', 'ffprobe'), '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)], jid, probe)
        info = json.loads(probe.read_text())
        video = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
        if not video:
            raise RuntimeError('文件没有视频流')
        duration = float(info.get('format', {}).get('duration') or video.get('duration') or 0)
        if not math.isfinite(duration) or duration <= 0:
            raise RuntimeError('无法读取有效视频时长')
        try:
            fps = float(Fraction(video.get('avg_frame_rate', '0/1')))
        except (ValueError, ZeroDivisionError):
            fps = 0
        with self.store.connect() as conn:
            conn.execute('UPDATE media SET duration=?,fps=?,width=?,height=? WHERE id=?',
                         (duration, fps, video['width'], video['height'], mid))
        ffmpeg = os.getenv('FFMPEG_BIN', 'ffmpeg')
        common = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-threads', '2', '-i', str(path)]
        self.update(jid, stage='生成 720p 代理视频', progress=10)
        progress = folder / 'progress.txt'
        progress.unlink(missing_ok=True)
        proxy_tmp = folder / 'proxy.partial.mp4'
        # Bound both dimensions, preserve aspect and handle portrait footage.
        scale = "scale=1280:720:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1"
        self.run(common + ['-map', '0:v:0', '-map', '0:a:0?', '-vf', scale, '-r', '24',
                          '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '28', '-threads', '2',
                          '-c:a', 'aac', '-b:a', '96k', '-movflags', '+faststart',
                          '-progress', str(progress), str(proxy_tmp)], jid, folder / 'proxy.log', progress, duration)
        self.update(jid, stage='生成缩略图', progress=95)
        thumb_tmp = folder / 'thumbnail.partial.jpg'
        self.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-ss', str(min(1, duration / 2)),
                  '-i', str(path), '-frames:v', '1', '-vf', 'scale=480:480:force_original_aspect_ratio=decrease',
                  '-threads', '1', str(thumb_tmp)], jid, folder / 'thumbnail.log')
        self.check(jid)
        proxy, thumb = folder / 'proxy.mp4', folder / 'thumbnail.jpg'
        proxy_tmp.replace(proxy)
        thumb_tmp.replace(thumb)
        with self.store.connect() as conn:
            conn.execute('UPDATE media SET proxy_path=?,thumbnail_path=? WHERE id=?', (str(proxy), str(thumb), mid))
        self.update(jid, status='succeeded', stage='预处理完成', progress=100, error=None)

    def loop(self):
        while not self.stop_event.is_set():
            with self.store.connect() as conn:
                conn.execute('BEGIN IMMEDIATE')
                row = conn.execute("SELECT * FROM jobs WHERE status='queued' AND cancel_requested=0 ORDER BY created_at LIMIT 1").fetchone()
                if row:
                    conn.execute("UPDATE jobs SET status='running',attempts=attempts+1,updated_at=? WHERE id=?", (now(), row['id']))
            if not row:
                self.stop_event.wait(.3)
                continue
            job = dict(row)
            try:
                self.preprocess(job)
            except Cancelled:
                cancelled = self.store.rows('SELECT cancel_requested FROM jobs WHERE id=?', (job['id'],))
                status = 'cancelled' if cancelled and cancelled[0]['cancel_requested'] else 'queued'
                self.update(job['id'], status=status, stage='已取消' if status == 'cancelled' else '等待重启恢复')
            except Exception as exc:
                self.update(job['id'], status='failed', stage='处理失败', error=str(exc)[:3000])
