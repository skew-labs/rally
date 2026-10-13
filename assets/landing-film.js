// Keep the film out of the landing page's network and decode budget until asked.
const section = document.querySelector('.l-film');
if (section) {
  const media = section.querySelector('.l-film-media');
  const video = section.querySelector('video');
  const trigger = section.querySelector('.l-film-play');
  const label = section.querySelector('.l-film-play-label');
  const status = section.querySelector('.l-film-status');
  const fallback = section.querySelector('.l-film-fallback');
  let loading = false;
  let timer;
  let attempt = 0;

  function reset(message = '', replay = false) {
    clearTimeout(timer);
    loading = false;
    media.classList.remove('is-active', 'is-loading');
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
    video.pause();
    reset(error?.name === 'AbortError' ? '' : 'The film could not load. Try again or open the video.');
    if (document.activeElement === video) trigger.focus({preventScroll: true});
  }

  trigger.addEventListener('click', async event => {
    event.preventDefault();
    if (loading) return;
    const id = ++attempt;
    loading = true;
    trigger.setAttribute('aria-disabled', 'true');
    label.textContent = 'Loading…';
    status.textContent = 'Loading the film.';
    fallback.hidden = true;
    media.classList.add('is-loading');
    video.controls = true;
    if (!video.getAttribute('src')) {
      const supportsWebM = video.canPlayType('video/webm; codecs="vp9, opus"');
      video.src = supportsWebM ? video.dataset.webm : video.dataset.mp4;
      video.load();
    } else if (video.error) {
      video.load();
    } else if (video.ended) {
      video.currentTime = 0;
    }
    timer = setTimeout(() => fail(id), 15000);
    try {
      // Call in the original tap handler so iOS retains the audio gesture.
      await video.play();
      if (id !== attempt) return;
      clearTimeout(timer);
      loading = false;
      media.classList.remove('is-loading');
      media.classList.add('is-active');
      const transferFocus = document.activeElement === trigger;
      trigger.hidden = true;
      status.textContent = '';
      video.tabIndex = 0;
      if (transferFocus) video.focus({preventScroll: true});
    } catch (error) {
      fail(id, error);
    }
  });
  trigger.addEventListener('keydown', event => {
    if (event.key === ' ') { event.preventDefault(); trigger.click(); }
  });
  video.addEventListener('error', () => fail(attempt));
  video.addEventListener('ended', () => {
    const transferFocus = document.activeElement === video;
    reset('', true);
    if (transferFocus) trigger.focus({preventScroll: true});
  });
  function pause() {
    if (document.fullscreenElement === video || document.pictureInPictureElement === video || video.webkitDisplayingFullscreen) return;
    video.pause();
    if (loading) { ++attempt; reset(); }
  }
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(entries => {
      if (!entries[0].isIntersecting) pause();
    }, {threshold: 0}).observe(media);
  }
  document.addEventListener('visibilitychange', () => { if (document.hidden) pause(); });
  window.addEventListener('pagehide', pause);
}
