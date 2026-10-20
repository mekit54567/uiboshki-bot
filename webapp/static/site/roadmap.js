// Фильтры роадмапа (webapp/routes/roadmap_page.py): «Все · Вышло · Не вышло · В работе · Дальше».
(function () {
  var chips = document.querySelectorAll(".chips button");
  for (var i = 0; i < chips.length; i++) chips[i].addEventListener("click", function () {
    var f = this.getAttribute("data-f");
    for (var j = 0; j < chips.length; j++) chips[j].classList.toggle("on", chips[j] === this);
    var rows = document.querySelectorAll("[data-st]");
    for (var k = 0; k < rows.length; k++) rows[k].classList.toggle("hide", f !== "all" && rows[k].getAttribute("data-st") !== f);
  });
})();
