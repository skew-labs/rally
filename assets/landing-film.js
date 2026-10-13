// Media stays unloaded until an explicit play gesture. Controls work in place.
const section = document.querySelector('.l-film');
if (section?.querySelector('.l-film-controls')) {
  const media = section.querySelector('.l-film-media');
  const video = section.querySelector('video');
  const trigger = section.querySelector('.l-film-play');
  const label = section.querySelector('.l-film-play-label');
  const status = section.querySelector('.l-film-status');
  const fallback = section.querySelector('.l-film-fallback');
  const controls = section.querySelector('.l-film-controls');
  const toggle = controls.querySelector('[data-film-toggle]');
  const sound = controls.querySelector('[data-film-sound]');
  const full = controls.querySelector('[data-film-fullscreen]');
  const seek = controls.querySelector('input');
  const time = controls.querySelector('output');
  let loading = false, timer, attempt = 0, frame = 0, lastTime = '';
  const clock = value => `${Math.floor(value / 60)}:${String(Math.floor(value % 60)).padStart(2, '0')}`;
  const fullscreen = () => document.fullscreenElement === media || video.webkitDisplayingFullscreen;

  function progress() {
    const duration = Number.isFinite(video.duration) ? video.duration : 18;
    const position = Math.min(duration, video.currentTime || 0);
    seek.disabled = !Number.isFinite(video.duration);
    seek.max = String(duration);
    seek.value = String(position);
    seek.style.setProperty('--film-progress', `${duration ? position / duration * 100 : 0}%`);
    const next = `${clock(position)} / ${clock(duration)}`;
    if (next !== lastTime) {
      time.textContent = lastTime = next;
      seek.setAttribute('aria-valuetext', `${clock(position)} of ${clock(duration)}`);
    }
  }
  function stopFrame() { cancelAnimationFrame(frame); frame = 0; }
  function tick() {
    progress();
    frame = !video.paused && !video.ended && !document.hidden ? requestAnimationFrame(tick) : 0;
  }
  function sync() {
    toggle.dataset.paused = String(video.paused);
    toggle.setAttribute('aria-label', video.paused ? 'Play film' : 'Pause film');
    video.setAttribute('aria-label', video.paused ? 'Play Rally film' : 'Pause Rally film');
    sound.dataset.muted = String(video.muted);
    sound.setAttribute('aria-label', video.muted ? 'Unmute film' : 'Mute film');
    sound.setAttribute('aria-pressed', String(video.muted));
    full.setAttribute('aria-label', fullscreen() ? 'Exit fullscreen' : 'Enter fullscreen');
    full.setAttribute('aria-pressed', String(!!fullscreen()));
    progress();
    stopFrame();
    if (!video.paused && !document.hidden) frame = requestAnimationFrame(tick);
  }
  function reset(message = '', replay = false) {
    clearTimeout(timer); stopFrame(); loading = false;
    media.classList.remove('is-active', 'is-loading');
    controls.hidden = true;
    trigger.hidden = false;
    trigger.removeAttribute('aria-disabled');
    trigger.setAttribute('aria-label', replay ? 'Replay Rally film, 18 seconds' : 'Play Rally film, 18 seconds');
    label.textContent = message ? 'Try again' : replay ? 'Replay film' : 'Play film';
    status.textContent = message;
    fallback.hidden = !message;
    video.tabIndex = -1;
  }
  function fail(id, error) {
    if (id !== attempt) return;
    ++attempt;
    const transferFocus = media.contains(document.activeElement);
    video.pause();
    reset(error?.name === 'AbortError' ? '' : 'The film could not load. Try again or open the video.');
    if (transferFocus) trigger.focus({preventScroll: true});
  }
  async function play() {
    if (loading) return;
    const id = ++attempt;
    const transferFocus = document.activeElement === trigger;
    loading = true;
    trigger.setAttribute('aria-disabled', 'true');
    label.textContent = 'Loading…';
    status.textContent = 'Loading the film.';
    fallback.hidden = true;
    media.classList.add('is-loading');
    if (!video.getAttribute('src')) {
      video.src = video.canPlayType('video/webm; codecs="vp9, opus"') ? video.dataset.webm : video.dataset.mp4;
      video.load();
    } else if (video.error) video.load();
    else if (video.ended) video.currentTime = 0;
    timer = setTimeout(() => fail(id), 15000);
    try {
      await video.play();
      if (id !== attempt) return;
      clearTimeout(timer); loading = false;
      media.classList.remove('is-loading');
      media.classList.add('is-active');
      trigger.hidden = true; controls.hidden = false;
      status.textContent = ''; video.tabIndex = 0; sync();
      if (transferFocus) toggle.focus({preventScroll: true});
    } catch (error) { fail(id, error); }
  }
  function togglePlayback() { if (video.paused) play(); else video.pause(); }
  trigger.addEventListener('click', event => {event.preventDefault(); play();});
  trigger.addEventListener('keydown', event => {if (event.key === ' ') {event.preventDefault(); trigger.click();}});
  toggle.addEventListener('click', togglePlayback);
  video.addEventListener('click', togglePlayback);
  video.addEventListener('keydown', event => {
    if (event.key === ' ' || event.key === 'Enter') {event.preventDefault(); togglePlayback();}
  });
  sound.addEventListener('click', () => {video.muted = !video.muted; sync();});
  seek.addEventListener('input', () => {
    if (Number.isFinite(video.duration)) video.currentTime = Math.max(0, Math.min(video.duration, Number(seek.value)));
    progress();
  });
  full.hidden = !document.fullscreenEnabled && typeof video.webkitEnterFullscreen !== 'function';
  full.addEventListener('click', async () => {
    try {
      if (document.fullscreenElement === media) await document.exitFullscreen();
      else if (document.fullscreenEnabled) await media.requestFullscreen();
      else video.webkitEnterFullscreen?.();
    } catch {status.textContent = 'Fullscreen is unavailable in this browser.';}
  });
  for (const event of ['play', 'pause', 'volumechange', 'loadedmetadata', 'seeked']) video.addEventListener(event, sync);
  video.addEventListener('timeupdate', progress);
  document.addEventListener('fullscreenchange', sync);
  video.addEventListener('error', () => fail(attempt));
  video.addEventListener('ended', () => {
    const transferFocus = media.contains(document.activeElement);
    reset('', true);
    if (transferFocus) trigger.focus({preventScroll: true});
  });
  function pause() {
    if (fullscreen() || document.pictureInPictureElement === video) return;
    video.pause(); stopFrame();
    if (loading) {++attempt; reset();}
  }
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(entries => {if (!entries[0].isIntersecting) pause();}, {threshold: 0}).observe(media);
  }
  document.addEventListener('visibilitychange', () => {if (document.hidden) {stopFrame(); pause();}});
  window.addEventListener('pagehide', pause);
}
