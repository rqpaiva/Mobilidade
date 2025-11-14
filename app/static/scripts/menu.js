document.addEventListener('DOMContentLoaded', () => {
  const burger = document.querySelector('.hamburger');
  const side   = document.getElementById('sideMenu');
  const main   = document.querySelector('main.wrapper') || document.querySelector('.main-content');

  burger?.addEventListener('click', () => {
    side?.classList.toggle('open');
    main?.classList.toggle('shifted');
    burger.classList.toggle('is-active');
  });

  // fecha o menu ao clicar em um link (mobile)
  document.querySelectorAll('#sideMenu a').forEach(a => {
    a.addEventListener('click', () => {
      if (window.innerWidth < 980) {
        side?.classList.remove('open');
        main?.classList.remove('shifted');
      }
    });
  });

  // marca item ativo
  const here = location.pathname.replace(/\/+$/, '');
  document.querySelectorAll('#sideMenu a').forEach(a => {
    const href = (a.getAttribute('href') || '').replace(/\/+$/, '');
    if (href && (here === href || here.startsWith(href))) a.classList.add('active');
  });
});


