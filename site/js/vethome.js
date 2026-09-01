/* ==========================================================================
   VetHome — seção de veterinários
   Lê data/veterinarios.json (gerenciado pelo painel em /admin), mostra 6 por
   página em grade 3x2 e leva para a página individual ao clicar.
   Só entram os marcados como "ativo", na ordem definida no painel.
   ========================================================================== */
(function () {
  "use strict";

  var PER_PAGE = 6;
  var SHADOWS = ["purple-shadow", "orange-shadow", "yellow-shadow"];

  var grid = document.getElementById("vetGrid");
  var dots = document.getElementById("vetDots");
  var count = document.getElementById("vetCount");
  var prev = document.getElementById("vetPrev");
  var next = document.getElementById("vetNext");

  if (!grid) return;

  var vets = [];
  var page = 0;
  var pages = 1;
  var alturaMaxGrade = 0;

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* linha do card que só aparece se o campo estiver preenchido */
  function linha(classe, texto) {
    return texto ? '<div class="' + classe + '">' + escapeHtml(texto) + "</div>" : "";
  }

  function renderPage() {
    var start = page * PER_PAGE;
    var slice = vets.slice(start, start + PER_PAGE);

    grid.innerHTML = slice
      .map(function (vet, offset) {
        var index = start + offset;
        var sombra = SHADOWS[index % SHADOWS.length];
        return (
          '<a class="team-block ' + sombra + '" href="vet.html?vet=' + encodeURIComponent(vet.slug) + '">' +
          '<img src="' + escapeHtml(vet.foto) + '" loading="lazy" alt="' + escapeHtml(vet.nome) + '" class="team-member-image"/>' +
          '<div class="team-member-name-wrapper">' +
          '<div class="h6 dark-font-color">' + escapeHtml(vet.nome) + "</div>" +
          linha("paragraph dark-grey-color", vet.especialidade) +
          linha("vet-card-crmv", vet.crmv) +
          linha("vet-card-cidade", vet.cidade) +
          "</div>" +
          '<span class="vet-perfil-btn">Ver perfil &rarr;</span>' +
          "</a>"
        );
      })
      .join("");

    prev.disabled = page === 0;
    next.disabled = page >= pages - 1;
    count.textContent = slice.length
      ? start + 1 + "–" + (start + slice.length) + " de " + vets.length
      : "";

    var showControls = pages > 1;
    prev.hidden = !showControls;
    next.hidden = !showControls;
    count.hidden = !showControls;

    dots.innerHTML = !showControls
      ? ""
      : Array.apply(null, { length: pages })
          .map(function (_, i) {
            return (
              '<li><button type="button" data-page="' + i + '" aria-current="' + (i === page) +
              '" aria-label="Página ' + (i + 1) + ' de veterinários"></button></li>'
            );
          })
          .join("");

    travarAltura();
  }

  /* A última página tem menos cards. Sem isto a seção encolhe, o navegador corta
     a rolagem e o visitante é jogado para a seção seguinte ao clicar na seta. */
  function travarAltura() {
    grid.style.minHeight = "";
    var altura = grid.offsetHeight;
    if (altura > alturaMaxGrade) alturaMaxGrade = altura;
    if (alturaMaxGrade) grid.style.minHeight = alturaMaxGrade + "px";
  }

  var recalcular;
  window.addEventListener("resize", function () {
    clearTimeout(recalcular);
    recalcular = setTimeout(function () {
      alturaMaxGrade = 0;
      travarAltura();
    }, 150);
  });

  dots.addEventListener("click", function (event) {
    var button = event.target.closest("button");
    if (!button) return;
    page = Number(button.dataset.page);
    renderPage();
  });

  prev.addEventListener("click", function () {
    if (page > 0) {
      page--;
      renderPage();
    }
  });

  next.addEventListener("click", function () {
    if (page < pages - 1) {
      page++;
      renderPage();
    }
  });

  fetch("data/veterinarios.json", { cache: "no-store" })
    .then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(function (data) {
      vets = (Array.isArray(data) ? data : [])
        /* o painel marca quem sai do ar sem apagar o cadastro */
        .filter(function (v) { return v.status !== "inativo"; })
        .sort(function (a, b) { return (a.ordem || 0) - (b.ordem || 0); });
      pages = Math.max(1, Math.ceil(vets.length / PER_PAGE));
      page = 0;
      renderPage();
    })
    .catch(function (error) {
      console.error("Não foi possível carregar os veterinários:", error);
      grid.innerHTML =
        '<p class="paragraph dark-grey-color">Não foi possível carregar a equipe agora. Recarregue a página.</p>';
    });
})();

/* ==========================================================================
   VetHome — depoimentos no celular
   No celular o CSS transforma o slider do template em uma faixa que desliza
   no dedo. Este trecho cuida das duas peças que o CSS não resolve:
     - as bolinhas que dizem quantos depoimentos existem e onde você está
     - o "ler mais" dos depoimentos longos, para o card não virar parede
   Acima de 767px nada disso roda: lá o slider do template segue intacto.
   ========================================================================== */
(function () {
  "use strict";

  var CELULAR = "(max-width:767px)";
  var LINHAS = 6; /* precisa bater com o -webkit-line-clamp do CSS */

  var mask = document.querySelector(".testimonial-slider-mask");
  var slider = document.querySelector(".testimonial-slider");
  if (!mask || !slider) return;

  var slides = Array.prototype.slice.call(mask.querySelectorAll(".testimonial-slide"));
  if (slides.length < 2) return;

  var dots = null;
  var montado = false;

  /* ---------- "ler mais" ---------- */
  function montarLerMais() {
    slides.forEach(function (slide) {
      var p = slide.querySelector(".testimonial-slide-text-wrapper .paragraph");
      var wrapper = slide.querySelector(".testimonial-slide-text-wrapper");
      if (!p || !wrapper || slide.querySelector(".dep-mais")) return;

      /* só ganha botão quem realmente foi cortado */
      if (p.scrollHeight <= p.clientHeight + 2) return;

      var botao = document.createElement("button");
      botao.type = "button";
      botao.className = "dep-mais";
      botao.textContent = "ler mais";
      botao.setAttribute("aria-expanded", "false");

      botao.addEventListener("click", function () {
        var aberto = slide.classList.toggle("dep-aberto");
        botao.textContent = aberto ? "ler menos" : "ler mais";
        botao.setAttribute("aria-expanded", aberto ? "true" : "false");
      });

      /* entra logo depois do texto, antes da assinatura */
      var assinatura = wrapper.querySelector(".reviewer-details");
      if (assinatura) wrapper.insertBefore(botao, assinatura);
      else wrapper.appendChild(botao);
    });
  }

  function removerLerMais() {
    mask.querySelectorAll(".dep-mais").forEach(function (b) { b.remove(); });
    slides.forEach(function (s) { s.classList.remove("dep-aberto"); });
  }

  /* ---------- bolinhas ---------- */
  function montarDots() {
    if (dots) return;
    dots = document.createElement("ul");
    dots.className = "dep-dots";

    slides.forEach(function (slide, i) {
      var li = document.createElement("li");
      var b = document.createElement("button");
      b.type = "button";
      b.setAttribute("aria-label", "Ver depoimento " + (i + 1) + " de " + slides.length);
      b.setAttribute("aria-current", i === 0 ? "true" : "false");
      b.addEventListener("click", function () {
        mask.scrollTo({ left: slide.offsetLeft - mask.offsetLeft, behavior: "smooth" });
      });
      li.appendChild(b);
      dots.appendChild(li);
    });

    slider.parentNode.insertBefore(dots, slider.nextSibling);
    mask.addEventListener("scroll", aoRolar, { passive: true });
  }

  function removerDots() {
    if (!dots) return;
    mask.removeEventListener("scroll", aoRolar);
    dots.remove();
    dots = null;
  }

  /* qual card está mais perto do centro da faixa */
  var agendado;
  function aoRolar() {
    if (agendado) return;
    agendado = requestAnimationFrame(function () {
      agendado = null;
      if (!dots) return;
      var centro = mask.scrollLeft + mask.clientWidth / 2;
      var maisPerto = 0;
      var menorDist = Infinity;
      slides.forEach(function (s, i) {
        var meio = s.offsetLeft - mask.offsetLeft + s.offsetWidth / 2;
        var d = Math.abs(meio - centro);
        if (d < menorDist) { menorDist = d; maisPerto = i; }
      });
      Array.prototype.forEach.call(dots.querySelectorAll("button"), function (b, i) {
        b.setAttribute("aria-current", i === maisPerto ? "true" : "false");
      });
    });
  }

  /* ---------- liga e desliga conforme a largura ---------- */
  function aplicar() {
    var celular = window.matchMedia(CELULAR).matches;
    if (celular && !montado) {
      montarDots();
      montarLerMais();
      montado = true;
    } else if (!celular && montado) {
      removerDots();
      removerLerMais();
      montado = false;
    }
  }

  /* o clamp só mede certo depois das fontes carregarem */
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(aplicar);
  }
  aplicar();
  window.addEventListener("load", aplicar);

  var redimensionar;
  window.addEventListener("resize", function () {
    clearTimeout(redimensionar);
    redimensionar = setTimeout(aplicar, 200);
  });
})();
