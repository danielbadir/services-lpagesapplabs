(function () {
  'use strict';
  // Set before the body paints so the CSS below can hide .reveal elements.
  // If this file fails to load, the class is never added, no .reveal is ever
  // hidden, and the whole page stays readable — the animation is the thing
  // that degrades, not the content. Previously .reveal was hidden by default
  // and only JS could reveal it, so one failed request blanked 151 elements
  // across the platform with no error and no fallback.
  document.documentElement.className += ' js';
}());

(function () {
  'use strict';
  // Everything below touches the DOM. main.js is loaded in <head> without
  // defer so the .js flag above lands before first paint — which means the
  // body is NOT parsed yet at this point. Running querySelectorAll here
  // directly matched zero elements, so nothing was ever observed and every
  // .reveal element stayed at opacity:0 permanently. Wait for the DOM.
  function boot() {

    var revealObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) {
          e.target.classList.add('visible');
          revealObserver.unobserve(e.target);
        }
      });
    }, { threshold: 0.12 });
    document.querySelectorAll('.reveal').forEach(function (el) {
      revealObserver.observe(el);
    });

    var ham = document.getElementById('hamburger');
    var navMobile = document.getElementById('navMobile');
    if (ham && navMobile) {
      ham.setAttribute('aria-expanded', 'false');
      ham.setAttribute('aria-controls', 'navMobile');
      ham.addEventListener('click', function () {
        var isOpen = navMobile.classList.toggle('open');
        ham.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
      });
      navMobile.querySelectorAll('a').forEach(function (a) {
        a.addEventListener('click', function () {
          navMobile.classList.remove('open');
          ham.setAttribute('aria-expanded', 'false');
        });
      });
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
}());
