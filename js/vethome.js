/* ==========================================================================
   VetHome — seção de veterinários
   Lê data/veterinarios.json, mostra 6 por página em grade 3x2 e abre um
   modal com a descrição ao clicar no card. A descrição NÃO aparece no card.
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
  var backdrop = document.getElementById("vetBackdrop");

  if (!grid) return;

  var vets = [];
  var page = 0;
  var pages = 1;
  var lastFocused = null;
  var alturaMaxGrade = 0;

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* Foto recem-enviada pelo painel ja esta no repositorio, mas o site so passa
     a servi-la depois de reconstruir. Ate la, busca a do repositorio em vez de
     mostrar um quadrado quebrado. */
  var RAIZ_REPO = "https://raw.githubusercontent.com/mychelleaneves-debug" +
    "/vethomev1/gh-pages/";

  function reservaDaFoto(caminho) {
    var url = RAIZ_REPO + String(caminho || "").replace(/^\//, "");
    return " onerror=" + '"' + "this.onerror=null;this.src=&#39;" +
      escapeHtml(url) + "&#39;" + '"';
  }

  /* as descrições vêm com quebras de linha e tópicos; preserva os parágrafos */
  function formatBio(value) {
    return escapeHtml(value).replace(/\n{2,}/g, "<br><br>").replace(/\n/g, "<br>");
  }

  function renderPage() {
    var start = page * PER_PAGE;
    var slice = vets.slice(start, start + PER_PAGE);

    grid.innerHTML = slice
      .map(function (vet, offset) {
        var index = start + offset;
        return (
          '<div class="team-block ' + SHADOWS[index % SHADOWS.length] + '" role="button" tabindex="0" aria-haspopup="dialog" data-vet="' + index + '">' +
          '<img src="' + escapeHtml(vet.foto) + '" loading="lazy" alt="' + escapeHtml(vet.nome) + '" class="team-member-image"' + reservaDaFoto(vet.foto) + '/>' +
          '<div class="team-member-name-wrapper">' +
          '<div class="h6 dark-font-color">' + escapeHtml(vet.nome) + "</div>" +
          '<div class="paragraph dark-grey-color">' + escapeHtml(vet.especialidade) + "</div>" +
          '</div>' +
          '<button class="vet-perfil-btn" data-vet="' + index + '" aria-label="Ver perfil de ' + escapeHtml(vet.nome) + '">Ver Perfil</button>' +
          "</div>"
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

  function openModal(index) {
    var vet = vets[index];
    if (!vet) return;

    lastFocused = document.activeElement;

    var regions = (vet.regioes || [])
      .map(function (region) {
        return "<li>" + escapeHtml(region) + "</li>";
      })
      .join("");

    backdrop.innerHTML =
      '<div class="vet-modal" role="dialog" aria-modal="true" aria-labelledby="vetModalTitle">' +
      '<button class="vet-close" type="button" id="vetClose" aria-label="Fechar">' +
      '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><path d="m2 2 12 12M14 2 2 14"/></svg>' +
      "</button>" +
      '<img src="' + escapeHtml(vet.foto) + '" alt="' + escapeHtml(vet.nome) + '" class="team-member-image"' + reservaDaFoto(vet.foto) + '/>' +
      '<h3 class="h6 dark-font-color" id="vetModalTitle">' + escapeHtml(vet.nome) + "</h3>" +
      '<div class="paragraph dark-grey-color vet-role">' + escapeHtml(vet.especialidade) + "</div>" +
      (vet.crmv ? '<span class="vet-crmv">' + escapeHtml(vet.crmv) + "</span>" : "") +
      (vet.descricao ? '<p class="paragraph dark-grey-color vet-bio">' + formatBio(vet.descricao) + "</p>" : "") +
      (regions ? '<div class="vet-block"><h4>Regiões que atende</h4><ul class="vet-regions">' + regions + "</ul></div>" : "") +
      "</div>";

    backdrop.hidden = false;
    document.body.style.overflow = "hidden";
    document.getElementById("vetClose").focus();
  }

  function closeModal() {
    backdrop.hidden = true;
    backdrop.innerHTML = "";
    document.body.style.overflow = "";
    if (lastFocused && lastFocused.focus) lastFocused.focus();
  }

  function cardFrom(event) {
    if (event.target.closest(".team-member-contact-link")) return null;
    return event.target.closest(".team-block");
  }

  grid.addEventListener("click", function (event) {
    var card = cardFrom(event);
    if (card) openModal(Number(card.dataset.vet));
  });

  grid.addEventListener("keydown", function (event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    var card = cardFrom(event);
    if (card) {
      event.preventDefault();
      openModal(Number(card.dataset.vet));
    }
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

  backdrop.addEventListener("click", function (event) {
    if (event.target === backdrop || event.target.closest("#vetClose")) closeModal();
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !backdrop.hidden) closeModal();
  });

  /* De onde vem a lista da equipe.

     O painel grava direto no repositorio, e o arquivo bruto do GitHub mostra
     a mudanca na hora. A copia que o GitHub Pages serve junto com o site so
     aparece depois que ele reconstroi tudo, o que as vezes leva varios
     minutos - por isso ela fica de reserva, para o caso do primeiro endereco
     falhar. O ?v= evita a copia guardada pelo navegador. */
  var FONTE_AO_VIVO = "https://raw.githubusercontent.com/mychelleaneves-debug" +
    "/vethomev1/gh-pages/data/veterinarios.json";
  var FONTE_RESERVA = "data/veterinarios.json";

  function buscarEquipe(endereco) {
    return fetch(endereco + "?v=" + Date.now(), { cache: "no-store" })
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      });
  }

  /* No computador (painel local) manda o arquivo da pasta, senao a previa
     mostraria o que esta no GitHub em vez do que acabou de ser editado aqui. */
  var noComputador = /^(localhost|127\.0\.0\.1|)$/.test(location.hostname);
  var primeira = noComputador ? FONTE_RESERVA : FONTE_AO_VIVO;
  var segunda = noComputador ? FONTE_AO_VIVO : FONTE_RESERVA;

  buscarEquipe(primeira)
    .catch(function () { return buscarEquipe(segunda); })
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
