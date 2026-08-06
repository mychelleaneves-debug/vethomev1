/* ==========================================================================
   VetHome — seção de veterinários
   Lê data/veterinarios.json, mostra 9 por página em grade 3x3 e abre um
   modal com a descrição ao clicar no card. A descrição NÃO aparece no card.
   ========================================================================== */
(function () {
  "use strict";

  var PER_PAGE = 9;
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
          '<img src="' + escapeHtml(vet.foto) + '" loading="lazy" alt="' + escapeHtml(vet.nome) + '" class="team-member-image"/>' +
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
      '<img src="' + escapeHtml(vet.foto) + '" alt="' + escapeHtml(vet.nome) + '" class="team-member-image"/>' +
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

  fetch("data/veterinarios.json")
    .then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(function (data) {
      vets = Array.isArray(data) ? data : [];
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
