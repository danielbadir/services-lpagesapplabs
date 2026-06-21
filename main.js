(function () {
  'use strict';

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
}());
