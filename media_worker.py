"""One bounded, restartable ffmpeg worker. Run separately from the web service."""
import argparse
import fcntl
import json
import math
import os
import re
import resource
import shutil
import signal
import subprocess
import time

import service as s
import media_pipeline as media

STOP = False


class EncodeError(Exception):
    pass


def child_limits():
    resource.setrlimit(resource.RLIMIT_CPU, (190, 200))
    resource.setrlimit(resource.RLIMIT_FSIZE, (media.MAX_OUTPUT, media.MAX_OUTPUT))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.nice(10)


def run(binary, args, timeout=15):
    # The encoder receives no RPC endpoint, auth token or other service secrets.
    executable = shutil.which(binary)
    if not executable:
        raise EncodeError('encoder_unavailable')
    try:
        result = subprocess.run([executable, '-hide_banner', '-v', 'error', '-max_alloc', '67108864', *args],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout, check=False,
                                env={'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8'},
                                preexec_fn=child_limits)
    except subprocess.TimeoutExpired:
        raise EncodeError('processing_timeout')
    if result.returncode:
        # Decoder diagnostics can contain original metadata; never expose them.
        raise EncodeError('invalid_video')
    if len(result.stdout) > 1_000_000:
        raise EncodeError('invalid_video')
    return result.stdout


def probe(path):
    try:
        info = json.loads(run('ffprobe', ['-protocol_whitelist', 'file,pipe', '-format_whitelist', 'mov,matroska,webm',
                                            '-show_entries', 'stream=index,codec_type,codec_name,width,height,avg_frame_rate:format=duration,format_name',
                                            '-of', 'json', str(path)], timeout=8))
        video = [x for x in info['streams'] if x['codec_type'] == 'video']
        duration = float(info['format']['duration'])
        if len(video) != 1 or len(info['streams']) > 6 or not math.isfinite(duration) or not 0 < duration <= media.MAX_DURATION:
            raise ValueError()
        width, height = int(video[0]['width']), int(video[0]['height'])
        if not 1 <= width <= 8192 or not 1 <= height <= 8192 or width * height > media.MAX_PIXELS:
            raise ValueError()
        return {**video[0], 'duration': duration, 'audio': any(x['codec_type'] == 'audio' for x in info['streams'])}
    except EncodeError:
        raise
    except Exception:
        raise EncodeError('invalid_video')


def process(job):
    ident = job['media_id']
    if not re.fullmatch(r'[a-f0-9]{32}', ident) or not re.fullmatch(ident + r'\.source\.(?:mp4|webm)', job['input_path']):
        raise EncodeError('invalid_video')
    source = s.STATE / 'media' / job['input_path']
    if source.parent != s.STATE / 'media' or not source.is_file() or source.is_symlink() or source.stat().st_size > media.MAX_UPLOAD:
        raise EncodeError('invalid_video')
    work = s.STATE / 'media' / ('.work-' + ident)
    final = s.STATE / 'media' / ident
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(mode=0o700)
    info = probe(source)
    # Cap both orientations without upscaling; square clips stay at most 720px.
    scale = "scale=w='if(gte(iw,ih),min(iw,1280),min(iw,720))':h='if(gte(iw,ih),min(ih,720),min(ih,1280))':force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1,fps=30"
    output = work / 'video.mp4'
    run('ffmpeg', ['-nostdin', '-y', '-threads', '1', '-filter_threads', '1', '-protocol_whitelist', 'file,pipe', '-format_whitelist', 'mov,matroska,webm',
                   '-i', str(source), '-map', '0:v:0', '-map', '0:a:0?', '-map_metadata', '-1', '-map_chapters', '-1',
                   '-vf', scale, '-c:v', 'libx264', '-threads', '1', '-preset', 'veryfast', '-crf', '26',
                   '-pix_fmt', 'yuv420p', '-profile:v', 'main', '-level', '4.0', '-c:a', 'aac', '-b:a', '96k', '-ac', '2',
                   '-g', '120', '-keyint_min', '120', '-sc_threshold', '0',
                   '-movflags', '+faststart', '-max_muxing_queue_size', '256', str(output)], timeout=200)
    encoded = probe(output)
    if encoded['codec_name'] != 'h264' or encoded['width'] > 1280 or encoded['height'] > 1280 or output.stat().st_size > media.MAX_OUTPUT:
        raise EncodeError('invalid_output')
    # A poster is a small decoded frame, with all source metadata removed.
    run('ffmpeg', ['-nostdin', '-y', '-threads', '1', '-filter_threads', '1', '-protocol_whitelist', 'file,pipe',
                   '-ss', str(min(.5, info['duration'] / 4)), '-i', str(output), '-frames:v', '1',
                   '-vf', 'scale=640:640:force_original_aspect_ratio=decrease', '-map_metadata', '-1', '-c:v', 'libwebp',
                   '-quality', '75', '-threads', '1', str(work / 'poster.webp')], timeout=15)
    # Short social clips use fast-start MP4. Longer clips also get 4s HLS segments.
    hls = encoded['duration'] > 15
    if hls:
        (work / 'hls').mkdir(mode=0o700)
        run('ffmpeg', ['-nostdin', '-y', '-threads', '1', '-protocol_whitelist', 'file,pipe', '-i', str(output),
                       '-map', '0:v:0', '-map', '0:a:0?', '-c', 'copy', '-map_metadata', '-1', '-f', 'hls',
                       '-hls_time', '4', '-hls_playlist_type', 'vod', '-hls_segment_filename', str(work / 'hls' / 'segment%05d.ts'),
                       str(work / 'hls' / 'index.m3u8')], timeout=20)
    total = sum(x.stat().st_size for x in work.rglob('*') if x.is_file())
    meta = {'version': media.VERSION, 'width': encoded['width'], 'height': encoded['height'],
            'duration': round(encoded['duration'], 3), 'videoBytes': output.stat().st_size,
            'originalBytes': source.stat().st_size, 'storedBytes': total, 'hls': hls}
    for path in work.rglob('*'):
        path.chmod(0o700 if path.is_dir() else 0o600)
    # Reserve actual derivative storage in the same transaction that marks ready.
    with s.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT owner,size FROM media WHERE id=?', (ident,)).fetchone()
        if not row:
            raise EncodeError('upload_removed')
        used = db.execute('SELECT coalesce(sum(size),0) FROM media WHERE owner=?', (row['owner'],)).fetchone()[0]
        if used - row['size'] + total > media.OWNER_QUOTA:
            raise EncodeError('storage_limit')
        shutil.rmtree(final, ignore_errors=True)
        work.rename(final)
        db.execute('UPDATE media SET path=?,mime=?,size=? WHERE id=?', (ident + '/video.mp4', 'video/mp4', total, ident))
        db.execute("UPDATE media_jobs SET state='ready',updated=?,error=NULL,metadata=? WHERE media_id=?", (s.now(), s.dump(meta), ident))
    source.unlink(missing_ok=True)
    return meta


def run_one():
    job = media.claim()
    if not job:
        return None
    try:
        meta = process(job)
        return {'id': job['media_id'], 'state': 'ready', **meta}
    except Exception as exc:
        reason = str(exc) if isinstance(exc, EncodeError) else 'encode_failed'
        media.fail(job, reason)
        return {'id': job['media_id'], 'state': 'failed', 'error': reason}


def main():
    global STOP
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true', help='Process at most one queued job')
    args = parser.parse_args()
    media.initialize()
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise SystemExit('Install ffmpeg and ffprobe on the remote media worker')
    with (s.STATE / 'media-worker.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('A media worker is already running')
        signal.signal(signal.SIGTERM, lambda *_: globals().__setitem__('STOP', True))
        while not STOP:
            result = run_one()
            if result:
                print(s.dump(result), flush=True)
            if args.once:
                break
            if not result:
                time.sleep(2)


if __name__ == '__main__':
    main()
